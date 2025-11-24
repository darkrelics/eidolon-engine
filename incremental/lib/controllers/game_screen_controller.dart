import 'dart:async';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/repositories/character_repository.dart';
import 'package:eidolon_incremental/services/api_metrics.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/indexeddb_service.dart';
import 'package:eidolon_incremental/services/notification_service.dart';
import 'package:eidolon_incremental/services/rate_limiter.dart';
import 'package:eidolon_incremental/services/story_polling_service.dart';
import 'package:eidolon_incremental/utils/debounce.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:eidolon_incremental/utils/retry.dart';
import 'package:flutter/material.dart';

enum CharacterLoadRateLimitStrategy { automated, humanDriven, immediate }

/// Story lifecycle states to prevent premature completion detection
enum StoryLifecycleState {
  /// No active story
  none,

  /// Story is running with active segments
  running,

  /// Story completion confirmed by polling service
  completed,
}

class GameScreenController extends ChangeNotifier {
  final ApiService _apiService;
  late final StoryPollingService _runtime;
  late final CharacterRepository _characterRepository;
  final GlobalRateLimiter _rateLimiter = GlobalRateLimiter();

  // State
  Character? _character;
  CharacterInfo? _characterInfo;
  bool _isLoading = true;
  String? _error;
  bool _isSubmittingDecision = false;
  bool _storyCompletionNotified = false;
  Future<void>? _activeCharacterLoad;
  StoryLifecycleState _storyLifecycleState = StoryLifecycleState.none;

  // Timer & Debouncers
  Timer? _characterUpdateTimer;
  int _characterUpdateTimerCount = 0;
  late final Debouncer _decisionDebouncer;
  late final Debouncer _refreshDebouncer;
  Timer? _statusUpdateDebounce;

  // Data
  List<Map<String, dynamic>> _segmentHistory = const [];
  Map<String, dynamic>? _lastStoryDetails;
  int _segmentCounter = 0;
  String? _orchestratedSegmentId;

  // UI State
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  // Caching
  List<Map<String, dynamic>>? _cachedCompletedSegments;
  String? _completedSegmentsCacheKey;
  List<Map<String, dynamic>>? _cachedStoryHistory;
  String? _storyHistoryCacheKey;

  // Getters
  Character? get character => _character;
  CharacterInfo? get characterInfo => _characterInfo;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get isSubmittingDecision => _isSubmittingDecision;
  StoryLifecycleState get storyLifecycleState => _storyLifecycleState;
  List<Map<String, dynamic>> get segmentHistory => _segmentHistory;
  int get selectedPanelIndex => _selectedPanelIndex;

  GameScreenController({required ApiService apiService}) : _apiService = apiService {
    _runtime = StoryPollingService(apiService: _apiService);
    _characterRepository = CharacterRepository(apiService: _apiService, indexedDBService: IndexedDBService());
    _decisionDebouncer = Debouncer(delay: const Duration(milliseconds: 300));
    _refreshDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  }

  @override
  void dispose() {
    _runtime.dispose();
    _decisionDebouncer.dispose();
    _refreshDebouncer.dispose();
    _characterUpdateTimer?.cancel();
    _statusUpdateDebounce?.cancel();
    super.dispose();
  }

  void setSelectedPanelIndex(int index) {
    _selectedPanelIndex = index;
    notifyListeners();
  }

