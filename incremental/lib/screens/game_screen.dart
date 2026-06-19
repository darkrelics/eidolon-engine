import 'package:eidolon_incremental/controllers/game_screen_controller.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/repositories/character_repository.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/widgets/game/character_panel.dart';
import 'package:eidolon_incremental/widgets/game/inventory_panel.dart';
import 'package:eidolon_incremental/widgets/game/story_panel.dart';
import 'package:eidolon_incremental/widgets/shared/breadcrumb.dart';
import 'package:eidolon_incremental/widgets/shared/error_boundary.dart';
import 'package:eidolon_incremental/widgets/shared/keyboard_shortcuts.dart';
import 'package:eidolon_incremental/widgets/shared/responsive_layout.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class GameScreen extends StatelessWidget {
  const GameScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => GameScreenController(
        apiService: ApiService(authService: AuthService.instance),
        characterRepository: context.read<CharacterRepository>(),
      ),
      child: const _GameScreenView(),
    );
  }
}

class _GameScreenView extends StatefulWidget {
  const _GameScreenView();

  @override
  State<_GameScreenView> createState() => _GameScreenViewState();
}

class _GameScreenViewState extends State<_GameScreenView> {
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final controller = context.read<GameScreenController>();
    final args = ModalRoute.of(context)?.settings.arguments;
    final characterProvider = context.read<CharacterProvider>();

