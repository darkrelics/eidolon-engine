import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../models/character.dart';
import '../../models/story.dart';
import '../story/active_story_widget.dart';
import '../story/available_stories_widget.dart';
import '../story/story_history_widget.dart';

/// Center panel that displays story content dynamically
class StoryPanel extends StatefulWidget {
  final Character character;
  final bool isLoading;
  final String? error;
  final VoidCallback? onRefresh;
  final Function(StoryMetadata)? onStorySelect;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onRestSegment;

  const StoryPanel({
    super.key,
    required this.character,
    this.isLoading = false,
    this.error,
    this.onRefresh,
    this.onStorySelect,
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onRestSegment,
  });

  @override
  State<StoryPanel> createState() => _StoryPanelState();
}

class _StoryPanelState extends State<StoryPanel> with SingleTickerProviderStateMixin {
  bool _showHistory = false;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    );
    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(StoryPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Trigger animation when story state changes
    if (_hasActiveStory() != _hasActiveStory(oldWidget.character)) {
      _animationController.forward(from: 0);
    }
  }

  bool _hasActiveStory([Character? character]) {
    final char = character ?? widget.character;
    return char.storyState != null && char.storyState!.isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      margin: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: colorScheme.primaryContainer,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.auto_stories,
                  color: colorScheme.onPrimaryContainer,
                ),
                const SizedBox(width: 8),
                Text(
                  _getHeaderTitle(),
                  style: theme.textTheme.titleLarge?.copyWith(
                    color: colorScheme.onPrimaryContainer,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                // History toggle button
                if (!_hasActiveStory() && widget.character.completedStories.isNotEmpty)
                  IconButton(
                    icon: AnimatedRotation(
                      turns: _showHistory ? 0.5 : 0,
                      duration: const Duration(milliseconds: 200),
                      child: Icon(
                        _showHistory ? Icons.library_books : Icons.history,
                        color: colorScheme.onPrimaryContainer,
                      ),
                    ),
                    onPressed: () {
                      setState(() {
                        _showHistory = !_showHistory;
                        _animationController.forward(from: 0);
                      });
                    },
                    tooltip: _showHistory ? 'Show Available Stories' : 'Show History',
                  ),
                if (widget.onRefresh != null)
                  IconButton(
                    icon: Icon(
                      Icons.refresh,
                      color: colorScheme.onPrimaryContainer,
                    ),
                    onPressed: widget.onRefresh,
                    tooltip: 'Refresh',
                  ),
              ],
            ),
          ).animate()
            .fadeIn(duration: 200.ms)
            .slideY(begin: -0.1, end: 0),
          
          // Content
          Expanded(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: _buildContent(),
            ),
          ),
        ],
      ),
    );
  }

  String _getHeaderTitle() {
    if (_hasActiveStory()) {
      final storyTitle = widget.character.storyState?['Story']?['Title'];
      return storyTitle ?? 'Active Story';
    } else if (_showHistory) {
      return 'Story History';
    } else {
      return 'Available Stories';
    }
  }

  Widget _buildContent() {
    // Don't show loading if we already have content
    if (widget.isLoading && !_hasActiveStory() && 
        widget.character.availableStoriesDetails == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(
              'Loading stories...',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ).animate()
          .fadeIn(duration: 300.ms)
          .scale(begin: const Offset(0.8, 0.8), end: const Offset(1, 1)),
      );
    }

    if (widget.error != null) {
      return _buildErrorWidget();
    }

    if (_hasActiveStory()) {
      return _buildActiveStoryWidget();
    }

    if (_showHistory) {
      return _buildHistoryWidget();
    }

    return _buildAvailableStoriesWidget();
  }

  Widget _buildErrorWidget() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: colorScheme.error,
            ).animate()
              .shake(duration: 500.ms)
              .scale(delay: 100.ms),
            const SizedBox(height: 16),
            Text(
              'Error Loading Stories',
              style: theme.textTheme.titleMedium?.copyWith(
                color: colorScheme.error,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              widget.error!,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            if (widget.onRefresh != null) ...[
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: widget.onRefresh,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ).animate()
                .fadeIn(delay: 200.ms)
                .slideY(begin: 0.2, end: 0),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildActiveStoryWidget() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: ActiveStoryWidget(
        key: ValueKey('active_story_${widget.character.storyState?.hashCode}'),
        character: widget.character,
        onDecisionSelect: widget.onDecisionSelect,
        onAbandonStory: widget.onAbandonStory,
        onRestSegment: widget.onRestSegment,
      ),
    );
  }

  Widget _buildAvailableStoriesWidget() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      child: AvailableStoriesWidget(
        key: const ValueKey('available_stories'),
        character: widget.character,
        onStorySelect: widget.onStorySelect,
        isLoading: widget.isLoading,
      ),
    );
  }

  Widget _buildHistoryWidget() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      switchInCurve: Curves.easeInOut,
      switchOutCurve: Curves.easeInOut,
      child: StoryHistoryWidget(
        key: const ValueKey('story_history'),
        character: widget.character,
      ),
    );
  }
}