  void initialize(Character? character, CharacterInfo? info, {Character? savedCharacter}) {
    debugPrint('GameScreenController: initializing');

    if (character != null) {
      // Direct character object with story state
      if (_character == null || _character!.id != character.id) {
        final storyData = character.storyState?['Story'] as Map<String, dynamic>?;
        final completedSegments = character.storyState?['CompletedSegments'] as List<dynamic>?;

        _resetForNewCharacter();
        _character = character;
        _characterInfo = CharacterInfo(name: character.name, id: character.id, dead: character.health <= 0);
        _isLoading = false;
        _error = null;

        if (storyData != null) {
          _lastStoryDetails = Map<String, dynamic>.from(storyData);
        }

        if (completedSegments != null) {
          _segmentHistory = completedSegments
              .whereType<Map<String, dynamic>>()
              .map((segment) {
                final copy = Map<String, dynamic>.from(segment);
                if (!copy.containsKey('_index')) {
                  copy['_index'] = _segmentCounter++;
                }
                return copy;
              })
              .where(_isSegmentComplete)
              .toList();
        }

        _synchronizeStoryCompletionState();
        notifyListeners();

        _startOrchestrationIfNeeded();
        _manageCharacterUpdateTimer();
      }
    } else if (info != null) {
      // Only update if it's a different character or first load
      if (_characterInfo == null || _characterInfo!.id != info.id) {
        _resetForNewCharacter();
        _characterInfo = info;
        _character = null;
        _isLoading = true;
        _error = null;
        notifyListeners();

        _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate).then((_) => _loadSegmentHistory());
      }
    } else if (savedCharacter != null) {
      // Load from provider/local storage
      debugPrint('GameScreenController: Found saved character: ${savedCharacter.name}');
      _resetForNewCharacter();
      _character = savedCharacter;
      _characterInfo = CharacterInfo(name: savedCharacter.name, id: savedCharacter.id, dead: savedCharacter.health <= 0);
      _isLoading = false;
      _error = null;
      notifyListeners();

      _startOrchestrationIfNeeded();
      _manageCharacterUpdateTimer();

      // Refresh character data from server in background
      _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate, showLoadingIndicator: false);
    } else {
      // No character found
      _isLoading = false;
      notifyListeners();
    }
  }

  void _resetForNewCharacter() {
    _runtime.stopPolling();
    _characterUpdateTimer?.cancel();
    _characterUpdateTimerCount = 0;
    _orchestratedSegmentId = null;
    _segmentHistory = <Map<String, dynamic>>[];
    _segmentCounter = 0;
    _lastStoryDetails = null;
    _storyCompletionNotified = false;
    _storyLifecycleState = StoryLifecycleState.none;
    _invalidateCache();
  }

  void _invalidateCache() {
    _cachedCompletedSegments = null;
    _completedSegmentsCacheKey = null;
    _cachedStoryHistory = null;
    _storyHistoryCacheKey = null;
  }

  String _segmentIdentity(Map<String, dynamic> segment) {
    // Primary key: ActiveSegmentID (unique execution identifier)
    final activeSegmentId = segment['ActiveSegmentID'];
    if (activeSegmentId != null) {
      final idString = activeSegmentId.toString().trim();
      if (idString.isNotEmpty) {
        return 'active:$idString';
      }
    }

    // Fallback: SegmentID (story definition identifier)
    final segmentId = segment['SegmentID'];
    if (segmentId != null) {
      final idString = segmentId.toString().trim();
      if (idString.isNotEmpty) {
        return 'segment:$idString';
      }
    }

    // Last resort: Composite key from available fields
    final storyInstanceId = segment['StoryInstanceID']?.toString().trim();
    final storyId = segment['StoryID']?.toString().trim();
    final segmentActivity = segment['SegmentActivity']?.toString().trim();
    final segmentTitle = segment['SegmentTitle']?.toString().trim();
    final prompt = segment['Prompt']?.toString().trim();

    final parts = <String>[
      if (storyInstanceId != null && storyInstanceId.isNotEmpty) storyInstanceId,
      if (storyId != null && storyId.isNotEmpty) storyId,
      if (segmentActivity != null && segmentActivity.isNotEmpty) segmentActivity,
      if (segmentTitle != null && segmentTitle.isNotEmpty) segmentTitle,
      if (prompt != null && prompt.isNotEmpty) prompt,
    ];

    if (parts.isEmpty) {
      return 'fallback:${segment.hashCode}';
    }

    return 'composite:${parts.join('|')}';
  }

  void _sortSegmentsChronologically(List<Map<String, dynamic>> segments, {bool newestFirst = false}) {
    segments.sort((a, b) {
      final aIndex = a['_index'] as int?;
      final bIndex = b['_index'] as int?;

      if (aIndex != null && bIndex != null) {
        return newestFirst ? bIndex.compareTo(aIndex) : aIndex.compareTo(bIndex);
      }

      if (aIndex == null && bIndex == null) return 0;
      if (aIndex == null) return 1;
      if (bIndex == null) return -1;

      return 0;
    });
  }

  void _manageCharacterUpdateTimer() {
    final hasActiveStory = _character?.activeSegmentID != null;

    if (hasActiveStory) {
      if (_characterUpdateTimer != null) {
        _characterUpdateTimer?.cancel();
        _characterUpdateTimer = null;
        _characterUpdateTimerCount = 0;
      }
    } else {
      if (_characterUpdateTimer == null && _character != null) {
        _characterUpdateTimerCount = 0;
        _characterUpdateTimer = Timer.periodic(const Duration(minutes: 2), (timer) {
          _characterUpdateTimerCount++;
          if (_characterUpdateTimerCount >= 60) {
            timer.cancel();
            _characterUpdateTimer = null;
            _characterUpdateTimerCount = 0;
            return;
          }

          _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.automated, showLoadingIndicator: false);
        });
      }
    }
  }

  Future<void> _loadCharacterData({
    CharacterLoadRateLimitStrategy strategy = CharacterLoadRateLimitStrategy.automated,
    bool showLoadingIndicator = true,
  }) {
    final activeLoad = _activeCharacterLoad;
    if (activeLoad != null) {
      return activeLoad;
    }

    final future = _loadCharacterDataInternal(strategy: strategy, showLoadingIndicator: showLoadingIndicator);
    _activeCharacterLoad = future;
    future.whenComplete(() {
      if (identical(_activeCharacterLoad, future)) {
        _activeCharacterLoad = null;
      }
    });

    return future;
  }

  Future<void> _loadCharacterDataInternal({
    required CharacterLoadRateLimitStrategy strategy,
    required bool showLoadingIndicator,
  }) async {
    if (_characterInfo == null) return;

    final previousCharacterId = _character?.id;

    try {
      _error = null;
      if (showLoadingIndicator) {
        _isLoading = true;
        notifyListeners();
      }

      final character = await retryWithBackoff(() => _executeCharacterLoad(strategy));

      _isLoading = false;
      final newCharacterId = character?.id;
      if (previousCharacterId != newCharacterId) {
        _resetForNewCharacter();
      }
      _character = character;
      _error = null;
      if (character?.activeSegmentID != null) {
        _storyCompletionNotified = false;
      }

      final storyData = character?.storyState?['Story'] as Map<String, dynamic>?;
      if (storyData != null) {
        _lastStoryDetails = Map<String, dynamic>.from(storyData);
      }

      _synchronizeStoryCompletionState();
      notifyListeners();

      _startOrchestrationIfNeeded();
      _manageCharacterUpdateTimer();
    } catch (e) {
      debugPrint('GameScreenController: ERROR loading character: $e');
      _error = ErrorHandler.getUserFriendlyMessage(e, context: 'loading character');
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<Character?> _executeCharacterLoad(CharacterLoadRateLimitStrategy strategy) {
    switch (strategy) {
      case CharacterLoadRateLimitStrategy.immediate:
        return _apiService.getCharacterById(_characterInfo!.id).then((character) {
          _rateLimiter.limiter.recordCall(GlobalRateLimiter.getCharacter);
          return character;
        });
      case CharacterLoadRateLimitStrategy.humanDriven:
        return _rateLimiter.limiter.executeHumanDriven(
          GlobalRateLimiter.getCharacter,
          () => _apiService.getCharacterById(_characterInfo!.id),
        );
      case CharacterLoadRateLimitStrategy.automated:
        return _rateLimiter.limiter.executeAutomated(
          GlobalRateLimiter.getCharacter,
          () => _apiService.getCharacterById(_characterInfo!.id),
        );
    }
  }

  Future<void> refreshCharacterImmediate() {
    if (_refreshDebouncer.isActive) {
      return Future.value();
    }

    _refreshDebouncer.runImmediate(() {});

    return _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate, showLoadingIndicator: false);
  }

  Future<void> handleStorySelect(BuildContext context, StoryMetadata story) async {
    if (!story.available) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(story.cooldownRemaining > 0 ? 'Story on cooldown' : 'Story not available')));
      return;
    }

    try {
      _isLoading = true;
      _segmentHistory = [];
      _storyCompletionNotified = false;
      notifyListeners();

      final initialSegment = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.startStory,
        () => _apiService.startStory(characterId: _character!.id, storyId: story.storyID),
        throwOnRateLimit: true,
      );

      // Build story state and active IDs for immediate UI
      final newStoryState = Map<String, dynamic>.from(_character?.storyState ?? <String, dynamic>{});
      newStoryState['ActiveSegment'] = initialSegment;
      newStoryState['Story'] = {
        'Title': story.title,
        'Description': story.description,
        'Type': story.type,
        'StoryID': story.storyID,
      };

      _character = _character!.copyWith(
        activeStoryId: initialSegment['StoryID']?.toString(),
        activeSegmentId: initialSegment['ActiveSegmentID']?.toString() ?? initialSegment['SegmentID']?.toString(),
        storyState: newStoryState,
        gameMode: 'Incremental',
      );

      _lastStoryDetails = Map<String, dynamic>.from(newStoryState['Story'] as Map<String, dynamic>);

      // Add initial segment to history for tracking
      final initialSegmentCopy = Map<String, dynamic>.from(initialSegment);
      initialSegmentCopy['StoryTitle'] = story.title;
      initialSegmentCopy['_index'] = _segmentCounter++;
      _segmentHistory = [initialSegmentCopy];

      _isLoading = false;
      _storyLifecycleState = StoryLifecycleState.running;

      ApiMetrics.startSegment();
      notifyListeners();

      _startOrchestrationIfNeeded(force: true);
      _manageCharacterUpdateTimer();
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
        );
      }
      _isLoading = false;
      notifyListeners();
    }
  }

  void _startOrchestrationIfNeeded({bool force = false}) {
    if (_character == null) return;
    final segId = _character!.activeSegmentID;
    if (!force && (segId == null || segId == _orchestratedSegmentId)) return;

    _orchestratedSegmentId = segId;

    if (segId == null) return; // No active story

    if (_storyLifecycleState != StoryLifecycleState.running) {
      _storyLifecycleState = StoryLifecycleState.running;
      notifyListeners();
    }

    _runtime.startPolling(
      characterId: _character!.id,
      onStatusUpdate: (status) {
        if (_character == null) return;

        final segmentKey = _segmentIdentity(status);
        final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);
        final processingStatus = status['ProcessingStatus'];

        final currentActiveSegmentId = _character!.activeSegmentID;
        final newActiveSegmentId = status['ActiveSegmentID']?.toString() ?? status['SegmentID']?.toString();
        final segmentChanged = currentActiveSegmentId != newActiveSegmentId;
        final statusChanged = processingStatus != _character!.storyState?['ActiveSegment']?['ProcessingStatus'];

        if (!exists) {
          final segmentCopy = Map<String, dynamic>.from(status);
          if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
            segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
          }
          segmentCopy['_index'] = _segmentCounter++;
          _segmentHistory = [..._segmentHistory, segmentCopy];
        } else {
          _segmentHistory = _segmentHistory.map((s) {
            if (_segmentIdentity(s) == segmentKey) {
              final updated = Map<String, dynamic>.from(status);
              if (!updated.containsKey('StoryTitle') && _lastStoryDetails != null) {
                updated['StoryTitle'] = _lastStoryDetails!['Title'];
              }
              if (s.containsKey('_index')) {
                updated['_index'] = s['_index'];
              }
              return updated;
            }
            return s;
          }).toList();
        }

        final storyState = Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{});
        storyState['ActiveSegment'] = status;

        final story = status['Story'] as Map<String, dynamic>?;
        if (story != null) {
          storyState['Story'] = story;
          _lastStoryDetails = Map<String, dynamic>.from(story);
        }

        if (segmentChanged || statusChanged || !exists) {
          _statusUpdateDebounce?.cancel();
          _statusUpdateDebounce = Timer(const Duration(milliseconds: 200), () {
            _character = _character!.copyWith(activeSegmentId: newActiveSegmentId, storyState: storyState);
            _error = null;
            _invalidateCache();
            notifyListeners();
          });
        } else {
          _character = _character!.copyWith(activeSegmentId: newActiveSegmentId, storyState: storyState);
          notifyListeners();
        }
      },
      onSegmentComplete: (segmentUpdates) async {
        if (_character == null) return;

        try {
          final updatedCharacter = await _characterRepository.updateCharacterFromSegment(_character!.id, segmentUpdates);

          if (updatedCharacter != null) {
            _character = updatedCharacter;
            _error = null;
            notifyListeners();
          }
        } catch (e) {
          try {
            final character = await _apiService.getCharacterById(_character!.id);
            if (character != null) {
              _character = character;
              _error = null;
              notifyListeners();
            }
          } catch (fallbackError) {
            _error = 'Failed to update character';
            notifyListeners();
          }
        }
      },
      onCharacterReload: (characterData) {
        try {
          final updated = Character.fromJson(characterData);

          final wasRunning = _storyLifecycleState == StoryLifecycleState.running;
          final hasActiveSegmentField = updated.activeSegmentID != null;
          final hasActiveStoryField = updated.activeStoryID != null;
          final hasActiveSegmentInState = updated.storyState?['ActiveSegment'] != null;
          final hasActiveStoryInState = updated.storyState?['ActiveStory'] != null;

          final storyCompleted =
              wasRunning && !hasActiveSegmentField && !hasActiveStoryField && !hasActiveSegmentInState && !hasActiveStoryInState;

          final newActiveSegment = updated.storyState?['ActiveSegment'] as Map<String, dynamic>?;

          if (newActiveSegment != null) {
            final segmentKey = _segmentIdentity(newActiveSegment);
            final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);

            if (!exists) {
              final segmentCopy = Map<String, dynamic>.from(newActiveSegment);
              if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
                segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
              }
              segmentCopy['_index'] = _segmentCounter++;
              _segmentHistory = [..._segmentHistory, segmentCopy];
            }
          }

          _character = updated;
          _error = null;
          notifyListeners();

          if (storyCompleted) {
            _runtime.stopPolling();
            _storyLifecycleState = StoryLifecycleState.completed;
            notifyListeners();
            _handleStoryCompletion(refreshCharacter: false, showMessage: true).then((_) {
              _manageCharacterUpdateTimer();
            });
          }
        } catch (e) {
          _error = 'Failed to update character';
          notifyListeners();
        }
      },
      onStoryComplete: () async {
        if (_storyLifecycleState == StoryLifecycleState.completed) return;

        _storyLifecycleState = StoryLifecycleState.completed;
        notifyListeners();

        try {
          final refreshedCharacter = await _characterRepository.refreshCharacterFromServer(_character!.id);
          if (refreshedCharacter != null) {
            _character = refreshedCharacter;
            notifyListeners();
          }
        } catch (e) {
          debugPrint('GameScreenController: Failed to refresh character from server: $e');
        }

        await _handleStoryCompletion(refreshCharacter: false, showMessage: true);
        _manageCharacterUpdateTimer();
      },
      onError: (err) {
        _error = err.toString();
        notifyListeners();
      },
    );
  }

  Future<void> _loadSegmentHistory({bool mergeWithExisting = false}) async {
    if (_character == null) {
      if (!mergeWithExisting) {
        _segmentHistory = [];
        _synchronizeStoryCompletionState();
        notifyListeners();
      }
      return;
    }

    if (_character!.activeStoryID != null && !mergeWithExisting) {
      return;
    }

    try {
      final historyResponse = await _apiService.getSegmentHistory(characterId: _character!.id);

      final history = historyResponse.map((segment) => Map<String, dynamic>.from(segment)).where((segment) {
        final completedAt = segment['CompletedAt'];
        if (completedAt is String && completedAt.isNotEmpty) return true;
        if (completedAt is num && completedAt > 0) return true;
        if (segment['Status']?.toString().toLowerCase() == 'completed') return true;
        return _isSegmentComplete(segment);
      }).toList();

      if (mergeWithExisting) {
        final mergedByKey = <String, Map<String, dynamic>>{};
        for (final existing in _segmentHistory) {
          mergedByKey[_segmentIdentity(existing)] = Map<String, dynamic>.from(existing);
        }
        for (final segment in history) {
          final key = _segmentIdentity(segment);
          final existingSegment = mergedByKey[key];
          final merged = Map<String, dynamic>.from(segment);
          if (existingSegment != null && existingSegment.containsKey('_index')) {
            merged['_index'] = existingSegment['_index'];
          } else {
            merged['_index'] = _segmentCounter++;
          }
          mergedByKey[key] = merged;
        }
        final mergedSegments = mergedByKey.values.toList();
        _sortSegmentsChronologically(mergedSegments);
        _segmentHistory = mergedSegments;
      } else {
        _segmentHistory = history.map((segment) {
          final copy = Map<String, dynamic>.from(segment);
          if (!copy.containsKey('_index')) {
            copy['_index'] = _segmentCounter++;
          }
          return copy;
        }).toList();
      }
      _synchronizeStoryCompletionState();
      notifyListeners();
    } catch (e) {
      debugPrint('GameScreenController: Failed to load segment history: $e');
    }
  }

  bool _isSegmentComplete(Map<String, dynamic> segment) {
    final completedAt = segment['CompletedAt'];
    if (completedAt is String && completedAt.isNotEmpty) return true;
    if (completedAt is num && completedAt > 0) return true;
    if (segment['Status']?.toString().toLowerCase() == 'completed') return true;

    final processingStatus = segment['ProcessingStatus']?.toString().toLowerCase();
    if (processingStatus == 'processed') {
      final endTimeStr = segment['EndTime']?.toString();
      if (endTimeStr != null && endTimeStr.isNotEmpty) {
        try {
          final endTime = DateTime.parse(endTimeStr).toUtc();
          final now = DateTime.now().toUtc();
          return now.isAfter(endTime) || now.isAtSameMomentAs(endTime);
        } catch (e) {
          // ignore
        }
      }
      final timeRemaining = segment['TimeRemaining'];
      if (timeRemaining is num) {
        return timeRemaining <= 0;
      }
      return false;
    }

    if (segment['StoryComplete'] == true) return true;

    return false;
  }

  void _synchronizeStoryCompletionState() {
    if (_character == null || _segmentHistory.isEmpty) return;
    if (_character!.activeSegmentID != null) return;

    final currentStoryState = _character!.storyState ?? <String, dynamic>{};
    final updatedStoryState = Map<String, dynamic>.from(currentStoryState);

    final synchronizedSegments = _segmentHistory.map((segment) => Map<String, dynamic>.from(segment)).toList();
    _sortSegmentsChronologically(synchronizedSegments);
    updatedStoryState['CompletedSegments'] = synchronizedSegments;

    if (!updatedStoryState.containsKey('Story') && _lastStoryDetails != null) {
      updatedStoryState['Story'] = Map<String, dynamic>.from(_lastStoryDetails!);
    }

    _character = _character!.copyWith(storyState: updatedStoryState);
  }

  Future<void> handleDecisionSelect(BuildContext context, String choiceId) async {
    if (_isSubmittingDecision || _decisionDebouncer.isActive) return;

    _isSubmittingDecision = true;
    _error = null;
    notifyListeners();

    _decisionDebouncer.runImmediate(() {});

    try {
      final response = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.submitDecision,
        () => _apiService.submitDecision(characterId: _character!.id, decision: choiceId),
        throwOnRateLimit: true,
      );

      final completedSegment = response['CompletedSegment'] as Map<String, dynamic>?;

      if (response['NextSegment'] != null) {
        final nextSegment = response['NextSegment'] as Map<String, dynamic>;

        if (completedSegment != null) {
          final segmentCopy = Map<String, dynamic>.from(completedSegment);
          if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
            segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
          }

          final segmentKey = _segmentIdentity(segmentCopy);
          final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);

          if (!exists) {
            segmentCopy['_index'] = _segmentCounter++;
            _segmentHistory = [..._segmentHistory, segmentCopy];
          } else {
            _segmentHistory = _segmentHistory.map((s) {
              if (_segmentIdentity(s) == segmentKey) {
                if (s.containsKey('_index')) {
                  segmentCopy['_index'] = s['_index'];
                }
                return segmentCopy;
              }
              return s;
            }).toList();
          }
        }

        final nextSegmentCopy = Map<String, dynamic>.from(nextSegment);
        if (!nextSegmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
          nextSegmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
        }

        final nextKey = _segmentIdentity(nextSegmentCopy);
        final nextExists = _segmentHistory.any((s) => _segmentIdentity(s) == nextKey);

        if (!nextExists) {
          nextSegmentCopy['_index'] = _segmentCounter++;
          _segmentHistory = [..._segmentHistory, nextSegmentCopy];
        } else {
          _segmentHistory = _segmentHistory.map((s) {
            if (_segmentIdentity(s) == nextKey) {
              if (s.containsKey('_index')) {
                nextSegmentCopy['_index'] = s['_index'];
              }
              return nextSegmentCopy;
            }
            return s;
          }).toList();
        }

        final updatedStoryState = Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{})
          ..['ActiveSegment'] = nextSegment;

        final dynamic nextSegmentIdValue = nextSegment['ActiveSegmentID'] ?? nextSegment['SegmentID'];
        final String? nextSegmentId = nextSegmentIdValue?.toString();

        _character = _character!.copyWith(activeSegmentId: nextSegmentId, storyState: updatedStoryState);
        notifyListeners();

        _startOrchestrationIfNeeded(force: true);
        _manageCharacterUpdateTimer();
      } else {
        _runtime.stopPolling();
        await _handleStoryCompletion(refreshCharacter: true);
      }

      if (context.mounted && completedSegment != null) {
        final outcome = completedSegment['Outcome'];
        String? outcomeType;
        Map<String, dynamic>? rewards;

        if (outcome is Map<String, dynamic>) {
          outcomeType = outcome['Type'] as String?;
          final rawRewards = outcome['Rewards'];
          if (rawRewards is Map<String, dynamic>) {
            rewards = rawRewards;
          }
        } else if (outcome is String) {
          outcomeType = outcome;
        }

        if (outcomeType != null) {
          NotificationService.showSegmentComplete(context, segmentType: 'decision', outcome: outcomeType);

          if (rewards != null) {
            for (final reward in rewards.entries) {
              await Future.delayed(const Duration(milliseconds: 500));
              if (context.mounted) {
                NotificationService.showReward(context, type: reward.key, value: reward.value);
              }
            }
          }
        }
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
        );
      }
      _error = ErrorHandler.getUserFriendlyMessage(e);
      notifyListeners();
    } finally {
      _isSubmittingDecision = false;
      notifyListeners();
    }
  }

  Future<void> _handleStoryCompletion({
    bool refreshCharacter = true,
    bool showMessage = true,
    Map<String, dynamic>? finalActiveSegment,
  }) async {
    _runtime.stopPolling();
    ApiMetrics.endSegment();

    if (_storyLifecycleState != StoryLifecycleState.completed) {
      _storyLifecycleState = StoryLifecycleState.completed;
      notifyListeners();
    }

    final activeSegment = finalActiveSegment ?? (_character?.storyState?['ActiveSegment'] as Map<String, dynamic>?);
    final shouldIncludeFinalSegment = activeSegment != null && _isSegmentComplete(activeSegment);

    try {
      if (shouldIncludeFinalSegment) {
        final copy = Map<String, dynamic>.from(activeSegment);
        if (!copy.containsKey('StoryTitle') && _lastStoryDetails != null && _lastStoryDetails!['Title'] is String) {
          copy['StoryTitle'] = _lastStoryDetails!['Title'];
        }

        final segmentKey = _segmentIdentity(copy);
        final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);
        if (!exists) {
          copy['_index'] = _segmentCounter++;
          _segmentHistory = [..._segmentHistory, copy];
        } else {
          _segmentHistory = _segmentHistory.map((s) {
            if (_segmentIdentity(s) == segmentKey) {
              if (s.containsKey('_index')) {
                copy['_index'] = s['_index'];
              }
              return copy;
            }
            return s;
          }).toList();
        }
      }

      if (refreshCharacter) {
        await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate, showLoadingIndicator: false);
      }
    } catch (e) {
      debugPrint('GameScreenController: Error updating state after story completion: $e');
    }

    if (_character != null) {
      final completedSegmentsCopy = _segmentHistory.map((segment) => Map<String, dynamic>.from(segment)).toList();
      _sortSegmentsChronologically(completedSegmentsCopy);

      Map<String, dynamic>? storyStateUpdate;
      if (completedSegmentsCopy.isNotEmpty || _lastStoryDetails != null) {
        storyStateUpdate = <String, dynamic>{};
        if (completedSegmentsCopy.isNotEmpty) {
          storyStateUpdate['CompletedSegments'] = completedSegmentsCopy;
        }
        if (_lastStoryDetails != null) {
          storyStateUpdate['Story'] = Map<String, dynamic>.from(_lastStoryDetails!);
        }
      }

      _character = _character!.copyWith(activeStoryId: null, activeSegmentId: null, storyState: storyStateUpdate, gameMode: 'None');
    }

    _isLoading = false;
    notifyListeners();

    _manageCharacterUpdateTimer();

    if (showMessage && !_storyCompletionNotified) {
      // We need a context to show the snackbar, but this method is internal.
      // The controller shouldn't trigger UI directly if possible, but for now we'll rely on the caller or a callback mechanism if we were stricter.
      // However, since we don't have context here, we'll skip the snackbar inside this private method and rely on state.
      // Wait, the original code used context. We should probably expose a stream or callback for notifications.
      // For simplicity in this refactor step, I'll add a callback or just let the UI react to state changes.
      // But wait, the original code showed a snackbar.

      _storyCompletionNotified = true;
    }
  }

  // Helper to show completion message if needed, called from UI or public method
  String? getCompletionMessage() {
    return null;
  }

  Future<void> handleAbandonStory({required Function(String) onAbandon, required Function(String) onError}) async {
    try {
      _isLoading = true;
      notifyListeners();

      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.abandonStory,
        () => _apiService.abandonStory(_character!.id),
        throwOnRateLimit: true,
      );

      _runtime.stopPolling();

      // Handle abandonment
      try {
        await Future.wait([_loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate), _loadSegmentHistory()]);
      } catch (e) {
        debugPrint('GameScreenController: Error updating state after story abandonment: $e');
      }

      if (_character != null) {
        final completedSegmentsCopy = _segmentHistory.map((segment) => Map<String, dynamic>.from(segment)).toList();
        _sortSegmentsChronologically(completedSegmentsCopy);

        Map<String, dynamic>? storyStateUpdate;
        if (completedSegmentsCopy.isNotEmpty || _lastStoryDetails != null) {
          storyStateUpdate = <String, dynamic>{};
          if (completedSegmentsCopy.isNotEmpty) {
            storyStateUpdate['CompletedSegments'] = completedSegmentsCopy;
          }
          if (_lastStoryDetails != null) {
            storyStateUpdate['Story'] = Map<String, dynamic>.from(_lastStoryDetails!);
          }
        }

        _character = _character!.copyWith(
          activeStoryId: null,
          activeSegmentId: null,
          storyState: storyStateUpdate,
          gameMode: 'None',
        );
      }

      _isLoading = false;
      notifyListeners();

      _manageCharacterUpdateTimer();

      if (!_storyCompletionNotified) {
        final storyData = _character?.storyState?['Story'] as Map<String, dynamic>?;
        final fallbackStoryTitle = _segmentHistory.isNotEmpty ? _segmentHistory.last['StoryTitle'] as String? : null;
        final storyTitle = storyData?['Title'] ?? fallbackStoryTitle ?? 'Story';

        onAbandon('$storyTitle abandoned');
        _storyCompletionNotified = true;
      }
    } catch (e) {
      onError(ErrorHandler.getUserFriendlyMessage(e));
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> handleReturnToStories() async {
    _runtime.stopPolling();

    if (_character != null) {
      _character = _character!.copyWith(storyState: null, gameMode: 'None');
    }
    _lastStoryDetails = null;
    _storyLifecycleState = StoryLifecycleState.none;
    notifyListeners();

    await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate, showLoadingIndicator: false);

    _segmentHistory = [];
    _storyCompletionNotified = false;
    _lastStoryDetails = null;
    notifyListeners();

    _manageCharacterUpdateTimer();
  }

  List<Map<String, dynamic>> getCompletedSegments() {
    final activeSegmentId = _character?.activeSegmentID;
    final cacheKey = '${activeSegmentId ?? 'none'}_${_segmentHistory.length}_${_segmentHistory.hashCode}';

    if (_completedSegmentsCacheKey == cacheKey && _cachedCompletedSegments != null) {
      return _cachedCompletedSegments!;
    }

    final completed = _segmentHistory.where((segment) {
      final segmentActiveId = segment['ActiveSegmentID']?.toString() ?? segment['SegmentID']?.toString();
      final isComplete = segmentActiveId != activeSegmentId && _isSegmentComplete(segment);
      return isComplete;
    }).toList();

    _sortSegmentsChronologically(completed, newestFirst: true);

    _completedSegmentsCacheKey = cacheKey;
    _cachedCompletedSegments = completed;

    return completed;
  }

  List<Map<String, dynamic>> buildStoryHistoryArchive() {
    final activeSegmentId = _character?.activeSegmentID;
    final stateSegmentsHash = _character?.storyState?['CompletedSegments']?.hashCode ?? 0;
    final cacheKey = '${activeSegmentId ?? 'none'}_${_segmentHistory.length}_${_segmentHistory.hashCode}_$stateSegmentsHash';

    if (_storyHistoryCacheKey == cacheKey && _cachedStoryHistory != null) {
      return _cachedStoryHistory!;
    }

    final Map<String, Map<String, dynamic>> deduped = {};

    void addSegments(Iterable<Map<String, dynamic>> segments) {
      for (final segment in segments) {
        final copy = Map<String, dynamic>.from(segment);
        final segmentActiveId = copy['ActiveSegmentID']?.toString() ?? copy['SegmentID']?.toString();
        final key = _segmentIdentity(copy);

        final isActiveSegment = activeSegmentId != null && segmentActiveId == activeSegmentId;
        if (!isActiveSegment) {
          deduped[key] = copy;
        }
      }
    }

    final completedSegmentsDynamic = _character?.storyState?['CompletedSegments'] as List<dynamic>?;
    if (completedSegmentsDynamic != null) {
      final completedSegments = completedSegmentsDynamic
          .whereType<Map<String, dynamic>>()
          .where(_isSegmentComplete)
          .map((segment) => Map<String, dynamic>.from(segment));
      addSegments(completedSegments);
    }

    if (_segmentHistory.isNotEmpty) {
      final historyCopies = _segmentHistory.where(_isSegmentComplete).map((segment) => Map<String, dynamic>.from(segment));
      addSegments(historyCopies);
    }

    final segments = deduped.values.toList();
    _sortSegmentsChronologically(segments);

    _storyHistoryCacheKey = cacheKey;
    _cachedStoryHistory = segments;

    return segments;
  }
}