    if (args is Character) {
      controller.initialize(args, null);
    } else if (args is CharacterInfo) {
      controller.initialize(null, args);
    } else {
      controller.initialize(
        null,
        null,
        savedCharacter: characterProvider.character,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<GameScreenController>();
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final deviceType = ResponsiveLayout.getDeviceType(context);

    // Redirect if no character found after initialization
    if (!controller.isLoading &&
        controller.character == null &&
        controller.characterInfo == null &&
        controller.error == null) {
      // Use PostFrameCallback to avoid build-time navigation
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          Navigator.pushReplacementNamed(context, '/character-selection');
        }
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return ErrorBoundary(
      onError: (details) {
        debugPrint('GameScreen: ErrorBoundary caught error in GameScreen');
        debugPrint('GameScreen: Error details: ${details.exception}');
      },
      child: GameKeyboardShortcuts(
        onRefresh: controller.refreshCharacterImmediate,
        onEscape: () {
          Navigator.pushReplacementNamed(context, '/character-selection');
        },
        onTogglePanel: () {
          if (deviceType != DeviceType.desktop) {
            controller.setSelectedPanelIndex(
              (controller.selectedPanelIndex + 1) % 3,
            );
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
                          Navigator.pushReplacementNamed(
                            context,
                            '/character-selection',
                          );
                        },
                      ),
                      if (controller.characterInfo != null)
                        BreadcrumbItem(
                          label: controller.characterInfo!.name,
                          icon: Icons.person,
                        ),
                      if (controller.character?.storyState != null &&
                          controller.character!.storyState!['Story'] != null)
                        BreadcrumbItem(
                          label:
                              controller
                                  .character!
                                  .storyState!['Story']['Title'] ??
                              'Story',
                          icon: Icons.auto_stories,
                        ),
                    ],
                  )
                : Text(controller.characterInfo?.name ?? 'Game'),
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
                onPressed: controller.refreshCharacterImmediate,
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
            child: controller.isLoading && controller.character == null
                ? const Center(child: CircularProgressIndicator())
                : controller.error != null && controller.character == null
                ? _buildErrorWidget(context, controller)
                : controller.character == null
                ? _buildNoCharacterWidget(context)
                : _buildGameInterface(context, controller, deviceType),
          ),
          bottomNavigationBar:
              deviceType == DeviceType.mobile && controller.character != null
              ? BottomNavigationBar(
                  currentIndex: controller.selectedPanelIndex,
                  onTap: controller.setSelectedPanelIndex,
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

  Widget _buildErrorWidget(
    BuildContext context,
    GameScreenController controller,
  ) {
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
              controller.error!,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: controller.refreshCharacterImmediate,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoCharacterWidget(BuildContext context) {
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

  Widget _buildGameInterface(
    BuildContext context,
    GameScreenController controller,
    DeviceType deviceType,
  ) {
    switch (deviceType) {
      case DeviceType.desktop:
        return _buildDesktopLayout(context, controller);
      case DeviceType.tablet:
        return _buildTabletLayout(context, controller);
      case DeviceType.mobile:
        return _buildMobileLayout(context, controller);
    }
  }

  Widget _buildDesktopLayout(
    BuildContext context,
    GameScreenController controller,
  ) {
    return Row(
      children: [
        // Character Panel (Left)
        SizedBox(
          width: 320,
          child: CharacterPanel(
            key: ValueKey('character_panel_${controller.character!.id}'),
            character: controller.character!,
            onRefresh: controller.refreshCharacterImmediate,
          ),
        ),
        // Story Panel (Center)
        Expanded(
          child: StoryPanel(
            key: ValueKey(
              'story_panel_${controller.character!.id}_${controller.character!.activeSegmentID ?? "none"}',
            ),
            character: controller.character!,
            segmentHistory: controller.getCompletedSegments(),
            storyHistoryArchive: controller.buildStoryHistoryArchive(),
            isLoading: controller.isLoading,
            error: controller.error,
            onRefresh: controller.refreshCharacterImmediate,
            onStorySelect: (story) =>
                controller.handleStorySelect(context, story),
            onDecisionSelect: (choice) =>
                controller.handleDecisionSelect(context, choice),
            onAbandonStory: controller.character!.storyState != null
                ? () => _confirmAbandonStory(context, controller)
                : null,
            onReturnToStories: controller.handleReturnToStories,
            isDecisionSubmitting: controller.isSubmittingDecision,
            isStoryConfirmedComplete:
                controller.storyLifecycleState == StoryLifecycleState.completed,
          ),
        ),
        // Inventory Panel (Right)
        SizedBox(
          width: 320,
          child: InventoryPanel(
            key: ValueKey('inventory_panel_${controller.character!.id}'),
            character: controller.character!,
            onRefresh: controller.refreshCharacterImmediate,
          ),
        ),
      ],
    );
  }

  Widget _buildTabletLayout(
    BuildContext context,
    GameScreenController controller,
  ) {
    return Row(
      children: [
        // Character Panel (Collapsible)
        if (controller.selectedPanelIndex == 0)
          SizedBox(
            width: 280,
            child: CharacterPanel(
              key: ValueKey('character_panel_${controller.character!.id}'),
              character: controller.character!,
              onRefresh: controller.refreshCharacterImmediate,
            ),
          ),
        // Story Panel (Center - Always visible)
        Expanded(
          child: StoryPanel(
            key: ValueKey(
              'story_panel_${controller.character!.id}_${controller.character!.activeSegmentID ?? "none"}',
            ),
            character: controller.character!,
            segmentHistory: controller.getCompletedSegments(),
            storyHistoryArchive: controller.buildStoryHistoryArchive(),
            isLoading: controller.isLoading,
            error: controller.error,
            onRefresh: controller.refreshCharacterImmediate,
            onStorySelect: (story) =>
                controller.handleStorySelect(context, story),
            onDecisionSelect: (choice) =>
                controller.handleDecisionSelect(context, choice),
            onAbandonStory: controller.character!.storyState != null
                ? () => _confirmAbandonStory(context, controller)
                : null,
            onReturnToStories: controller.handleReturnToStories,
            isDecisionSubmitting: controller.isSubmittingDecision,
            isStoryConfirmedComplete:
                controller.storyLifecycleState == StoryLifecycleState.completed,
          ),
        ),
        // Inventory Panel (Collapsible)
        if (controller.selectedPanelIndex == 2)
          SizedBox(
            width: 280,
            child: InventoryPanel(
              key: ValueKey('inventory_panel_${controller.character!.id}'),
              character: controller.character!,
              onRefresh: controller.refreshCharacterImmediate,
            ),
          ),
      ],
    );
  }

  Widget _buildMobileLayout(
    BuildContext context,
    GameScreenController controller,
  ) {
    // Show only the selected panel
    switch (controller.selectedPanelIndex) {
      case 0:
        return CharacterPanel(
          key: ValueKey('character_panel_${controller.character!.id}'),
          character: controller.character!,
          onRefresh: controller.refreshCharacterImmediate,
        );
      case 1:
        return StoryPanel(
          key: ValueKey(
            'story_panel_${controller.character!.id}_${controller.character!.activeSegmentID ?? "none"}',
          ),
          character: controller.character!,
          segmentHistory: controller.getCompletedSegments(),
          storyHistoryArchive: controller.buildStoryHistoryArchive(),
          isLoading: controller.isLoading,
          error: controller.error,
          onRefresh: controller.refreshCharacterImmediate,
          onStorySelect: (story) =>
              controller.handleStorySelect(context, story),
          onDecisionSelect: (choice) =>
              controller.handleDecisionSelect(context, choice),
          onAbandonStory: controller.character!.storyState != null
              ? () => _confirmAbandonStory(context, controller)
              : null,
          onReturnToStories: controller.handleReturnToStories,
          isDecisionSubmitting: controller.isSubmittingDecision,
          isStoryConfirmedComplete:
              controller.storyLifecycleState == StoryLifecycleState.completed,
        );
      case 2:
        return InventoryPanel(
          key: ValueKey('inventory_panel_${controller.character!.id}'),
          character: controller.character!,
          onRefresh: controller.refreshCharacterImmediate,
        );
      default:
        return const SizedBox();
    }
  }

  Future<void> _confirmAbandonStory(
    BuildContext context,
    GameScreenController controller,
  ) async {
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

    if (confirmed == true) {
      if (mounted) {
        await controller.handleAbandonStory(
          onAbandon: (message) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(message),
                  duration: const Duration(seconds: 4),
                ),
              );
            }
          },
          onError: (error) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(error),
                  backgroundColor: Theme.of(context).colorScheme.error,
                ),
              );
            }
          },
        );
      }
    }
  }
}
