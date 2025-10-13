import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/services/api_metrics.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/services/notification_service.dart';
import 'package:eidolon_incremental/services/rate_limiter.dart';
import 'package:eidolon_incremental/services/story_polling_service.dart';
import 'package:eidolon_incremental/utils/debounce.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:eidolon_incremental/utils/retry.dart';
import 'package:eidolon_incremental/widgets/game/character_panel.dart';
import 'package:eidolon_incremental/widgets/game/inventory_panel.dart';
import 'package:eidolon_incremental/widgets/game/story_panel.dart';
import 'package:eidolon_incremental/widgets/shared/breadcrumb.dart';
import 'package:eidolon_incremental/widgets/shared/error_boundary.dart';
import 'package:eidolon_incremental/widgets/shared/keyboard_shortcuts.dart';
import 'package:eidolon_incremental/widgets/shared/responsive_layout.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({super.key});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

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

class _GameScreenState extends State<GameScreen> {
  late ApiService _apiService;
  late StoryPollingService _runtime;
  final GlobalRateLimiter _rateLimiter = GlobalRateLimiter();
  Character? _character;
  CharacterInfo? _characterInfo;
  bool _isLoading = true;
  String? _error;
  bool _isSubmittingDecision = false;
  bool _storyCompletionNotified = false;
  Future<void>? _activeCharacterLoad;

  // Story lifecycle tracking to prevent premature completion
  StoryLifecycleState _storyLifecycleState = StoryLifecycleState.none;

  // Character update timer (when not in active story)
  Timer? _characterUpdateTimer;
  int _characterUpdateTimerCount = 0;

  // Segment history (completion view only)
  List<Map<String, dynamic>> _segmentHistory = const [];
  Map<String, dynamic>? _lastStoryDetails;

  // Panel visibility for mobile/tablet
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  // Track last orchestrated segment to avoid duplicate starts
  String? _orchestratedSegmentId;

  // Debouncers for user actions
  late Debouncer _decisionDebouncer;
  late Debouncer _refreshDebouncer;

  // Performance optimization: Cache expensive computations
  List<Map<String, dynamic>>? _cachedCompletedSegments;
  String? _completedSegmentsCacheKey;
  List<Map<String, dynamic>>? _cachedStoryHistory;
  String? _storyHistoryCacheKey;
  final Map<String, DateTime> _timestampCache = {};
  Timer? _statusUpdateDebounce;

