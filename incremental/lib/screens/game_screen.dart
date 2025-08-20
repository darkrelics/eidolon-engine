import 'dart:async';
import 'package:flutter/material.dart';
import '../models/character.dart';
import '../models/story.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/polling_service.dart';
import '../services/notification_service.dart';
import '../utils/error_handler.dart';
import '../widgets/shared/breadcrumb.dart';
import '../widgets/shared/responsive_layout.dart';
import '../widgets/shared/keyboard_shortcuts.dart';
import '../widgets/shared/error_boundary.dart';
import '../widgets/game/character_panel.dart';
import '../widgets/game/inventory_panel.dart';
import '../widgets/game/story_panel.dart';
import '../providers/theme_provider.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({super.key});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  late ApiService _apiService;
  late PollingManager _pollingManager;
  Character? _character;
  CharacterInfo? _characterInfo;
  bool _isLoading = true;
  String? _error;
  StreamSubscription<void>? _mechanicalPollingSubscription;
  StreamSubscription<void>? _storyPollingSubscription;
  
  // Panel visibility for mobile/tablet
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  @override
  void initState() {
    super.initState();
    debugPrint('GameScreen: initState called');
    _apiService = ApiService(authService: AuthService.instance);
    _pollingManager = PollingManager();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Get character info from route arguments
    final args = ModalRoute.of(context)?.settings.arguments;
    debugPrint('GameScreen: didChangeDependencies called, args type: ${args.runtimeType}');
    
    // Handle both Character and CharacterInfo types
    if (args is Character) {
      // Only update if it's a different character or first load
      if (_character == null || _character!.id != args.id) {
        debugPrint('GameScreen: Got full Character - name: ${args.name}, id: ${args.id}');
        _character = args;
        _characterInfo = CharacterInfo(
          name: args.name,
          id: args.id,
          dead: args.health <= 0,
        );
        // Only call setState if actually changing from loading state
        if (_isLoading) {
          setState(() {
            _isLoading = false;
          });
        }
        _startPollingIfNeeded();
      } else {
        debugPrint('GameScreen: didChangeDependencies called but same character - skipping update');
      }
    } else if (args is CharacterInfo) {
      // Only update if it's a different character or first load
      if (_characterInfo == null || _characterInfo!.id != args.id) {
        debugPrint(
          'GameScreen: Got CharacterInfo - name: ${args.name}, id: ${args.id}',
        );
        _characterInfo = args;
        _loadCharacterData();
      } else {
        debugPrint('GameScreen: didChangeDependencies called but same CharacterInfo - skipping update');
      }
    } else if (args != null) {
      debugPrint('GameScreen: didChangeDependencies called with unexpected args type: ${args.runtimeType}');
    }
  }

  @override
  void dispose() {
    _mechanicalPollingSubscription?.cancel();
    _storyPollingSubscription?.cancel();
    _pollingManager.stopAllPolling();
    super.dispose();
  }

  Future<void> _loadCharacterData({bool silent = false}) async {
    debugPrint('GameScreen: Loading character data (silent: $silent)');
    if (_characterInfo == null) return;

    try {
      if (!silent) {
        setState(() {
          _isLoading = true;
          _error = null;
        });
      }

      final character = await _apiService.getCharacterById(_characterInfo!.id);
      debugPrint(
        'GameScreen: Character loaded: ${character != null ? 'success' : 'null'}',
      );

      if (mounted) {
        setState(() {
          _character = character;
          _isLoading = false;
          _error = null;
        });
        // Reset retry counter on success
        _pollingManager.resetRetries('mechanical_${_characterInfo!.id}');
        _pollingManager.resetRetries('story_${_characterInfo!.id}');
        _startPollingIfNeeded();
        
        // Set up segment polling if there's an active story
        if (character?.storyState != null && character!.storyState!.isNotEmpty) {
          _setupSegmentPolling();
          
          // Immediately poll for segment status to get any existing narrative
          debugPrint('GameScreen: Active segment found, polling for current status');
          () async {
            try {
              final statusResponse = await _apiService.getSegmentStatus(
                characterId: character.id,
              );
              debugPrint('GameScreen: Initial segment status poll completed');
              
              // Check if narrative is available
              if (statusResponse['ProcessingStatus'] == 'processed') {
                debugPrint('GameScreen: Segment narrative is available');
              }
            } catch (e) {
              debugPrint('GameScreen: Error polling initial segment status: $e');
            }
          }();
        }
      }
    } catch (e) {
      debugPrint('GameScreen: ERROR loading character: $e');
      
      // Handle polling errors with retry logic
      if (silent) {
        final shouldRetry = await _pollingManager.handleError(
          'mechanical_${_characterInfo!.id}',
          () => _loadCharacterData(silent: true),
        );
        
        if (!shouldRetry && mounted) {
          // Max retries reached, show error
          setState(() {
            _error = 'Connection lost. Please refresh to reconnect.';
          });
        }
      } else {
        // Non-silent errors are shown immediately
        if (mounted) {
          setState(() {
            _error = ErrorHandler.getUserFriendlyMessage(
              e,
              context: 'loading character',
            );
            _isLoading = false;
          });
        }
      }
    }
  }

  void _startPollingIfNeeded() {
    // Cancel existing subscriptions
    _mechanicalPollingSubscription?.cancel();
    _storyPollingSubscription?.cancel();
    _pollingManager.stopAllPolling();
    
    if (_character == null || _characterInfo == null) return;
    
    // Check if we have an active story with a mechanical segment
    final hasActiveStory = _character!.storyState != null && 
                          _character!.storyState!.isNotEmpty;
    
    if (hasActiveStory) {
      final segmentType = _character!.storyState?['ActiveSegment']?['SegmentType'];
      final processingStatus = _character!.storyState?['ActiveSegment']?['ProcessingStatus'];
      
      if (segmentType == 'mechanical' && processingStatus == 'processing') {
        // Start mechanical segment polling
        _mechanicalPollingSubscription = _pollingManager
            .startMechanicalPolling(_characterInfo!.id)
            .listen((_) => _loadCharacterData(silent: true));
        debugPrint('GameScreen: Started polling for mechanical segment');
      }
    } else {
      // Start general story polling when no active story
      _storyPollingSubscription = _pollingManager
          .startStoryPolling(_characterInfo!.id)
          .listen((_) => _refreshStories());
      debugPrint('GameScreen: Started general story polling');
    }
  }

  Future<void> _refreshStories() async {
    // Only refresh if no active story
    if (_character?.storyState != null && _character!.storyState!.isNotEmpty) {
      return;
    }
    
    try {
      final character = await _apiService.getCharacterById(_characterInfo!.id);
      if (mounted && character != null) {
        setState(() {
          _character = character;
        });
      }
    } catch (e) {
      debugPrint('GameScreen: Error refreshing stories: $e');
    }
  }

  Future<void> _handleStorySelect(StoryMetadata story) async {
    if (!story.available) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            story.cooldownRemaining > 0
                ? 'Story on cooldown'
                : 'Story not available',
          ),
        ),
      );
      return;
    }

    try {
      setState(() {
        _isLoading = true;
      });

      await _apiService.startStory(
        characterId: _character!.id,
        storyId: story.storyID,
      );

      // Reload character to get the new story state
      await _loadCharacterData();
      
      // Set up segment status polling
      // Poll once after 1 minute to get processed narrative
      _setupSegmentPolling();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
        setState(() {
          _isLoading = false;
        });
      }
    }
  }
  
  void _setupSegmentPolling() {
    if (_character == null || _character!.storyState == null) {
      debugPrint('GameScreen: No character or story state, skipping segment polling setup');
      return;
    }
    
    final activeSegment = _character!.storyState?['ActiveSegment'];
    if (activeSegment == null) {
      debugPrint('GameScreen: No active segment, skipping segment polling setup');
      return;
    }
    
    debugPrint('GameScreen: Setting up segment polling for active segment');
    
    final segmentType = activeSegment['SegmentType'] as String?;
    
    // Parse times - they come as ISO 8601 strings
    DateTime? endDateTime;
    DateTime? startDateTime;
    
    try {
      final endTimeStr = activeSegment['EndTime'];
      final startTimeStr = activeSegment['StartTime'];
      
      if (endTimeStr != null) {
        endDateTime = DateTime.parse(endTimeStr);
      }
      if (startTimeStr != null) {
        startDateTime = DateTime.parse(startTimeStr);
      }
    } catch (e) {
      debugPrint('GameScreen: Error parsing segment times: $e');
      return;
    }
    
    if (endDateTime == null || startDateTime == null) return;
    
    final now = DateTime.now();
    
    // Cancel any existing polling timers
    _mechanicalPollingSubscription?.cancel();
    
    // For mechanical segments, poll 60 seconds after the segment started
    if (segmentType == 'mechanical') {
      final timeSinceStart = now.difference(startDateTime);
      final timeUntilOneMinute = const Duration(seconds: 60) - timeSinceStart;
      
      debugPrint('GameScreen: Mechanical segment - time since start: ${timeSinceStart.inSeconds}s');
      debugPrint('GameScreen: Time until 1-minute poll: ${timeUntilOneMinute.inSeconds}s');
      
      // Only set timer if we haven't passed the 1-minute mark yet
      if (timeUntilOneMinute.inSeconds > 0) {
        debugPrint('GameScreen: Setting timer for 1-minute poll in ${timeUntilOneMinute.inSeconds}s');
        Timer(timeUntilOneMinute, () async {
          if (!mounted) return;
        
        try {
          debugPrint('GameScreen: Polling segment status after 1 minute');
          final statusResponse = await _apiService.getSegmentStatus(
            characterId: _character!.id,
          );
          
          // Update UI with narrative if available
          if (statusResponse['ProcessingStatus'] == 'processed' && mounted) {
            // Reload character to get updated segment data with narrative
            await _loadCharacterData(silent: true);
          }
        } catch (e) {
          debugPrint('GameScreen: Error polling segment status: $e');
        }
      });
      } else {
        // We're already past the 1-minute mark, poll immediately
        debugPrint('GameScreen: Already past 1-minute mark, polling immediately');
        () async {
          try {
            final statusResponse = await _apiService.getSegmentStatus(
              characterId: _character!.id,
            );
            
            // Update UI with narrative if available
            if (statusResponse['ProcessingStatus'] == 'processed' && mounted) {
              // Reload character to get updated segment data with narrative
              await _loadCharacterData(silent: true);
            }
          } catch (e) {
            debugPrint('GameScreen: Error polling segment status: $e');
          }
        }();
      }
    }
    
    // Poll at segment completion time for all segment types
    final timeUntilCompletion = endDateTime.difference(now);
    if (timeUntilCompletion.inSeconds > 0) {
      Timer(timeUntilCompletion, () async {
        if (!mounted) return;
        
        try {
          debugPrint('GameScreen: Polling segment status at completion time for $segmentType segment');
          final statusResponse = await _apiService.getSegmentStatus(
            characterId: _character!.id,
          );
          
          // Check if segment is complete
          if (statusResponse['IsComplete'] == true && mounted) {
            // For decision segments that timed out, the backend will use default decision
            if (segmentType == 'decision') {
              debugPrint('GameScreen: Decision segment timed out - default decision will be used');
            }
            
            // Wait a bit for the backend to process the advancement
            // The poller runs every minute and advancement is async
            await Future.delayed(const Duration(seconds: 3));
            
            // Reload character to advance to next segment or complete story
            await _loadCharacterData();
            
            // Set up polling for the new segment if there is one
            if (_character?.storyState != null && _character!.storyState!.isNotEmpty) {
              _setupSegmentPolling();
            }
          }
        } catch (e) {
          debugPrint('GameScreen: Error checking segment completion: $e');
        }
      });
    }
  }

  Future<void> _handleDecisionSelect(String choiceId) async {
    try {
      setState(() {
        _isLoading = true;
      });

      await _apiService.submitDecision(
        characterId: _character!.id,
        decision: choiceId,
      );

      // Reload character to get the next segment
      await _loadCharacterData();
      
      // Set up polling for the new segment
      _setupSegmentPolling();
      
      if (mounted) {
        // Show notification for decision outcome
        final outcome = _character?.storyState?['ActiveSegment']?['Outcome'];
        if (outcome != null) {
          NotificationService.showSegmentComplete(
            context,
            segmentType: 'decision',
            outcome: outcome['Type'],
          );
          
          // Show reward notifications
          final rewards = outcome['Rewards'] as Map<String, dynamic>?;
          if (rewards != null) {
            for (final reward in rewards.entries) {
              await Future.delayed(const Duration(milliseconds: 500));
              if (mounted) {
                NotificationService.showReward(
                  context,
                  type: reward.key,
                  value: reward.value,
                );
              }
            }
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _handleRestSegment() async {
    debugPrint('GameScreen: Rest segment triggered');
    
    try {
      setState(() {
        _isLoading = true;
      });

      // Call the rest endpoint directly
      await _apiService.rest(_character!.id);
      
      // Reload character data
      await _loadCharacterData();
      
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Resting...'),
          duration: Duration(seconds: 2),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _handleAbandonStory() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Abandon Story'),
        content: const Text('Are you sure you want to abandon this story?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Abandon'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      setState(() {
        _isLoading = true;
      });

      await _apiService.abandonStory(_character!.id);

      // Reload character to clear story state
      await _loadCharacterData();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('GameScreen: Building with character: ${_character?.name}, loading: $_isLoading, error: $_error}');
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final deviceType = ResponsiveLayout.getDeviceType(context);

    return ErrorBoundary(
      onError: (details) {
        debugPrint('GameScreen: ErrorBoundary caught error in GameScreen');
        debugPrint('GameScreen: Error details: ${details.exception}');
      },
      child: GameKeyboardShortcuts(
        onRefresh: _loadCharacterData,
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
        title: ResponsiveBreadcrumb(
          items: [
            BreadcrumbItem(
              label: 'Characters',
              icon: Icons.people,
              onTap: () {
                Navigator.pushReplacementNamed(context, '/character-selection');
              },
            ),
            if (_characterInfo != null)
              BreadcrumbItem(
                label: _characterInfo!.name,
                icon: Icons.person,
              ),
            if (_character?.storyState != null && 
                _character!.storyState!['Story'] != null)
              BreadcrumbItem(
                label: _character!.storyState!['Story']['Title'] ?? 'Story',
                icon: Icons.auto_stories,
              ),
          ],
        ),
        leading: IconButton(
          icon: const Icon(Icons.chevron_left),
          onPressed: () {
            Navigator.pushReplacementNamed(context, '/character-selection');
          },
          tooltip: 'Back to Character Selection',
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadCharacterData,
            tooltip: 'Refresh',
          ),
          const ThemeModeSelector(),
          IconButton(
            icon: const Icon(Icons.help_outline),
            onPressed: () => KeyboardShortcutHelp.show(context),
            tooltip: 'Keyboard Shortcuts',
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/account-settings');
            },
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
                BottomNavigationBarItem(
                  icon: Icon(Icons.person),
                  label: 'Character',
                ),
                BottomNavigationBarItem(
                  icon: Icon(Icons.auto_stories),
                  label: 'Story',
                ),
                BottomNavigationBarItem(
                  icon: Icon(Icons.inventory_2),
                  label: 'Inventory',
                ),
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
            Icon(
              Icons.error_outline,
              size: 64,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              'Error loading character',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _loadCharacterData,
              child: const Text('Retry'),
            ),
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
            Icon(
              Icons.person_off,
              size: 64,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 16),
            Text(
              'No Character Selected',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(
              'Please select a character to play',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
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
          child: CharacterPanel(
            character: _character!,
            onRefresh: _loadCharacterData,
          ),
        ),
        // Story Panel (Center)
        Expanded(
          child: StoryPanel(
            character: _character!,
            isLoading: _isLoading,
            error: _error,
            onRefresh: _loadCharacterData,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null
                ? _handleAbandonStory
                : null,
            onRestSegment: _handleRestSegment,
          ),
        ),
        // Inventory Panel (Right)
        SizedBox(
          width: 320,
          child: InventoryPanel(
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
              character: _character!,
              onRefresh: _loadCharacterData,
            ),
          ),
        // Story Panel (Center - Always visible)
        Expanded(
          child: StoryPanel(
            character: _character!,
            isLoading: _isLoading,
            error: _error,
            onRefresh: _loadCharacterData,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null
                ? _handleAbandonStory
                : null,
            onRestSegment: _handleRestSegment,
          ),
        ),
        // Inventory Panel (Collapsible)
        if (_selectedPanelIndex == 2)
          SizedBox(
            width: 280,
            child: InventoryPanel(
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
          character: _character!,
          onRefresh: _loadCharacterData,
        );
      case 1:
        return StoryPanel(
          character: _character!,
          isLoading: _isLoading,
          error: _error,
          onRefresh: _loadCharacterData,
          onStorySelect: _handleStorySelect,
          onDecisionSelect: _handleDecisionSelect,
          onAbandonStory: _character!.storyState != null
              ? _handleAbandonStory
              : null,
          onRestSegment: _handleRestSegment,
        );
      case 2:
        return InventoryPanel(
          character: _character!,
        );
      default:
        return const SizedBox();
    }
  }
}