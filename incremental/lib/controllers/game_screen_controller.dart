import 'dart:async';

import 'package:eidolon_incremental/controllers/segment_history_manager.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/repositories/character_repository.dart';
import 'package:eidolon_incremental/services/api_metrics.dart';
import 'package:eidolon_incremental/services/api_service.dart';
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
  final CharacterRepository _characterRepository;
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
  bool _disposed = false;
  bool _handlingStoryCompletion = false;
  String? _initializedCharacterId;

  // Timer & Debouncers
  Timer? _characterUpdateTimer;
  int _characterUpdateTimerCount = 0;
  late final Debouncer _decisionDebouncer;
  late final Debouncer _refreshDebouncer;
  Timer? _statusUpdateDebounce;

  // Data
  late final SegmentHistoryManager _segmentHistory;
  Map<String, dynamic>? _lastStoryDetails;
  String? _orchestratedSegmentId;

  // UI State
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  // Getters
  Character? get character => _character;
  CharacterInfo? get characterInfo => _characterInfo;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get isSubmittingDecision => _isSubmittingDecision;
  StoryLifecycleState get storyLifecycleState => _storyLifecycleState;
  List<Map<String, dynamic>> get segmentHistory => _segmentHistory.segments;
  int get selectedPanelIndex => _selectedPanelIndex;

  GameScreenController({required ApiService apiService, required CharacterRepository characterRepository})
      : _apiService = apiService,
        _characterRepository = characterRepository {
    _segmentHistory = SegmentHistoryManager();
    _runtime = StoryPollingService(apiService: _apiService);
    _decisionDebouncer = Debouncer(delay: const Duration(milliseconds: 300));
    _refreshDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  }

  @override
  void dispose() {
    _disposed = true;
    _runtime.dispose();
    _decisionDebouncer.dispose();
    _refreshDebouncer.dispose();
    _characterUpdateTimer?.cancel();
    _statusUpdateDebounce?.cancel();
    // Note: _activeCharacterLoad is not cancelled explicitly
    // Instead, we check _disposed before calling notifyListeners()
    // This allows in-flight requests to complete safely without affecting UI
    super.dispose();
  }

  @override
  void notifyListeners() {
    if (!_disposed) {
      super.notifyListeners();
    }
  }

  void setSelectedPanelIndex(int index) {
    _selectedPanelIndex = index;
    notifyListeners();
  }

  void initialize(Character? character, CharacterInfo? info, {Character? savedCharacter}) {
    // Determine the ID of the character being initialized
    final incomingId = character?.id ?? info?.id ?? savedCharacter?.id;

    // Skip re-initialization for the same character (prevents didChangeDependencies re-entry)
    if (incomingId != null && _initializedCharacterId == incomingId) {
      return;
    }

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
          final typedSegments = completedSegments.whereType<Map<String, dynamic>>().toList();
          final indexed = _segmentHistory.assignIndices(typedSegments);
          _segmentHistory.segments = indexed.where(_segmentHistory.isSegmentComplete).toList();
        }

        _synchronizeStoryCompletionState();
        _initializedCharacterId = character.id;
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
        _initializedCharacterId = info.id;
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
      _initializedCharacterId = savedCharacter.id;
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
    _segmentHistory.reset();
    _lastStoryDetails = null;
    _storyCompletionNotified = false;
    _storyLifecycleState = StoryLifecycleState.none;
    _handlingStoryCompletion = false;
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
    if (_characterInfo == null || _disposed) return;

    final previousCharacterId = _character?.id;

    try {
      _error = null;
      if (showLoadingIndicator) {
        _isLoading = true;
        notifyListeners();
      }

      final character = await retryWithBackoff(() => _executeCharacterLoad(strategy));

      // Check if disposed after async operation
      if (_disposed) {
        debugPrint('GameScreenController: Disposed during character load - ignoring result');
        return;
      }

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
      // Check if disposed before error handling
      if (_disposed) {
        debugPrint('GameScreenController: Disposed during character load error - ignoring');
        return;
      }

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
      _segmentHistory.segments = [];
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
      _segmentHistory.addOrUpdateSegment(initialSegmentCopy, _lastStoryDetails);

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

    // Extract segment start time from current state for initial poll delay calculation
    DateTime? segmentStartTime;
    final activeSegment = _character!.storyState?['ActiveSegment'];
    if (activeSegment != null && activeSegment['StartTime'] != null) {
      try {
        segmentStartTime = DateTime.parse(activeSegment['StartTime'] as String).toUtc();
      } catch (e) {
        // If parsing fails, polling service will use default 60-second delay
        debugPrint('GameScreenController: Failed to parse StartTime: $e');
      }
    }

    _runtime.startPolling(
      characterId: _character!.id,
      segmentStartTime: segmentStartTime,
      onStatusUpdate: (status) {
        if (_disposed || _character == null) return;

        final segmentKey = _segmentHistory.segmentIdentity(status);
        final exists = _segmentHistory.segments.any((s) => _segmentHistory.segmentIdentity(s) == segmentKey);
        final processingStatus = status['ProcessingStatus'];

        final currentActiveSegmentId = _character!.activeSegmentID;
        final newActiveSegmentId = status['ActiveSegmentID']?.toString() ?? status['SegmentID']?.toString();
        final segmentChanged = currentActiveSegmentId != newActiveSegmentId;
        final statusChanged = processingStatus != _character!.storyState?['ActiveSegment']?['ProcessingStatus'];

        _segmentHistory.addOrUpdateSegment(status, _lastStoryDetails);

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
            _segmentHistory.invalidateCache();
            notifyListeners();
          });
        } else {
          _character = _character!.copyWith(activeSegmentId: newActiveSegmentId, storyState: storyState);
          notifyListeners();
        }
      },
      onSegmentComplete: (segmentUpdates) async {
        if (_disposed || _character == null) return;

        try {
          final updatedCharacter = await _characterRepository.updateCharacterFromSegment(_character!.id, segmentUpdates);

          if (_disposed) return;

          if (updatedCharacter != null) {
            _character = updatedCharacter;
            _error = null;
            notifyListeners();
          }
        } catch (e) {
          if (_disposed) return;

          try {
            final character = await _apiService.getCharacterById(_character!.id);

            if (_disposed) return;

            if (character != null) {
              _character = character;
              _error = null;
              notifyListeners();
            }
          } catch (fallbackError) {
            if (_disposed) return;

            _error = 'Failed to update character';
            notifyListeners();
          }
        }
      },
      onCharacterReload: (characterData) {
        if (_disposed) return;

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
            _segmentHistory.addOrUpdateSegment(newActiveSegment, _lastStoryDetails);
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
        if (_disposed || _storyLifecycleState == StoryLifecycleState.completed) return;

        _storyLifecycleState = StoryLifecycleState.completed;
        notifyListeners();

        try {
          final refreshedCharacter = await _characterRepository.refreshCharacterFromServer(_character!.id);

          if (_disposed) return;

          if (refreshedCharacter != null) {
            _character = refreshedCharacter;
            notifyListeners();
          }
        } catch (e) {
          if (_disposed) return;

          debugPrint('GameScreenController: Failed to refresh character from server: $e');
        }

        if (_disposed) return;

        await _handleStoryCompletion(refreshCharacter: false, showMessage: true);
        _manageCharacterUpdateTimer();
      },
      onError: (err) {
        if (_disposed) return;

        _error = err.toString();
        notifyListeners();
      },
    );
  }

  Future<void> _loadSegmentHistory({bool mergeWithExisting = false}) async {
    if (_character == null) {
      if (!mergeWithExisting) {
        _segmentHistory.segments = [];
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
        return _segmentHistory.isSegmentComplete(segment);
      }).toList();

      if (mergeWithExisting) {
        final mergedByKey = <String, Map<String, dynamic>>{};
        for (final existing in _segmentHistory.segments) {
          mergedByKey[_segmentHistory.segmentIdentity(existing)] = Map<String, dynamic>.from(existing);
        }
        for (final segment in history) {
          final key = _segmentHistory.segmentIdentity(segment);
          final existingSegment = mergedByKey[key];
          final merged = Map<String, dynamic>.from(segment);
          if (existingSegment != null && existingSegment.containsKey('_index')) {
            merged['_index'] = existingSegment['_index'];
          }
          mergedByKey[key] = merged;
        }
        final mergedSegments = mergedByKey.values.toList();
        _segmentHistory.segments = _segmentHistory.assignIndices(mergedSegments);
        _segmentHistory.sortSegmentsChronologically(_segmentHistory.segments);
      } else {
        _segmentHistory.segments = _segmentHistory.assignIndices(history);
      }
      _synchronizeStoryCompletionState();
      notifyListeners();
    } catch (e) {
      debugPrint('GameScreenController: Failed to load segment history: $e');
    }
  }

  void _synchronizeStoryCompletionState() {
    final updated = _segmentHistory.synchronizeStoryCompletionState(_character, _lastStoryDetails);
    if (updated != null) {
      _character = updated;
    }
  }

  Map<String, dynamic>? _buildCompletedStoryState() {
    final completedSegmentsCopy = _segmentHistory.segments.map((segment) => Map<String, dynamic>.from(segment)).toList();
    _segmentHistory.sortSegmentsChronologically(completedSegmentsCopy);

    if (completedSegmentsCopy.isEmpty && _lastStoryDetails == null) {
      return null;
    }

    final storyStateUpdate = <String, dynamic>{};
    if (completedSegmentsCopy.isNotEmpty) {
      storyStateUpdate['CompletedSegments'] = completedSegmentsCopy;
    }
    if (_lastStoryDetails != null) {
      storyStateUpdate['Story'] = Map<String, dynamic>.from(_lastStoryDetails!);
    }
    return storyStateUpdate;
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
          _segmentHistory.addOrUpdateSegment(completedSegment, _lastStoryDetails);
        }

        _segmentHistory.addOrUpdateSegment(nextSegment, _lastStoryDetails);

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
    // Prevent re-entry from concurrent callbacks (polling + character reload)
    if (_handlingStoryCompletion) {
      debugPrint('GameScreenController: Story completion already in progress - skipping duplicate call');
      return;
    }
    _handlingStoryCompletion = true;

    try {
      _runtime.stopPolling();
      ApiMetrics.endSegment();

      if (_storyLifecycleState != StoryLifecycleState.completed) {
        _storyLifecycleState = StoryLifecycleState.completed;
        notifyListeners();
      }

      final activeSegment = finalActiveSegment ?? (_character?.storyState?['ActiveSegment'] as Map<String, dynamic>?);
      final shouldIncludeFinalSegment = activeSegment != null && _segmentHistory.isSegmentComplete(activeSegment);

      try {
        if (shouldIncludeFinalSegment) {
          _segmentHistory.addOrUpdateSegment(activeSegment, _lastStoryDetails);
        }

        if (refreshCharacter) {
          await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate, showLoadingIndicator: false);
        }
      } catch (e) {
        debugPrint('GameScreenController: Error updating state after story completion: $e');
      }

      if (_character != null) {
        _character = _character!.copyWith(
          activeStoryId: null,
          activeSegmentId: null,
          storyState: _buildCompletedStoryState(),
          gameMode: 'None',
        );
      }

      _isLoading = false;
      notifyListeners();

      _manageCharacterUpdateTimer();

      if (showMessage && !_storyCompletionNotified) {
        _storyCompletionNotified = true;
      }
    } finally {
      _handlingStoryCompletion = false;
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
        _character = _character!.copyWith(
          activeStoryId: null,
          activeSegmentId: null,
          storyState: _buildCompletedStoryState(),
          gameMode: 'None',
        );
      }

      _isLoading = false;
      notifyListeners();

      _manageCharacterUpdateTimer();

      if (!_storyCompletionNotified) {
        final storyData = _character?.storyState?['Story'] as Map<String, dynamic>?;
        final segments = _segmentHistory.segments;
        final fallbackStoryTitle = segments.isNotEmpty ? segments.last['StoryTitle'] as String? : null;
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

    _segmentHistory.segments = [];
    _storyCompletionNotified = false;
    _lastStoryDetails = null;
    notifyListeners();

    _manageCharacterUpdateTimer();
  }

  List<Map<String, dynamic>> getCompletedSegments() {
    return _segmentHistory.getCompletedSegments(_character?.activeSegmentID);
  }

  List<Map<String, dynamic>> buildStoryHistoryArchive() {
    return _segmentHistory.buildStoryHistoryArchive(
      _character?.activeSegmentID,
      _character?.storyState,
      _segmentHistory.segments,
    );
  }
}
