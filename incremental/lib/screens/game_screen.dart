import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
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

  // Character update timer (when not in active story)
  Timer? _characterUpdateTimer;

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
    } else if (args != null) {
      // Unexpected argument type provided via navigation; ignoring.
    }
  }

  @override
  void dispose() {
    _runtime.dispose();
    _decisionDebouncer.dispose();
    _refreshDebouncer.dispose();
    _characterUpdateTimer?.cancel();
    super.dispose();
  }

  void _resetForNewCharacter() {
    _runtime.cancel();
    _characterUpdateTimer?.cancel();
    _orchestratedSegmentId = null;
    _segmentHistory = <Map<String, dynamic>>[];
    _lastStoryDetails = null;
    _storyCompletionNotified = false;
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
      }
    } else {
      // Start timer if not in active story and timer not already running
      if (_characterUpdateTimer == null && _character != null) {
        debugPrint('GameScreen: Starting character update timer (no active story) - first update in 2 minutes');

        // Start periodic timer - fires every 2 minutes
        _characterUpdateTimer = Timer.periodic(const Duration(minutes: 2), (timer) {
          debugPrint('GameScreen: Auto-refreshing character (2-minute timer tick)');
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
        );

        _lastStoryDetails = Map<String, dynamic>.from(newStoryState['Story'] as Map<String, dynamic>);
        _isLoading = false;
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

    _runtime.start(
      character: _character!,
      onCharacterReloaded: (updated) {
        if (!mounted) return;

        // Before updating character, capture the completed segment if transitioning
        final oldActiveSegment = _character?.storyState?['ActiveSegment'] as Map<String, dynamic>?;
        final newActiveSegmentId = updated.activeSegmentID;
        final oldActiveSegmentId = oldActiveSegment?['ActiveSegmentID']?.toString() ?? oldActiveSegment?['SegmentID']?.toString();

        // If we're transitioning to a new segment (not completing the story), save the old one to history
        // Don't add if story is completing (newActiveSegmentId == null) - let _handleStoryCompletion handle it
        if (oldActiveSegment != null &&
            oldActiveSegmentId != null &&
            newActiveSegmentId != null &&
            newActiveSegmentId != oldActiveSegmentId &&
            _isSegmentComplete(oldActiveSegment)) {
          final segmentCopy = Map<String, dynamic>.from(oldActiveSegment);

          // Add story title for display
          if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
            segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
          }

          // Add to history if not already present
          final exists = _segmentHistory.any((s) {
            final id = s['SegmentID']?.toString() ?? s['ActiveSegmentID']?.toString();
            return id == oldActiveSegmentId;
          });

          if (!exists) {
            _segmentHistory = [..._segmentHistory, segmentCopy];
            debugPrint('GameScreen: Added completed segment to history: $oldActiveSegmentId');
          }
        }

        setState(() {
          _character = updated;
          _error = null;
          _isLoading = false;

          // Preserve last story details for completion screen
          final storyData = updated.storyState?['Story'] as Map<String, dynamic>?;
          if (storyData != null) {
            _lastStoryDetails = Map<String, dynamic>.from(storyData);
          }
        });

        // New segment or completed
        _startOrchestrationIfNeeded(force: true);
        _manageCharacterUpdateTimer();
      },
      onStatusUpdated: (status) {
        if (!mounted || _character == null) return;
        final storyState = Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{});
        final active = Map<String, dynamic>.from((storyState['ActiveSegment'] as Map<String, dynamic>?) ?? <String, dynamic>{});
        // Merge minimal status fields so UI can reveal processed results
        for (final entry in status.entries) {
          active[entry.key] = entry.value;
        }
        storyState['ActiveSegment'] = active;
        setState(() {
          _character = _character!.copyWith(storyState: storyState);
        });
      },
      onStoryComplete: (finalStatus) async {
        // Load history and show completion
        await _handleStoryCompletion(refreshCharacter: false, showMessage: true, finalActiveSegment: finalStatus);
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
      final history = historyResponse.map((segment) => Map<String, dynamic>.from(segment)).where(_isSegmentComplete).toList();
      if (!mounted) return;
      setState(() {
        if (mergeWithExisting) {
          // When merging, deduplicate based on segment ID
          final existingIds = _segmentHistory
              .map((s) => s['SegmentID']?.toString() ?? s['ActiveSegmentID']?.toString())
              .where((id) => id != null)
              .toSet();

          final newSegments = history.where((segment) {
            final segId = segment['SegmentID']?.toString() ?? segment['ActiveSegmentID']?.toString();
            return segId != null && !existingIds.contains(segId);
          }).toList();

          _segmentHistory = [..._segmentHistory, ...newSegments];
        } else {
          _segmentHistory = history;
        }
        _synchronizeStoryCompletionState();
      });
      debugPrint('GameScreen: Loaded ${history.length} segments from history API');
    } catch (e) {
      debugPrint('GameScreen: Failed to load segment history: $e');
    }
  }

  bool _isSegmentComplete(Map<String, dynamic> segment) {
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

    final processingStatus = segment['ProcessingStatus']?.toString().toLowerCase();
    if (processingStatus == 'processed') {
      return true;
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

    updatedStoryState['CompletedSegments'] = List<Map<String, dynamic>>.from(_segmentHistory);

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
          final segmentId = completedSegment['ActiveSegmentID']?.toString() ?? completedSegment['SegmentID']?.toString();
          if (segmentId != null) {
            final segmentCopy = Map<String, dynamic>.from(completedSegment);

            // Add story title for display
            if (!segmentCopy.containsKey('StoryTitle') && _lastStoryDetails != null) {
              segmentCopy['StoryTitle'] = _lastStoryDetails!['Title'];
            }

            // Add to history if not already present
            final exists = _segmentHistory.any((s) {
              final id = s['SegmentID']?.toString() ?? s['ActiveSegmentID']?.toString();
              return id == segmentId;
            });

            if (!exists) {
              _segmentHistory = [..._segmentHistory, segmentCopy];
              debugPrint('GameScreen: Added completed decision segment to history with narrative: $segmentId');
            }
          }
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
        _runtime.cancel();
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
    debugPrint('GameScreen: Handling story completion');
    _runtime.cancel();

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
        final segId = copy['SegmentID']?.toString() ?? copy['ActiveSegmentID']?.toString();
        if (segId != null) {
          final exists = _segmentHistory.any((s) {
            final id = s['SegmentID']?.toString() ?? s['ActiveSegmentID']?.toString();
            return id == segId;
          });
          if (!exists) {
            _segmentHistory = [..._segmentHistory, copy];
            debugPrint('GameScreen: Added final segment to local history before reload');
          }
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

        _character = _character!.copyWith(activeStoryId: null, activeSegmentId: null, storyState: storyStateUpdate);
      }

      _isLoading = false;
    });

    _manageCharacterUpdateTimer();

    if (showMessage && !_storyCompletionNotified) {
      final storyData = _character?.storyState?['Story'] as Map<String, dynamic>?;
      final fallbackStoryTitle = _segmentHistory.isNotEmpty ? _segmentHistory.last['StoryTitle'] as String? : null;
      final storyTitle = storyData?['Title'] ?? fallbackStoryTitle ?? 'Story';

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$storyTitle complete'), duration: const Duration(seconds: 4)));

      _storyCompletionNotified = true;
    }
  }

  Future<void> _handleStoryAbandonment() async {
    debugPrint('GameScreen: Handling story abandonment');
    _runtime.cancel();

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

        _character = _character!.copyWith(activeStoryId: null, activeSegmentId: null, storyState: storyStateUpdate);
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
    // Clear story state locally and reload to get available stories
    _runtime.cancel();
    if (mounted) {
      setState(() {
        if (_character != null) {
          _character = _character!.copyWith(storyState: null);
        }
        _lastStoryDetails = null;
      });
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
      _runtime.cancel();

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

  List<Map<String, dynamic>> _buildStoryHistoryArchive() {
    final Map<String, Map<String, dynamic>> deduped = {};

    void addSegments(Iterable<Map<String, dynamic>> segments) {
      for (final segment in segments) {
        final copy = Map<String, dynamic>.from(segment);
        final segmentId =
            copy['SegmentID']?.toString() ?? copy['ActiveSegmentID']?.toString();
        final key = segmentId ?? copy.hashCode.toString();
        deduped[key] = copy;
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

    return deduped.values.toList(growable: false);
  }

  Widget _buildDesktopLayout() {
    return Row(
      children: [
        // Character Panel (Left)
        SizedBox(
          width: 320,
          child: CharacterPanel(character: _character!, onRefresh: _refreshCharacterImmediate),
        ),
        // Story Panel (Center)
        Expanded(
          child: StoryPanel(
            character: _character!,
            segmentHistory: _segmentHistory,
            storyHistoryArchive: _buildStoryHistoryArchive(),
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onReturnToStories: _handleReturnToStories,
            isDecisionSubmitting: _isSubmittingDecision,
          ),
        ),
        // Inventory Panel (Right)
        SizedBox(width: 320, child: InventoryPanel(character: _character!)),
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
            child: CharacterPanel(character: _character!, onRefresh: _refreshCharacterImmediate),
          ),
        // Story Panel (Center - Always visible)
        Expanded(
          child: StoryPanel(
            character: _character!,
            segmentHistory: _segmentHistory,
            storyHistoryArchive: _buildStoryHistoryArchive(),
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onReturnToStories: _handleReturnToStories,
            isDecisionSubmitting: _isSubmittingDecision,
          ),
        ),
        // Inventory Panel (Collapsible)
        if (_selectedPanelIndex == 2) SizedBox(width: 280, child: InventoryPanel(character: _character!)),
      ],
    );
  }

  Widget _buildMobileLayout() {
    // Show only the selected panel
    switch (_selectedPanelIndex) {
      case 0:
        return CharacterPanel(character: _character!, onRefresh: _refreshCharacterImmediate);
      case 1:
        return StoryPanel(
          character: _character!,
          segmentHistory: _segmentHistory,
          storyHistoryArchive: _buildStoryHistoryArchive(),
          isLoading: _isLoading,
          error: _error,
          onRefresh: _refreshCharacterImmediate,
          onStorySelect: _handleStorySelect,
          onDecisionSelect: _handleDecisionSelect,
          onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
          onReturnToStories: _handleReturnToStories,
          isDecisionSubmitting: _isSubmittingDecision,
        );
      case 2:
        return InventoryPanel(character: _character!);
      default:
        return const SizedBox();
    }
  }
}