  @override
  void initState() {
    super.initState();
    debugPrint('GameScreen: initState called');
    _apiService = ApiService(authService: AuthService.instance);
    _runtime = StoryPollingService(apiService: _apiService);
    _decisionDebouncer = Debouncer(delay: const Duration(milliseconds: 300));
    _refreshDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Get character info from route arguments
    final args = ModalRoute.of(context)?.settings.arguments;
    // Handle both Character and CharacterInfo types
    if (args is Character) {
      // Direct character object with story state (from StorySelectionScreen)
      if (_character == null || _character!.id != args.id) {
        final storyData = args.storyState?['Story'] as Map<String, dynamic>?;
        final completedSegments = args.storyState?['CompletedSegments'] as List<dynamic>?;

        setState(() {
          _resetForNewCharacter();
          _character = args;
          _characterInfo = CharacterInfo(name: args.name, id: args.id, dead: args.health <= 0);
          _isLoading = false;
          _error = null;

          if (storyData != null) {
            _lastStoryDetails = Map<String, dynamic>.from(storyData);
          }

          if (completedSegments != null) {
            _segmentHistory = completedSegments
                .whereType<Map<String, dynamic>>()
                .map((segment) => Map<String, dynamic>.from(segment))
                .where(_isSegmentComplete)
                .toList();
          }

          _synchronizeStoryCompletionState();
        });

        _startOrchestrationIfNeeded();
        _manageCharacterUpdateTimer();
      }
    } else if (args is CharacterInfo) {
      // Only update if it's a different character or first load
      if (_characterInfo == null || _characterInfo!.id != args.id) {
        setState(() {
          _resetForNewCharacter();
          _characterInfo = args;
          _character = null;
          _isLoading = true;
          _error = null;
        });
        _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate)
            .then((_) => _loadSegmentHistory());
      }
    } else {
      // No route arguments (page reload or direct URL navigation)
      // Try to load from CharacterProvider (local storage)
      if (_characterInfo == null && _character == null) {
        debugPrint('GameScreen: No route arguments, checking CharacterProvider');

        // Try to get character from provider
        final characterProvider = context.read<CharacterProvider>();
        final savedCharacter = characterProvider.character;

        if (savedCharacter != null) {
          debugPrint('GameScreen: Found saved character: ${savedCharacter.name}');
          setState(() {
            _resetForNewCharacter();
            _character = savedCharacter;
            _characterInfo = CharacterInfo(
              name: savedCharacter.name,
              id: savedCharacter.id,
              dead: savedCharacter.health <= 0,
            );
            _isLoading = false;
            _error = null;
          });

          _startOrchestrationIfNeeded();
          _manageCharacterUpdateTimer();

          // Refresh character data from server in background
          _loadCharacterData(
            strategy: CharacterLoadRateLimitStrategy.immediate,
            showLoadingIndicator: false,
          );
        } else {
          // No saved character, redirect to selection
          debugPrint('GameScreen: No saved character, redirecting to character selection');
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.pushReplacementNamed(context, '/character-selection');
            }
          });
        }
      }
    }
  }

  @override
  void dispose() {
    _runtime.dispose();
    _decisionDebouncer.dispose();
    _refreshDebouncer.dispose();
    _characterUpdateTimer?.cancel();
    _characterUpdateTimerCount = 0;
    _statusUpdateDebounce?.cancel();
    super.dispose();
  }

  void _resetForNewCharacter() {
    _runtime.stopPolling();
    _characterUpdateTimer?.cancel();
    _characterUpdateTimerCount = 0;
    _orchestratedSegmentId = null;
    _segmentHistory = <Map<String, dynamic>>[];
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
    _timestampCache.clear();
  }

  /// Generate stable identity for segment tracking
  ///
  /// Key hierarchy:
  /// 1. ActiveSegmentID (preferred) - unique per segment execution
  /// 2. SegmentID (fallback) - story definition ID, can repeat across executions
  /// 3. Composite key (last resort) - for segments missing both IDs
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
    final completedAt = _segmentCompletionTimestamp(segment)?.millisecondsSinceEpoch;
    final segmentActivity = segment['SegmentActivity']?.toString().trim();
    final segmentTitle = segment['SegmentTitle']?.toString().trim();
    final prompt = segment['Prompt']?.toString().trim();

    final parts = <String>[
      if (storyInstanceId != null && storyInstanceId.isNotEmpty) storyInstanceId,
      if (storyId != null && storyId.isNotEmpty) storyId,
      if (completedAt != null) completedAt.toString(),
      if (segmentActivity != null && segmentActivity.isNotEmpty) segmentActivity,
      if (segmentTitle != null && segmentTitle.isNotEmpty) segmentTitle,
      if (prompt != null && prompt.isNotEmpty) prompt,
    ];

    if (parts.isEmpty) {
      return 'fallback:${segment.hashCode}';
    }

    return 'composite:${parts.join('|')}';
  }

  DateTime? _segmentCompletionTimestamp(Map<String, dynamic> segment) {
    const timestampFields = ['CompletedAt', 'ProcessedAt', 'EndTime', 'UpdatedAt', 'StartTime', 'CreatedAt'];
    for (final field in timestampFields) {
      final value = segment[field];
      final parsed = _parseSegmentDate(value);
      if (parsed != null) {
        return parsed;
      }
    }
    return null;
  }

  DateTime? _parseSegmentDate(Object? value) {
    if (value == null) return null;
    if (value is DateTime) {
      return value.toUtc();
    }
    if (value is num) {
      final numeric = value.toDouble();
      if (numeric.isNaN) return null;
      if (numeric > 1000000000000) {
        return DateTime.fromMillisecondsSinceEpoch(numeric.round(), isUtc: true);
      }
      return DateTime.fromMillisecondsSinceEpoch((numeric * 1000).round(), isUtc: true);
    }
    if (value is String) {
      final trimmed = value.trim();
      if (trimmed.isEmpty) return null;

      // Check cache first for string timestamps
      if (_timestampCache.containsKey(trimmed)) {
        return _timestampCache[trimmed];
      }

      final numeric = double.tryParse(trimmed);
      if (numeric != null) {
        return _parseSegmentDate(numeric);
      }
      try {
        final parsed = DateTime.parse(trimmed).toUtc();
        _timestampCache[trimmed] = parsed;
        return parsed;
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  void _sortSegmentsChronologically(List<Map<String, dynamic>> segments, {bool newestFirst = false}) {
    segments.sort((a, b) {
      final aTime = _segmentCompletionTimestamp(a);
      final bTime = _segmentCompletionTimestamp(b);

      if (aTime == null && bTime == null) {
        final compareKeys = _segmentIdentity(a).compareTo(_segmentIdentity(b));
        return newestFirst ? -compareKeys : compareKeys;
      }
      if (aTime == null) {
        return 1;
      }
      if (bTime == null) {
        return -1;
      }

      final comparison = aTime.compareTo(bTime);
      if (comparison != 0) {
        return newestFirst ? -comparison : comparison;
      }

      final compareKeys = _segmentIdentity(a).compareTo(_segmentIdentity(b));
      return newestFirst ? -compareKeys : compareKeys;
    });
  }

  /// Manage character update timer based on story state.
  /// Timer runs every 2 minutes when NOT in an active story.
  void _manageCharacterUpdateTimer() {
    final hasActiveStory = _character?.activeSegmentID != null;

    debugPrint('GameScreen: _manageCharacterUpdateTimer called - hasActiveStory=$hasActiveStory, timerExists=${_characterUpdateTimer != null}, characterId=${_character?.id}');

    if (hasActiveStory) {
      // Stop timer if in active story
      if (_characterUpdateTimer != null) {
        debugPrint('GameScreen: Stopping character update timer (in active story)');
        _characterUpdateTimer?.cancel();
        _characterUpdateTimer = null;
        _characterUpdateTimerCount = 0;
      }
    } else {
      // Start timer if not in active story and timer not already running
      if (_characterUpdateTimer == null && _character != null) {
        debugPrint('GameScreen: Starting character update timer (no active story) - first update in 2 minutes');
        _characterUpdateTimerCount = 0;

        // Start periodic timer - fires every 2 minutes
        _characterUpdateTimer = Timer.periodic(const Duration(minutes: 2), (timer) {
          _characterUpdateTimerCount++;
          debugPrint('GameScreen: Auto-refreshing character (2-minute timer tick $_characterUpdateTimerCount/60)');

          if (_characterUpdateTimerCount >= 60) {
            debugPrint('GameScreen: Timer count reached 60, stopping timer');
            timer.cancel();
            _characterUpdateTimer = null;
            _characterUpdateTimerCount = 0;
            return;
          }

          _loadCharacterData(
            strategy: CharacterLoadRateLimitStrategy.automated,
            showLoadingIndicator: false,
          );
        });
      } else if (_characterUpdateTimer != null) {
        debugPrint('GameScreen: Timer already running, not starting new one');
      } else if (_character == null) {
        debugPrint('GameScreen: Cannot start timer - no character loaded');
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

    final future = _loadCharacterDataInternal(
      strategy: strategy,
      showLoadingIndicator: showLoadingIndicator,
    );
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
    debugPrint('GameScreen: Loading character data');
    if (_characterInfo == null) return;

    final previousCharacterId = _character?.id;

    try {
      if (mounted) {
        setState(() {
          _error = null;
          if (showLoadingIndicator) {
            _isLoading = true;
          }
        });
      }

      final character = await retryWithBackoff(() => _executeCharacterLoad(strategy));
      debugPrint('GameScreen: Character loaded: ${character != null ? 'success' : 'null'}');

      if (mounted) {
        setState(() {
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
        });

        _startOrchestrationIfNeeded();
        _manageCharacterUpdateTimer();
      }
    } catch (e) {
      debugPrint('GameScreen: ERROR loading character: $e');
      if (mounted) {
        setState(() {
          _error = ErrorHandler.getUserFriendlyMessage(e, context: 'loading character');
          _isLoading = false;
        });
      }
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

  Future<void> _refreshCharacterImmediate() {
    // Debounce refresh to prevent spam clicking
    if (_refreshDebouncer.isActive) {
      debugPrint('Refresh blocked: debounce cooldown active');
      return Future.value();
    }

    _refreshDebouncer.runImmediate(() {
      // Empty callback - we just want the cooldown timer
    });

    return _loadCharacterData(
      strategy: CharacterLoadRateLimitStrategy.immediate,
      showLoadingIndicator: false,
    );
  }

  // Orchestration is handled by StoryPollingService

  Future<void> _handleStorySelect(StoryMetadata story) async {
    if (!story.available) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(story.cooldownRemaining > 0 ? 'Story on cooldown' : 'Story not available')));
      return;
    }

    try {
      if (mounted) {
        setState(() {
          _isLoading = true;
          // Clear segment history when starting a new story
          _segmentHistory = [];
          _storyCompletionNotified = false;
        });
      }

      final initialSegment = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.startStory,
        () => _apiService.startStory(characterId: _character!.id, storyId: story.storyID),
        throwOnRateLimit: true,
      );

      if (!mounted) return;

      setState(() {
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
        _segmentHistory = [initialSegmentCopy];
        debugPrint('GameScreen: Added initial segment to history: ${_character!.activeSegmentID}');

        _isLoading = false;

        // Set story lifecycle to running
        _storyLifecycleState = StoryLifecycleState.running;
        debugPrint('GameScreen: Story lifecycle state changed to RUNNING - story started: ${story.title}');

        // Start API metrics tracking for this segment
        ApiMetrics.startSegment();
      });

      _startOrchestrationIfNeeded(force: true);
      _manageCharacterUpdateTimer();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
        );
        if (mounted) {
          setState(() {
            _isLoading = false;
          });
        }
      }
    }
  }

  void _startOrchestrationIfNeeded({bool force = false}) {
    if (_character == null) return;
    final segId = _character!.activeSegmentID;
    if (!force && (segId == null || segId == _orchestratedSegmentId)) return;

    _orchestratedSegmentId = segId;

    if (segId == null) return; // No active story

    // Set story lifecycle to running when orchestration starts
    if (_storyLifecycleState != StoryLifecycleState.running) {
      debugPrint('GameScreen: Story lifecycle state changed to RUNNING - orchestration started for segment: $segId');
      setState(() {
        _storyLifecycleState = StoryLifecycleState.running;
      });
    }

    _runtime.startPolling(
      characterId: _character!.id,
      onStatusUpdate: (status) {
        if (!mounted || _character == null) return;

        // Add segment to history for tracking (if not already present)
        final segmentId = status['ActiveSegmentID']?.toString() ?? status['SegmentID']?.toString();
        final segmentKey = _segmentIdentity(status);
        final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);
        final processingStatus = status['ProcessingStatus'];
        final timeRemaining = status['TimeRemaining'];

        debugPrint('GameScreen: Segment update - ID: $segmentId, Status: $processingStatus, Time: ${timeRemaining}s, InHistory: $exists');

        // Check if this is a meaningful update before triggering setState
        final currentActiveSegmentId = _character!.activeSegmentID;
        final newActiveSegmentId = status['ActiveSegmentID']?.toString() ?? status['SegmentID']?.toString();
        final segmentChanged = currentActiveSegmentId != newActiveSegmentId;
        final statusChanged = processingStatus != _character!.storyState?['ActiveSegment']?['ProcessingStatus'];

        if (!exists) {
          final segmentCopy = Map<String, dynamic>.from(status);
          if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
            segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
          }
          _segmentHistory = [..._segmentHistory, segmentCopy];
          debugPrint('GameScreen: Added segment to history (total: ${_segmentHistory.length})');
        } else {
          // Update existing segment in history with latest data
          _segmentHistory = _segmentHistory.map((s) {
            if (_segmentIdentity(s) == segmentKey) {
              final updated = Map<String, dynamic>.from(status);
              if (!updated.containsKey('StoryTitle') && _lastStoryDetails != null) {
                updated['StoryTitle'] = _lastStoryDetails!['Title'];
              }
              return updated;
            }
            return s;
          }).toList();
          debugPrint('GameScreen: Updated existing segment in history');
        }

        // Update character with new segment status
        final storyState = Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{});
        storyState['ActiveSegment'] = status;

        // Preserve story details
        final story = status['Story'] as Map<String, dynamic>?;
        if (story != null) {
          storyState['Story'] = story;
          _lastStoryDetails = Map<String, dynamic>.from(story);
        }

        // Debounce only major changes; always call setState to maintain consistency
        if (segmentChanged || statusChanged || !exists) {
          // Major change - debounce to prevent rapid rebuilds
          _statusUpdateDebounce?.cancel();
          _statusUpdateDebounce = Timer(const Duration(milliseconds: 200), () {
            if (!mounted) return;
            setState(() {
              _character = _character!.copyWith(
                activeSegmentId: newActiveSegmentId,
                storyState: storyState,
              );
              _error = null;
              _invalidateCache();
            });
          });
        } else {
          // Minor update - immediate setState without debounce to prevent state drift
          if (mounted) {
            setState(() {
              _character = _character!.copyWith(
                activeSegmentId: newActiveSegmentId,
                storyState: storyState,
              );
            });
          }
        }
      },
      onCharacterReload: (characterData) {
        if (!mounted) return;

        // Parse character data and update
        try {
          final updated = Character.fromJson(characterData);

          // Detect story completion immediately
          // Check multiple indicators to ensure story is truly complete
          final wasRunning = _storyLifecycleState == StoryLifecycleState.running;
          final hasActiveSegmentField = updated.activeSegmentID != null;
          final hasActiveStoryField = updated.activeStoryID != null;
          final hasActiveSegmentInState = updated.storyState?['ActiveSegment'] != null;
          final hasActiveStoryInState = updated.storyState?['ActiveStory'] != null;

          final storyCompleted = wasRunning &&
                                !hasActiveSegmentField &&
                                !hasActiveStoryField &&
                                !hasActiveSegmentInState &&
                                !hasActiveStoryInState;

          if (wasRunning && (hasActiveSegmentField || hasActiveStoryField || hasActiveSegmentInState || hasActiveStoryInState)) {
            debugPrint('GameScreen: Story still active - activeSegmentID=${updated.activeSegmentID}, '
                      'activeStoryID=${updated.activeStoryID}, '
                      'hasActiveSegmentInState=$hasActiveSegmentInState, '
                      'hasActiveStoryInState=$hasActiveStoryInState');
          }

          // Add new segment to history if present
          // (Segments are tracked in history immediately when encountered)
          final newActiveSegment = updated.storyState?['ActiveSegment'] as Map<String, dynamic>?;
          final newActiveSegmentId = updated.activeSegmentID;

          if (newActiveSegment != null) {
            final segmentKey = _segmentIdentity(newActiveSegment);
            final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);

            if (!exists) {
              final segmentCopy = Map<String, dynamic>.from(newActiveSegment);
              if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
                segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
              }
              _segmentHistory = [..._segmentHistory, segmentCopy];
              debugPrint('GameScreen: Added new segment to history from character reload: ${newActiveSegmentId ?? segmentKey}');
            }
          }

          setState(() {
            _character = updated;
            _error = null;
          });

          debugPrint('GameScreen: Character reloaded at segment boundary');

          // Trigger completion immediately if detected
          if (storyCompleted) {
            debugPrint('GameScreen: Story completion detected in character reload - triggering immediate completion');
            _runtime.stopPolling();

            // Set lifecycle state to completed
            setState(() {
              _storyLifecycleState = StoryLifecycleState.completed;
            });
            debugPrint('GameScreen: Story lifecycle state changed to COMPLETED');

            // Handle completion
            _handleStoryCompletion(refreshCharacter: false, showMessage: true).then((_) {
              _manageCharacterUpdateTimer();
            });
          }
        } catch (e) {
          debugPrint('GameScreen: Error parsing character data: $e');
          setState(() {
            _error = 'Failed to update character';
          });
        }
      },
      onStoryComplete: () async {
        if (!mounted) return;

        debugPrint('GameScreen: Story complete - confirmed by polling service');
        debugPrint('GameScreen: Previous lifecycle state: $_storyLifecycleState');
        debugPrint('GameScreen: Active story ID: ${_character?.activeStoryID}');
        debugPrint('GameScreen: Active segment ID: ${_character?.activeSegmentID}');
        debugPrint('GameScreen: Segment history count: ${_segmentHistory.length}');

        // Skip if already handled completion
        if (_storyLifecycleState == StoryLifecycleState.completed) {
          debugPrint('GameScreen: Story completion already handled, skipping');
          return;
        }

        // Mark story as completed (confirmed by polling service)
        setState(() {
          _storyLifecycleState = StoryLifecycleState.completed;
        });
        debugPrint('GameScreen: Story lifecycle state changed to COMPLETED');

        // Handle completion
        await _handleStoryCompletion(refreshCharacter: true, showMessage: true);
        _manageCharacterUpdateTimer();
      },
      onError: (err) {
        if (!mounted) return;
        setState(() {
          _error = err.toString();
        });
      },
    );
  }

  Future<void> _loadSegmentHistory({bool mergeWithExisting = false}) async {
    if (_character == null) {
      if (mounted && !mergeWithExisting) {
        setState(() {
          _segmentHistory = [];
          _synchronizeStoryCompletionState();
        });
      }
      return;
    }

    // Load history when no active story OR when explicitly merging during completion
    // This allows us to fetch backend history even during the completion transition
    if (_character!.activeStoryID != null && !mergeWithExisting) {
      return;
    }

    try {
      final historyResponse = await _apiService.getSegmentHistory(characterId: _character!.id);

      // Trust backend completion markers, don't apply client-side timer checks to history
      final history = historyResponse.map((segment) => Map<String, dynamic>.from(segment)).where((segment) {
        final completedAt = segment['CompletedAt'];
        if (completedAt is String && completedAt.isNotEmpty) {
          return true;
        }
        if (completedAt is num && completedAt > 0) {
          return true;
        }

        final status = segment['Status']?.toString().toLowerCase();
        if (status == 'completed') {
          return true;
        }

        return _isSegmentComplete(segment);
      }).toList();

      _sortSegmentsChronologically(history);
      if (!mounted) return;
      setState(() {
        if (mergeWithExisting) {
          final mergedByKey = <String, Map<String, dynamic>>{};
          for (final existing in _segmentHistory) {
            mergedByKey[_segmentIdentity(existing)] = Map<String, dynamic>.from(existing);
          }
          for (final segment in history) {
            mergedByKey[_segmentIdentity(segment)] = Map<String, dynamic>.from(segment);
          }
          final mergedSegments = mergedByKey.values.toList();
          _sortSegmentsChronologically(mergedSegments);
          _segmentHistory = mergedSegments;
        } else {
          _segmentHistory = history.map((segment) => Map<String, dynamic>.from(segment)).toList();
        }
        _synchronizeStoryCompletionState();
      });
      debugPrint('GameScreen: Loaded ${history.length} segments from history API');
    } catch (e) {
      debugPrint('GameScreen: Failed to load segment history: $e');
    }
  }

  bool _isSegmentComplete(Map<String, dynamic> segment) {
    // A segment is only complete when BOTH conditions are met:
    // 1. ProcessingStatus == 'processed' (backend has generated results)
    // 2. Timer has expired (EndTime has passed)

    final completedAt = segment['CompletedAt'];
    if (completedAt is String && completedAt.isNotEmpty) {
      return true;
    }
    if (completedAt is num && completedAt > 0) {
      return true;
    }

    final status = segment['Status']?.toString().toLowerCase();
    if (status == 'completed') {
      return true;
    }

    // Check processing status AND timer expiration
    final processingStatus = segment['ProcessingStatus']?.toString().toLowerCase();
    if (processingStatus == 'processed') {
      // Processed, but need to check if timer expired
      final endTimeStr = segment['EndTime']?.toString();
      if (endTimeStr != null && endTimeStr.isNotEmpty) {
        try {
          final endTime = DateTime.parse(endTimeStr).toUtc();
          final now = DateTime.now().toUtc();
          final timerExpired = now.isAfter(endTime) || now.isAtSameMomentAs(endTime);
          debugPrint('GameScreen: _isSegmentComplete check - processed=true, timerExpired=$timerExpired (now=$now, end=$endTime)');
          return timerExpired;
        } catch (e) {
          debugPrint('GameScreen: Error parsing EndTime: $e');
        }
      }

      // If no EndTime or can't parse, check TimeRemaining
      final timeRemaining = segment['TimeRemaining'];
      if (timeRemaining is num) {
        final expired = timeRemaining <= 0;
        debugPrint('GameScreen: _isSegmentComplete check - processed=true, timeRemaining=$timeRemaining, expired=$expired');
        return expired;
      }

      // Processed but can't determine timer status - assume not complete yet
      debugPrint('GameScreen: _isSegmentComplete - processed=true but no timer info, assuming not complete');
      return false;
    }

    // Check if this is the final segment of a completed story
    final storyComplete = segment['StoryComplete'];
    if (storyComplete == true) {
      return true;
    }

    return false;
  }

  void _synchronizeStoryCompletionState() {
    if (_character == null || _segmentHistory.isEmpty) {
      return;
    }

    if (_character!.activeSegmentID != null) {
      return;
    }

    // Use immutable update pattern instead of direct mutation
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

  Future<void> _handleDecisionSelect(String choiceId) async {
    // Multi-layer protection against double submissions:
    // 1. Atomic flag check-and-set (prevents race conditions)
    // 2. Debouncer (ignores rapid clicks within 300ms)
    // 3. Rate limiter (15s cooldown between submissions)
    // 4. Backend conditional update (ultimate protection)

    if (_isSubmittingDecision) {
      debugPrint('Decision submission blocked: already processing');
      return;
    }

    // Check debouncer cooldown
    if (_decisionDebouncer.isActive) {
      debugPrint('Decision submission blocked: debounce cooldown active');
      return;
    }

    // Set flag IMMEDIATELY before any async operations to prevent race condition
    // Must use setState to update UI and disable buttons
    if (mounted) {
      setState(() {
        _isSubmittingDecision = true;
        _error = null;
      });
    }

    // Start debounce cooldown
    _decisionDebouncer.runImmediate(() {
      // Empty callback - we just want the cooldown timer
    });

    try {
      final response = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.submitDecision,
        () => _apiService.submitDecision(characterId: _character!.id, decision: choiceId),
        throwOnRateLimit: true,
      );

      // Use the completed segment from response (includes narrative ClientEvents)
      final completedSegment = response['CompletedSegment'] as Map<String, dynamic>?;

      // Use the next segment from response instead of reloading
      if (response['NextSegment'] != null) {
        final nextSegment = response['NextSegment'] as Map<String, dynamic>;

        // Add the completed decision segment to history with its narrative
        // Backend provides this with ClientEvents already generated
        if (completedSegment != null) {
          final segmentCopy = Map<String, dynamic>.from(completedSegment);

          // Add story title for display
          if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
            segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
          }

          // Add to history if not already present, otherwise refresh data (to capture narrative)
          final segmentKey = _segmentIdentity(segmentCopy);
          final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);

          if (!exists) {
            _segmentHistory = [..._segmentHistory, segmentCopy];
            debugPrint('GameScreen: Added completed decision segment to history with narrative: ${segmentCopy['SegmentID'] ?? segmentCopy['ActiveSegmentID'] ?? segmentKey}');
          } else {
            _segmentHistory = _segmentHistory.map((s) => _segmentIdentity(s) == segmentKey ? segmentCopy : s).toList();
          }
        }

        // Add next segment to history for tracking
        final nextSegmentCopy = Map<String, dynamic>.from(nextSegment);
        if (!nextSegmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
          nextSegmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
        }

        final nextKey = _segmentIdentity(nextSegmentCopy);
        final nextExists = _segmentHistory.any((s) => _segmentIdentity(s) == nextKey);

        if (!nextExists) {
          _segmentHistory = [..._segmentHistory, nextSegmentCopy];
          debugPrint('GameScreen: Added next segment to history after decision: ${nextSegmentCopy['SegmentID'] ?? nextSegmentCopy['ActiveSegmentID'] ?? nextKey}');
        } else {
          _segmentHistory =
              _segmentHistory.map((s) => _segmentIdentity(s) == nextKey ? nextSegmentCopy : s).toList();
        }

        if (mounted) {
          setState(() {
            // Update character's active segment locally
            final updatedStoryState =
                Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{})
                  ..['ActiveSegment'] = nextSegment;

            final dynamic nextSegmentIdValue =
                nextSegment['ActiveSegmentID'] ?? nextSegment['SegmentID'];
            final String? nextSegmentId = nextSegmentIdValue?.toString();

            _character = _character!.copyWith(
              activeSegmentId: nextSegmentId,
              storyState: updatedStoryState,
            );
          });
        }

        // Start orchestration for the new segment
        _startOrchestrationIfNeeded(force: true);
        _manageCharacterUpdateTimer();
      } else {
        // No next segment means the story has finished
        _runtime.stopPolling();
        await _handleStoryCompletion(refreshCharacter: true);
      }

      if (mounted && completedSegment != null) {
        // Show notification for decision outcome
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
              if (mounted) {
                NotificationService.showReward(context, type: reward.key, value: reward.value);
              }
            }
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
        );
        setState(() {
          _error = ErrorHandler.getUserFriendlyMessage(e);
        });
      }
    } finally {
      // Always reset submission flag
      if (mounted) {
        setState(() {
          _isSubmittingDecision = false;
        });
      }
    }
  }


  Future<void> _handleStoryCompletion({bool refreshCharacter = true, bool showMessage = true, Map<String, dynamic>? finalActiveSegment}) async {
    debugPrint('GameScreen: Handling story completion (refreshCharacter=$refreshCharacter, showMessage=$showMessage)');
    debugPrint('GameScreen: Current lifecycle state: $_storyLifecycleState');
    _runtime.stopPolling();

    // End API metrics tracking and print segment summary
    ApiMetrics.endSegment();

    // Ensure lifecycle state is set to completed
    if (_storyLifecycleState != StoryLifecycleState.completed) {
      debugPrint('GameScreen: Setting lifecycle state to COMPLETED (was $_storyLifecycleState)');
      setState(() {
        _storyLifecycleState = StoryLifecycleState.completed;
      });
    }

    // Capture the final segment BEFORE reloading character
    // This ensures we have the complete segment data even if backend clears it
    final activeSegment = finalActiveSegment ?? (_character?.storyState?['ActiveSegment'] as Map<String, dynamic>?);
    final shouldIncludeFinalSegment = activeSegment != null && _isSegmentComplete(activeSegment);

    try {
      // Add final segment to local history before any reloads
      // shouldIncludeFinalSegment already ensures activeSegment is non-null
      if (shouldIncludeFinalSegment) {
        final copy = Map<String, dynamic>.from(activeSegment);
        if (!copy.containsKey('StoryTitle') && _lastStoryDetails != null && _lastStoryDetails!['Title'] is String) {
          copy['StoryTitle'] = _lastStoryDetails!['Title'];
        }

        final segmentKey = _segmentIdentity(copy);
        final exists = _segmentHistory.any((s) => _segmentIdentity(s) == segmentKey);
        if (!exists) {
          _segmentHistory = [..._segmentHistory, copy];
          debugPrint('GameScreen: Added final segment to local history before reload');
        } else {
          _segmentHistory = _segmentHistory.map((s) => _segmentIdentity(s) == segmentKey ? copy : s).toList();
        }
      }

      // Now reload character - this will clear ActiveStoryID/ActiveSegmentID
      if (refreshCharacter) {
        await _loadCharacterData(
          strategy: CharacterLoadRateLimitStrategy.immediate,
          showLoadingIndicator: false,
        );
      }

      // Fetch backend history and merge with our local history
      // The updated _loadSegmentHistory allows this even during transition
      await _loadSegmentHistory(mergeWithExisting: true);
    } catch (e) {
      debugPrint('GameScreen: Error updating state after story completion: $e');
    }

    if (!mounted) return;

    setState(() {
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
    });

    _manageCharacterUpdateTimer();

    if (showMessage && !_storyCompletionNotified) {
      final storyData = _character?.storyState?['Story'] as Map<String, dynamic>?;
      final fallbackStoryTitle = _segmentHistory.isNotEmpty ? _segmentHistory.last['StoryTitle'] as String? : null;
      final storyTitle = storyData?['Title'] ?? fallbackStoryTitle ?? 'Story';

      debugPrint('GameScreen: Showing completion notification for: $storyTitle');
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$storyTitle complete'), duration: const Duration(seconds: 4)));

      _storyCompletionNotified = true;
    }

    debugPrint('GameScreen: Story completion handling finished - lifecycle: $_storyLifecycleState, segments: ${_segmentHistory.length}');
  }

  Future<void> _handleStoryAbandonment() async {
    debugPrint('GameScreen: Handling story abandonment');
    _runtime.stopPolling();

    try {
      // Reload character to clear story state and history
      await Future.wait([_loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate), _loadSegmentHistory()]);
    } catch (e) {
      debugPrint('GameScreen: Error updating state after story abandonment: $e');
    }

    if (!mounted) return;

    setState(() {
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
    });

    _manageCharacterUpdateTimer();

    if (!_storyCompletionNotified) {
      final storyData = _character?.storyState?['Story'] as Map<String, dynamic>?;
      final fallbackStoryTitle = _segmentHistory.isNotEmpty ? _segmentHistory.last['StoryTitle'] as String? : null;
      final storyTitle = storyData?['Title'] ?? fallbackStoryTitle ?? 'Story';

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$storyTitle abandoned'), duration: const Duration(seconds: 4)));

      _storyCompletionNotified = true;
    }
  }

  Future<void> _handleReturnToStories() async {
    debugPrint('GameScreen: Returning to stories - previous lifecycle: $_storyLifecycleState');
    // Clear story state locally and reload to get available stories
    _runtime.stopPolling();
    if (mounted) {
      setState(() {
        if (_character != null) {
          _character = _character!.copyWith(storyState: null, gameMode: 'None');
        }
        _lastStoryDetails = null;
        _storyLifecycleState = StoryLifecycleState.none;
      });
      debugPrint('GameScreen: Story lifecycle state changed to NONE');
    }

    // Reload character to get available stories
    await _loadCharacterData(
      strategy: CharacterLoadRateLimitStrategy.immediate,
      showLoadingIndicator: false,
    );
    // Clear segment history after story completion
    if (mounted) {
      setState(() {
        _segmentHistory = [];
        _storyCompletionNotified = false;
        _lastStoryDetails = null;
      });
    }
    _manageCharacterUpdateTimer();
  }

  Future<void> _handleAbandonStory() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Abandon Story'),
        content: const Text('Are you sure you want to abandon this story?'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            child: const Text('Abandon'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      if (mounted) {
        setState(() {
          _isLoading = true;
        });
      }

      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.abandonStory,
        () => _apiService.abandonStory(_character!.id),
        throwOnRateLimit: true,
      );

      // Stop runtime to prevent duplicate completion detection
      _runtime.stopPolling();

      // Handle abandonment with specific messaging
      await _handleStoryAbandonment();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
        );
        if (mounted) {
          setState(() {
            _isLoading = false;
          });
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Temporarily remove debug print to reduce noise
    // debugPrint('GameScreen: Building with character: ${_character?.name}, loading: $_isLoading, error: $_error}');
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final deviceType = ResponsiveLayout.getDeviceType(context);

    return ErrorBoundary(
      onError: (details) {
        debugPrint('GameScreen: ErrorBoundary caught error in GameScreen');
        debugPrint('GameScreen: Error details: ${details.exception}');
      },
      child: GameKeyboardShortcuts(
        onRefresh: _refreshCharacterImmediate,
        onEscape: () {
          Navigator.pushReplacementNamed(context, '/character-selection');
        },
        onTogglePanel: () {
          if (deviceType != DeviceType.desktop) {
            setState(() {
              _selectedPanelIndex = (_selectedPanelIndex + 1) % 3;
            });
          }
        },
        child: Scaffold(
          backgroundColor: colorScheme.surface,
          appBar: AppBar(
            title: deviceType == DeviceType.desktop
                ? ResponsiveBreadcrumb(
                    items: [
                      BreadcrumbItem(
                        label: 'Characters',
                        icon: Icons.people,
                        onTap: () {
                          Navigator.pushReplacementNamed(context, '/character-selection');
                        },
                      ),
                      if (_characterInfo != null) BreadcrumbItem(label: _characterInfo!.name, icon: Icons.person),
                      if (_character?.storyState != null && _character!.storyState!['Story'] != null)
                        BreadcrumbItem(label: _character!.storyState!['Story']['Title'] ?? 'Story', icon: Icons.auto_stories),
                    ],
                  )
                : Text(_characterInfo?.name ?? 'Game'),
            leading: IconButton(
              icon: const Icon(Icons.chevron_left),
              onPressed: () {
                Navigator.pushReplacementNamed(context, '/character-selection');
              },
              tooltip: 'Back to Character Selection',
            ),
            actions: [
              IconButton(icon: const Icon(Icons.refresh), onPressed: _refreshCharacterImmediate, tooltip: 'Refresh'),
              IconButton(
                icon: const Icon(Icons.settings),
                onPressed: () {
                  Navigator.pushNamed(context, '/account-settings');
                },
                tooltip: 'Settings',
              ),
              IconButton(
                icon: const Icon(Icons.logout),
                onPressed: () async {
                  final authProvider = context.read<AuthProvider>();
                  final navigator = Navigator.of(context);
                  await authProvider.signOut();
                  navigator.pushReplacementNamed('/login');
                },
                tooltip: 'Sign Out',
              ),
            ],
          ),
          body: SafeArea(
            child: _isLoading && _character == null
                ? const Center(child: CircularProgressIndicator())
                : _error != null && _character == null
                ? _buildErrorWidget()
                : _character == null
                ? _buildNoCharacterWidget()
                : _buildGameInterface(deviceType),
          ),
          bottomNavigationBar: deviceType == DeviceType.mobile && _character != null
              ? BottomNavigationBar(
                  currentIndex: _selectedPanelIndex,
                  onTap: (index) {
                    setState(() {
                      _selectedPanelIndex = index;
                    });
                  },
                  items: const [
                    BottomNavigationBarItem(icon: Icon(Icons.person), label: 'Character'),
                    BottomNavigationBarItem(icon: Icon(Icons.auto_stories), label: 'Story'),
                    BottomNavigationBarItem(icon: Icon(Icons.inventory_2), label: 'Inventory'),
                  ],
                )
              : null,
        ),
      ),
    );
  }

  Widget _buildErrorWidget() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 64, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 16),
            Text(
              'Error loading character',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(onPressed: _refreshCharacterImmediate, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }

  Widget _buildNoCharacterWidget() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.person_off, size: 64, color: Theme.of(context).colorScheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text('No Character Selected', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Text('Please select a character to play', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () {
                Navigator.pushReplacementNamed(context, '/character-selection');
              },
              child: const Text('Select Character'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGameInterface(DeviceType deviceType) {
    switch (deviceType) {
      case DeviceType.desktop:
        return _buildDesktopLayout();
      case DeviceType.tablet:
        return _buildTabletLayout();
      case DeviceType.mobile:
        return _buildMobileLayout();
    }
  }

  /// Get segments that are completed (not currently active)
  /// Segments are tracked in history immediately, but only displayed as "completed"
  /// when they're no longer the active segment
  List<Map<String, dynamic>> _getCompletedSegments() {
    // Cache key based on active segment and history length
    final activeSegmentId = _character?.activeSegmentID;
    final cacheKey = '${activeSegmentId ?? 'none'}_${_segmentHistory.length}_${_segmentHistory.hashCode}';

    // Return cached result if still valid
    if (_completedSegmentsCacheKey == cacheKey && _cachedCompletedSegments != null) {
      return _cachedCompletedSegments!;
    }

    final completed = _segmentHistory.where((segment) {
      // Check ActiveSegmentID first to match character.activeSegmentID (unique execution ID)
      // SegmentID is the story definition ID and can repeat across multiple executions
      final segmentActiveId = segment['ActiveSegmentID']?.toString() ?? segment['SegmentID']?.toString();
      // Only show as completed if it's NOT the current active segment
      final isComplete = segmentActiveId != activeSegmentId && _isSegmentComplete(segment);

      if (!isComplete && segmentActiveId == activeSegmentId) {
        debugPrint('GameScreen: Filtering out active segment from completed list: $segmentActiveId');
      }

      return isComplete;
    }).toList();

    _sortSegmentsChronologically(completed, newestFirst: true);

    if (completed.length != _segmentHistory.length) {
      debugPrint('GameScreen: Completed segments: ${completed.length}/${_segmentHistory.length} (active: $activeSegmentId)');
    }

    // Cache the result
    _completedSegmentsCacheKey = cacheKey;
    _cachedCompletedSegments = completed;

    return completed;
  }

  List<Map<String, dynamic>> _buildStoryHistoryArchive() {
    // Cache key based on active segment and history
    final activeSegmentId = _character?.activeSegmentID;
    final stateSegmentsHash = _character?.storyState?['CompletedSegments']?.hashCode ?? 0;
    final cacheKey = '${activeSegmentId ?? 'none'}_${_segmentHistory.length}_${_segmentHistory.hashCode}_$stateSegmentsHash';

    // Return cached result if still valid
    if (_storyHistoryCacheKey == cacheKey && _cachedStoryHistory != null) {
      return _cachedStoryHistory!;
    }

    final Map<String, Map<String, dynamic>> deduped = {};

    void addSegments(Iterable<Map<String, dynamic>> segments) {
      for (final segment in segments) {
        final copy = Map<String, dynamic>.from(segment);
        // Check ActiveSegmentID first to match character.activeSegmentID (unique execution ID)
        // SegmentID is the story definition ID and can repeat across multiple executions
        final segmentActiveId =
            copy['ActiveSegmentID']?.toString() ?? copy['SegmentID']?.toString();
        final key = _segmentIdentity(copy);

        // Only add if it's NOT the current active segment (completed mode only)
        final isActiveSegment = activeSegmentId != null && segmentActiveId == activeSegmentId;
        if (!isActiveSegment) {
          deduped[key] = copy;
        }
      }
    }

    final completedSegmentsDynamic =
        _character?.storyState?['CompletedSegments'] as List<dynamic>?;
    if (completedSegmentsDynamic != null) {
      final completedSegments = completedSegmentsDynamic
          .whereType<Map<String, dynamic>>()
          .where(_isSegmentComplete)
          .map((segment) => Map<String, dynamic>.from(segment));
      addSegments(completedSegments);
    }

    if (_segmentHistory.isNotEmpty) {
      final historyCopies = _segmentHistory
          .where(_isSegmentComplete)
          .map((segment) => Map<String, dynamic>.from(segment));
      addSegments(historyCopies);
    }

    final segments = deduped.values.toList();

    // Sort by CompletedAt timestamp to ensure correct order
    segments.sort((a, b) {
      final aCompleted = a['CompletedAt'];
      final bCompleted = b['CompletedAt'];

      // Parse timestamps using cached parser
      DateTime? aTime;
      DateTime? bTime;

      if (aCompleted is String && aCompleted.isNotEmpty) {
        aTime = _parseSegmentDate(aCompleted);
      } else if (aCompleted is num) {
        aTime = DateTime.fromMillisecondsSinceEpoch((aCompleted * 1000).toInt());
      }

      if (bCompleted is String && bCompleted.isNotEmpty) {
        bTime = _parseSegmentDate(bCompleted);
      } else if (bCompleted is num) {
        bTime = DateTime.fromMillisecondsSinceEpoch((bCompleted * 1000).toInt());
      }

      if (aTime == null && bTime == null) return 0;
      if (aTime == null) return 1;
      if (bTime == null) return -1;

      return aTime.compareTo(bTime);
    });

    // Cache the result
    _storyHistoryCacheKey = cacheKey;
    _cachedStoryHistory = segments;

    return segments;
  }

  Widget _buildDesktopLayout() {
    return Row(
      children: [
        // Character Panel (Left)
        SizedBox(
          width: 320,
          child: CharacterPanel(
            key: ValueKey('character_panel_${_character!.id}'),
            character: _character!,
            onRefresh: _refreshCharacterImmediate,
          ),
        ),
        // Story Panel (Center)
        Expanded(
          child: StoryPanel(
            key: ValueKey('story_panel_${_character!.id}_${_character!.activeSegmentID ?? "none"}'),
            character: _character!,
            segmentHistory: _getCompletedSegments(),
            storyHistoryArchive: _buildStoryHistoryArchive(),
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onReturnToStories: _handleReturnToStories,
            isDecisionSubmitting: _isSubmittingDecision,
            isStoryConfirmedComplete: _storyLifecycleState == StoryLifecycleState.completed,
          ),
        ),
        // Inventory Panel (Right)
        SizedBox(
          width: 320,
          child: InventoryPanel(
            key: ValueKey('inventory_panel_${_character!.id}'),
            character: _character!,
          ),
        ),
      ],
    );
  }

  Widget _buildTabletLayout() {
    return Row(
      children: [
        // Character Panel (Collapsible)
        if (_selectedPanelIndex == 0)
          SizedBox(
            width: 280,
            child: CharacterPanel(
              key: ValueKey('character_panel_${_character!.id}'),
              character: _character!,
              onRefresh: _refreshCharacterImmediate,
            ),
          ),
        // Story Panel (Center - Always visible)
        Expanded(
          child: StoryPanel(
            key: ValueKey('story_panel_${_character!.id}_${_character!.activeSegmentID ?? "none"}'),
            character: _character!,
            segmentHistory: _getCompletedSegments(),
            storyHistoryArchive: _buildStoryHistoryArchive(),
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onReturnToStories: _handleReturnToStories,
            isDecisionSubmitting: _isSubmittingDecision,
            isStoryConfirmedComplete: _storyLifecycleState == StoryLifecycleState.completed,
          ),
        ),
        // Inventory Panel (Collapsible)
        if (_selectedPanelIndex == 2)
          SizedBox(
            width: 280,
            child: InventoryPanel(
              key: ValueKey('inventory_panel_${_character!.id}'),
              character: _character!,
            ),
          ),
      ],
    );
  }

  Widget _buildMobileLayout() {
    // Show only the selected panel
    switch (_selectedPanelIndex) {
      case 0:
        return CharacterPanel(
          key: ValueKey('character_panel_${_character!.id}'),
          character: _character!,
          onRefresh: _refreshCharacterImmediate,
        );
      case 1:
        return StoryPanel(
          key: ValueKey('story_panel_${_character!.id}_${_character!.activeSegmentID ?? "none"}'),
          character: _character!,
          segmentHistory: _getCompletedSegments(),
          storyHistoryArchive: _buildStoryHistoryArchive(),
          isLoading: _isLoading,
          error: _error,
          onRefresh: _refreshCharacterImmediate,
          onStorySelect: _handleStorySelect,
          onDecisionSelect: _handleDecisionSelect,
          onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
          onReturnToStories: _handleReturnToStories,
          isDecisionSubmitting: _isSubmittingDecision,
          isStoryConfirmedComplete: _storyLifecycleState == StoryLifecycleState.completed,
        );
      case 2:
        return InventoryPanel(
          key: ValueKey('inventory_panel_${_character!.id}'),
          character: _character!,
        );
      default:
        return const SizedBox();
    }
  }
}
