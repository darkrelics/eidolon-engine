import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/character.dart';
import '../models/story.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/rate_limiter.dart';
import '../services/notification_service.dart';
import '../utils/error_handler.dart';
import '../utils/retry.dart';
import '../widgets/shared/breadcrumb.dart';
import '../widgets/shared/responsive_layout.dart';
import '../widgets/shared/keyboard_shortcuts.dart';
import '../widgets/shared/error_boundary.dart';
import '../widgets/game/character_panel.dart';
import '../widgets/game/inventory_panel.dart';
import '../widgets/game/story_panel.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({super.key});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  late ApiService _apiService;
  final GlobalRateLimiter _rateLimiter = GlobalRateLimiter();
  Character? _character;
  CharacterInfo? _characterInfo;
  bool _isLoading = true;
  String? _error;
  bool _isPolling = false; // Track if polling is active
  
  // Segment history for the current story display
  List<Map<String, dynamic>> _segmentHistory = [];
  
  // Panel visibility for mobile/tablet
  int _selectedPanelIndex = 1; // 0: Character, 1: Story, 2: Inventory

  @override
  void initState() {
    super.initState();
    debugPrint('GameScreen: initState called');
    _apiService = ApiService(authService: AuthService.instance);
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
        // Start polling if needed
        if (_character?.activeSegmentID != null && !_isPolling) {
          _isPolling = true;
          _runStoryPolling();
        }
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
        _loadCharacterData().then((_) => _loadSegmentHistory());
      } else {
        debugPrint('GameScreen: didChangeDependencies called but same CharacterInfo - skipping update');
      }
    } else if (args != null) {
      debugPrint('GameScreen: didChangeDependencies called with unexpected args type: ${args.runtimeType}');
    }
  }

  @override
  void dispose() {
    _isPolling = false; // Stop any polling
    super.dispose();
  }

  Future<void> _loadCharacterData() async {
    debugPrint('GameScreen: Loading character data');
    if (_characterInfo == null) return;

    try {
      setState(() {
        _isLoading = true;
        _error = null;
      });

      // Always use automated rate limiting for character loads
      final character = await retryWithBackoff(
        () => _rateLimiter.limiter.executeAutomated(
          GlobalRateLimiter.getCharacter,
          () => _apiService.getCharacterById(_characterInfo!.id),
        ),
      );
      debugPrint(
        'GameScreen: Character loaded: ${character != null ? 'success' : 'null'}',
      );

      if (mounted) {
        setState(() {
          _character = character;
          _isLoading = false;
          _error = null;
        });
        
        // Start polling if there's an active story
        if (character?.activeSegmentID != null && !_isPolling) {
          _isPolling = true;
          _runStoryPolling();
        }
      }
    } catch (e) {
      debugPrint('GameScreen: ERROR loading character: $e');
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

  /// Simple polling loop following the cadence:
  /// Start story -> 60s -> get segment -> at end -> get character -> repeat
  Future<void> _runStoryPolling() async {
    if (_character?.activeSegmentID == null) {
      _isPolling = false;
      return;
    }
    
    debugPrint('GameScreen: Starting story polling loop');
    
    // Wait 60 seconds for initial processing
    await Future.delayed(const Duration(seconds: 60));
    
    while (_isPolling && _character?.activeSegmentID != null) {
      try {
        // Get segment status
        final status = await retryWithBackoff(
          () => _apiService.getSegmentStatus(
            characterId: _character!.id,
          ),
        );
        
        // Update character's active segment with the status data
        if (mounted && status['ActiveSegmentID'] != null) {
          setState(() {
            if (_character != null && _character!.storyState != null) {
              // Update the active segment with fresh status data
              _character!.storyState!['ActiveSegment'] = status;
            }
          });
        }
        
        // Wait for segment to complete
        final timeRemaining = status['TimeRemaining'] as int? ?? 0;
        if (timeRemaining > 0) {
          await Future.delayed(Duration(seconds: timeRemaining));
        }
        
        // Only reload character if segment is complete or story ended
        final isComplete = status['IsComplete'] as bool? ?? false;
        if (isComplete) {
          // Load fresh character data and segment history
          await Future.wait([
            _loadCharacterData(),
            _loadSegmentHistory(),
          ]);
        }
        
        // If story continues, wait for next segment processing
        if (_character?.activeSegmentID != null) {
          await Future.delayed(const Duration(seconds: 60));
        }
      } catch (e) {
        debugPrint('GameScreen: Error in polling loop: $e');
        // Continue polling after a delay
        await Future.delayed(const Duration(seconds: 5));
      }
    }
    
    debugPrint('GameScreen: Story polling loop ended');
    _isPolling = false;
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
        // Clear segment history when starting a new story
        _segmentHistory = [];
      });

      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.startStory,
        () => _apiService.startStory(
          characterId: _character!.id,
          storyId: story.storyID,
        ),
        throwOnRateLimit: true,
      );

      // Reload character to get the new story state and history
      await Future.wait([
        _loadCharacterData(),
        _loadSegmentHistory(),
      ]);
      
      // Set up segment polling (60 seconds for processing, then at completion)
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
    // This method is being replaced by _runStoryPolling
    // Kept for now to avoid breaking references
    if (_character?.activeSegmentID != null && !_isPolling) {
      _isPolling = true;
      _runStoryPolling();
    }
  }
  
  
  
  Future<void> _loadSegmentHistory() async {
    if (_character == null || _character!.activeStoryID == null) {
      // No active story, clear history
      setState(() {
        _segmentHistory = [];
      });
      return;
    }
    
    try {
      final history = await _apiService.getSegmentHistory(
        characterId: _character!.id,
      );
      
      if (mounted) {
        setState(() {
          _segmentHistory = history;
        });
        debugPrint('GameScreen: Loaded ${history.length} segments from history');
      }
    } catch (e) {
      debugPrint('GameScreen: Failed to load segment history: $e');
      // Keep existing history on error
    }
  }

  Future<void> _handleDecisionSelect(String choiceId) async {
    try {
      setState(() {
        _isLoading = true;
      });

      final response = await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.submitDecision,
        () => _apiService.submitDecision(
          characterId: _character!.id,
          decision: choiceId,
        ),
        throwOnRateLimit: true,
      );

      // Use the next segment from response instead of reloading
      if (response['NextSegment'] != null) {
        final nextSegment = response['NextSegment'] as Map<String, dynamic>;
        
        setState(() {
          // Update character's active segment locally
          _character = _character!.copyWith(
            activeSegmentId: nextSegment['ActiveSegmentID'] as String?,
            storyState: {
              'ActiveSegment': nextSegment,
            },
          );
        });
        
        // Set up polling for the new segment
        _setupSegmentPolling();
      } else {
        // No next segment means story completed - need to reload for available stories
        await Future.wait([
          _loadCharacterData(),
          _loadSegmentHistory(),
        ]);
      }
      
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
      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.restCharacter,
        () => _apiService.rest(_character!.id),
        throwOnRateLimit: true,
      );
      
      // Reload character data and history
      await Future.wait([
        _loadCharacterData(),
        _loadSegmentHistory(),
      ]);
      
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

  Future<void> _handleReturnToStories() async {
    // Clear story state locally and reload to get available stories
    setState(() {
      if (_character != null) {
        _character!.storyState = null;
      }
    });
    
    // Reload character to get available stories
    await Future.wait([
      _loadCharacterData(),
      _loadSegmentHistory(),
    ]);
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

      await _rateLimiter.limiter.executeHumanDriven(
        GlobalRateLimiter.abandonStory,
        () => _apiService.abandonStory(_character!.id),
        throwOnRateLimit: true,
      );

      // Reload character to clear story state and history
      await Future.wait([
        _loadCharacterData(),
        _loadSegmentHistory(),
      ]);
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
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadCharacterData,
            tooltip: 'Refresh',
          ),
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
            segmentHistory: _segmentHistory,
            isLoading: _isLoading,
            error: _error,
            onRefresh: _loadCharacterData,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null
                ? _handleAbandonStory
                : null,
            onRestSegment: _handleRestSegment,
            onReturnToStories: _handleReturnToStories,
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
            segmentHistory: _segmentHistory,
            isLoading: _isLoading,
            error: _error,
            onRefresh: _loadCharacterData,
            onStorySelect: _handleStorySelect,
            onDecisionSelect: _handleDecisionSelect,
            onAbandonStory: _character!.storyState != null
                ? _handleAbandonStory
                : null,
            onRestSegment: _handleRestSegment,
            onReturnToStories: _handleReturnToStories,
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
          segmentHistory: _segmentHistory,
          isLoading: _isLoading,
          error: _error,
          onRefresh: _loadCharacterData,
          onStorySelect: _handleStorySelect,
          onDecisionSelect: _handleDecisionSelect,
          onAbandonStory: _character!.storyState != null
              ? _handleAbandonStory
              : null,
          onRestSegment: _handleRestSegment,
          onReturnToStories: _handleReturnToStories,
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