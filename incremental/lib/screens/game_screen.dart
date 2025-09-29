import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/character.dart';
import '../models/story.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/notification_service.dart';
import '../services/rate_limiter.dart';
import '../services/story_polling_service.dart';
import '../utils/error_handler.dart';
import '../utils/retry.dart';
import '../widgets/game/character_panel.dart';
import '../widgets/game/inventory_panel.dart';
import '../widgets/game/story_panel.dart';
import '../widgets/shared/breadcrumb.dart';
import '../widgets/shared/error_boundary.dart';
import '../widgets/shared/keyboard_shortcuts.dart';
import '../widgets/shared/responsive_layout.dart';

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

  // Segment history (completion view only)
  List<Map<String, dynamic>> _segmentHistory = const [];
  Map<String, dynamic>? _lastStoryDetails;

  // Panel visibility for mobile/tablet
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  // Track last orchestrated segment to avoid duplicate starts
  String? _orchestratedSegmentId;

  @override
  void initState() {
    super.initState();
    debugPrint('GameScreen: initState called');
    _apiService = ApiService(authService: AuthService.instance);
    _runtime = StoryPollingService(apiService: _apiService);
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
        _character = args;
        _characterInfo = CharacterInfo(name: args.name, id: args.id, dead: args.health <= 0);

        // Extract story details for later use
        final storyData = args.storyState?['Story'] as Map<String, dynamic>?;
        if (storyData != null) {
          _lastStoryDetails = Map<String, dynamic>.from(storyData);
        }

        // No loading state needed - we have complete character data
        if (_isLoading && mounted) {
          setState(() {
            _isLoading = false;
          });
        }

        _startOrchestrationIfNeeded();
      }
    } else if (args is CharacterInfo) {
      // Only update if it's a different character or first load
      if (_characterInfo == null || _characterInfo!.id != args.id) {
        _characterInfo = args;
        _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate).then((_) => _loadSegmentHistory());
      }
    } else if (args != null) {
      // Unexpected argument type provided via navigation; ignoring.
    }
  }

  @override
  void dispose() {
    _runtime.dispose();
    super.dispose();
  }

  Future<void> _loadCharacterData({CharacterLoadRateLimitStrategy strategy = CharacterLoadRateLimitStrategy.automated}) {
    final activeLoad = _activeCharacterLoad;
    if (activeLoad != null) {
      return activeLoad;
    }

    final future = _loadCharacterDataInternal(strategy: strategy);
    _activeCharacterLoad = future;
    future.whenComplete(() {
      if (identical(_activeCharacterLoad, future)) {
        _activeCharacterLoad = null;
      }
    });

    return future;
  }

  Future<void> _loadCharacterDataInternal({required CharacterLoadRateLimitStrategy strategy}) async {
    debugPrint('GameScreen: Loading character data');
    if (_characterInfo == null) return;

    try {
      if (mounted) {
        setState(() {
          _isLoading = true;
          _error = null;
        });
      }

      final character = await retryWithBackoff(() => _executeCharacterLoad(strategy));
      debugPrint('GameScreen: Character loaded: ${character != null ? 'success' : 'null'}');

      if (mounted) {
        setState(() {
          _character = character;
          _isLoading = false;
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
    return _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate);
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

    // Only load history when no active story
    if (_character!.activeStoryID != null) {
      return;
    }

    try {
      final historyResponse = await _apiService.getSegmentHistory(characterId: _character!.id);
      final history = historyResponse.map((segment) => Map<String, dynamic>.from(segment)).where(_isSegmentComplete).toList();
      if (!mounted) return;
      setState(() {
        _segmentHistory = mergeWithExisting ? [..._segmentHistory, ...history] : history;
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

    _character!.storyState ??= {};
    _character!.storyState!['CompletedSegments'] = List<Map<String, dynamic>>.from(_segmentHistory);

    if (_character!.storyState!['Story'] == null && _lastStoryDetails != null) {
      _character!.storyState!['Story'] = Map<String, dynamic>.from(_lastStoryDetails!);
    }
  }

  Future<void> _handleDecisionSelect(String choiceId) async {
    // Prevent double submissions
    if (_isSubmittingDecision) return;

    try {
      if (mounted) {
        setState(() {
          _isSubmittingDecision = true;
          _error = null;
        });
      }

      final response = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.submitDecision,
        () => _apiService.submitDecision(characterId: _character!.id, decision: choiceId),
        throwOnRateLimit: true,
      );

      final previousSegment = _character?.storyState?['ActiveSegment'] as Map<String, dynamic>?;

      // Use the next segment from response instead of reloading
      if (response['NextSegment'] != null) {
        final nextSegment = response['NextSegment'] as Map<String, dynamic>;

        if (mounted) {
          setState(() {
            // Update character's active segment locally
            final updatedStoryState = Map<String, dynamic>.from(_character!.storyState ?? <String, dynamic>{})
              ..['ActiveSegment'] = nextSegment;
            _character = _character!.copyWith(
              activeSegmentId: nextSegment['ActiveSegmentID'] as String?,
              storyState: updatedStoryState,
            );
          });
        }

        // Start orchestration for the new segment
        _startOrchestrationIfNeeded(force: true);
      } else {
        // No next segment means the story has finished
        _runtime.cancel();
        await _handleStoryCompletion(refreshCharacter: true);
      }

      if (mounted && previousSegment != null) {
        // Show notification for decision outcome
        final outcome = previousSegment['Outcome'];
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

  Future<void> _handleRestSegment() async {
    debugPrint('GameScreen: Rest segment triggered');

    try {
      if (mounted) {
        setState(() {
          _isLoading = true;
        });
      }

      // Call the rest endpoint directly
      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.restCharacter,
        () => _apiService.rest(_character!.id),
        throwOnRateLimit: true,
      );

      // Reload character data only (history is loaded on completion screens)
      await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Resting...'), duration: Duration(seconds: 2)));
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

  Future<void> _handleStoryCompletion({bool refreshCharacter = true, bool showMessage = true, Map<String, dynamic>? finalActiveSegment}) async {
    debugPrint('GameScreen: Handling story completion');
    _runtime.cancel();

    try {
      if (refreshCharacter) {
        await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate);
      }

      // Before loading history, optionally include the final segment from status
      final activeSegment = finalActiveSegment ?? (_character?.storyState?['ActiveSegment'] as Map<String, dynamic>?);
      if (activeSegment != null && _isSegmentComplete(activeSegment)) {
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
          }
        }
        debugPrint('GameScreen: Added final segment to history during completion');
      }

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
          _character!.storyState = null;
        }
        _lastStoryDetails = null;
      });
    }

    // Reload character to get available stories
    await _loadCharacterData(strategy: CharacterLoadRateLimitStrategy.immediate);
    // Clear segment history after story completion
    if (mounted) {
      setState(() {
        _segmentHistory = [];
        _storyCompletionNotified = false;
        _lastStoryDetails = null;
      });
    }
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
            storyHistoryArchive: const [],
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onRestSegment: _handleRestSegment,
            onReturnToStories: _handleReturnToStories,
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
            storyHistoryArchive: const [],
            isLoading: _isLoading,
            error: _error,
            onRefresh: _refreshCharacterImmediate,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
            onRestSegment: _handleRestSegment,
            onReturnToStories: _handleReturnToStories,
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
          storyHistoryArchive: const [],
          isLoading: _isLoading,
          error: _error,
          onRefresh: _refreshCharacterImmediate,
          onStorySelect: _handleStorySelect,
          onDecisionSelect: _handleDecisionSelect,
          onAbandonStory: _character!.storyState != null ? _handleAbandonStory : null,
          onRestSegment: _handleRestSegment,
          onReturnToStories: _handleReturnToStories,
        );
      case 2:
        return InventoryPanel(character: _character!);
      default:
        return const SizedBox();
    }
  }
}
