import 'package:flutter/material.dart';
import '../../models/character.dart';
import '../../models/story.dart';
import '../../services/story_cache_service.dart';
import '../story/active_story_widget.dart';
import '../story/available_stories_widget.dart';

/// Story panel display modes
enum StoryPanelState {
  selection,        // Show available + completed stories
  activeStory,      // Show active story + segments
  viewingCompleted  // Show completed story + segments
}

/// Center panel that displays story content dynamically
class StoryPanel extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final bool isLoading;
  final String? error;
  final VoidCallback? onRefresh;
  final Function(StoryMetadata)? onStorySelect;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onRestSegment;
  final VoidCallback? onReturnToStories;
  final Function(String)? onCompletedStorySelect;

  const StoryPanel({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.isLoading = false,
    this.error,
    this.onRefresh,
    this.onStorySelect,
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onRestSegment,
    this.onReturnToStories,
    this.onCompletedStorySelect,
  });

  @override
  State<StoryPanel> createState() => _StoryPanelState();
}

class _StoryPanelState extends State<StoryPanel> {
  StoryPanelState _currentState = StoryPanelState.selection;
  Map<String, dynamic>? _viewingCompletedStory;
  List<CompletedStoryInfo> _cachedCompletedStories = [];
  final StoryCacheService _storyCacheService = StoryCacheService();

  @override
  void initState() {
    super.initState();
    _loadCachedCompletedStories();
  }

  @override
  void didUpdateWidget(StoryPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Update state based on character changes
    if (oldWidget.character.id != widget.character.id ||
        oldWidget.character.lastUpdated != widget.character.lastUpdated) {
      _updatePanelState();
      _loadCachedCompletedStories();
    }
  }

  /// Load cached completed stories for this character
  Future<void> _loadCachedCompletedStories() async {
    final cachedStories = await _storyCacheService.getCachedStoriesForCharacter(
      widget.character.id,
    );
    
    if (mounted) {
      setState(() {
        _cachedCompletedStories = cachedStories;
      });
    }
  }

  /// Update panel state based on character state
  void _updatePanelState() {
    final char = widget.character;
    
    if (_viewingCompletedStory != null) {
      // Stay in viewing completed mode unless explicitly changed
      _currentState = StoryPanelState.viewingCompleted;
    } else if (char.activeStoryID != null) {
      // Character has an active story
      _currentState = StoryPanelState.activeStory;
    } else {
      // No active story, show selection
      _currentState = StoryPanelState.selection;
      _viewingCompletedStory = null; // Clear any completed story viewing
    }
  }

  /// Handle completed story selection
  void _handleCompletedStorySelect(String storyId) async {
    final cachedStory = await _storyCacheService.getCachedStory(
      characterId: widget.character.id,
      storyId: storyId,
    );
    
    if (cachedStory != null && mounted) {
      setState(() {
        _currentState = StoryPanelState.viewingCompleted;
        _viewingCompletedStory = cachedStory;
      });
      
      // Call the callback if provided
      widget.onCompletedStorySelect?.call(storyId);
    }
  }

  /// Return to story selection
  void _handleReturnToSelection() {
    setState(() {
      _currentState = StoryPanelState.selection;
      _viewingCompletedStory = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    // Update state based on current character
    _updatePanelState();
    
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
                // Back button for completed story viewing
                if (_currentState == StoryPanelState.viewingCompleted)
                  IconButton(
                    icon: Icon(
                      Icons.arrow_back,
                      color: colorScheme.onPrimaryContainer,
                    ),
                    onPressed: _handleReturnToSelection,
                    tooltip: 'Back to Stories',
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
          ),
          
          // Content
          Expanded(
            child: _buildContent(),
          ),
        ],
      ),
    );
  }

  String _getHeaderTitle() {
    switch (_currentState) {
      case StoryPanelState.selection:
        return 'Stories';
      case StoryPanelState.activeStory:
        // Check if story is complete (has completed segments but no active segment)
        final hasCompletedSegments = widget.character.storyState?['CompletedSegments'] != null &&
            (widget.character.storyState!['CompletedSegments'] as List).isNotEmpty;
        final hasActiveSegment = widget.character.activeSegmentID != null;
        
        if (hasCompletedSegments && !hasActiveSegment) {
          return 'Story Complete';
        }
        return 'Story';
      case StoryPanelState.viewingCompleted:
        return _viewingCompletedStory?['storyState']?['Story']?['Title'] ?? 'Completed Story';
    }
  }

  Widget _buildContent() {
    // Handle loading state
    if (widget.isLoading && _currentState == StoryPanelState.selection && 
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
        ),
      );
    }

    // Handle error state
    if (widget.error != null) {
      return _buildErrorWidget();
    }

    // Build content based on current state
    switch (_currentState) {
      case StoryPanelState.selection:
        return _buildUnifiedStorySelection();
      case StoryPanelState.activeStory:
        return _buildActiveStoryWidget();
      case StoryPanelState.viewingCompleted:
        return _buildCompletedStoryView();
    }
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
            ),
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
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// Build unified story selection showing available + completed stories
  Widget _buildUnifiedStorySelection() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Available Stories Section
          _buildAvailableStoriesSection(),
          
          // Completed Stories Section
          if (_cachedCompletedStories.isNotEmpty) ...[
            const SizedBox(height: 24),
            _buildCompletedStoriesSection(),
          ],
        ],
      ),
    );
  }

  /// Build available stories section
  Widget _buildAvailableStoriesSection() {
    return AvailableStoriesWidget(
      key: const ValueKey('available_stories'),
      character: widget.character,
      onStorySelect: widget.onStorySelect,
      isLoading: widget.isLoading,
    );
  }

  /// Build completed stories section
  Widget _buildCompletedStoriesSection() {
    final theme = Theme.of(context);
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Section Header
        Row(
          children: [
            Icon(
              Icons.history,
              color: theme.colorScheme.primary,
              size: 20,
            ),
            const SizedBox(width: 8),
            Text(
              'Completed Stories',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: theme.colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '${_cachedCompletedStories.length}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onPrimaryContainer,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        
        // Completed Story Cards
        ...(_cachedCompletedStories.take(5).map((completedStory) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: _CompletedStoryCard(
            completedStory: completedStory,
            onTap: () => _handleCompletedStorySelect(completedStory.storyId),
          ),
        ))),
        
        // Show More Button if there are more than 5
        if (_cachedCompletedStories.length > 5) ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () {
              // TODO: Show expanded completed stories view
            },
            icon: const Icon(Icons.expand_more),
            label: Text('Show ${_cachedCompletedStories.length - 5} More'),
          ),
        ],
      ],
    );
  }

  /// Build completed story view (when viewing a specific completed story)
  Widget _buildCompletedStoryView() {
    if (_viewingCompletedStory == null) {
      return const Center(
        child: Text('No completed story data'),
      );
    }

    final storyState = _viewingCompletedStory!['storyState'] as Map<String, dynamic>;
    final story = storyState['Story'] as Map<String, dynamic>?;
    final completedSegments = storyState['CompletedSegments'] as List<dynamic>?;
    
    if (story == null || completedSegments == null) {
      return const Center(
        child: Text('Invalid story data'),
      );
    }

    // Create a mock character with the completed story data for ActiveStoryWidget
    final mockCharacter = widget.character.copyWith(
      storyState: storyState,
    );
    
    // Convert completed segments to the format expected by ActiveStoryWidget
    final segmentHistory = completedSegments.cast<Map<String, dynamic>>();

    return ActiveStoryWidget(
      key: ValueKey('completed_story_${_viewingCompletedStory!['storyId']}'),
      character: mockCharacter,
      segmentHistory: segmentHistory,
      // No interactive callbacks for completed stories
      onDecisionSelect: null,
      onAbandonStory: null,
      onRestSegment: null,
      onRefresh: null,
    );
  }

  Widget _buildActiveStoryWidget() {
    return ActiveStoryWidget(
      key: ValueKey('active_story_${widget.character.storyState?.hashCode}'),
      character: widget.character,
      segmentHistory: widget.segmentHistory,
      onDecisionSelect: widget.onDecisionSelect,
      onAbandonStory: widget.onAbandonStory,
      onRestSegment: widget.onRestSegment,
      onRefresh: widget.onRefresh,
    );
  }

}

/// Widget for displaying a completed story in the selection list
class _CompletedStoryCard extends StatelessWidget {
  final CompletedStoryInfo completedStory;
  final VoidCallback onTap;

  const _CompletedStoryCard({
    required this.completedStory,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final outcomeColor = _getOutcomeColor(completedStory.lastOutcome);
    final outcomeIcon = _getOutcomeIcon(completedStory.lastOutcome);

    return Card(
      elevation: 1,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header Row
              Row(
                children: [
                  // Outcome Icon
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: outcomeColor.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Icon(
                      outcomeIcon,
                      size: 20,
                      color: outcomeColor,
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Title and Type
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          completedStory.storyTitle,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        _TypeBadge(type: completedStory.storyType),
                      ],
                    ),
                  ),
                  // Outcome Badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: outcomeColor.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: outcomeColor.withValues(alpha: 0.5)),
                    ),
                    child: Text(
                      completedStory.lastOutcome.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        color: outcomeColor,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ],
              ),
              
              // Description (if available)
              if (completedStory.storyDescription.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  completedStory.storyDescription,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              
              const SizedBox(height: 12),
              
              // Footer with stats
              Row(
                children: [
                  // Segment count
                  _StatChip(
                    icon: Icons.flag_outlined,
                    label: '${completedStory.segmentCount} segments',
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  // Completion time
                  _StatChip(
                    icon: Icons.schedule_outlined,
                    label: completedStory.formatCompletedAt(),
                    color: theme.colorScheme.primary,
                  ),
                  const Spacer(),
                  // View indicator
                  Icon(
                    Icons.chevron_right,
                    size: 16,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Color _getOutcomeColor(String outcome) {
    switch (outcome.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Colors.purple;
      case 'normal':
        return Colors.green;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      case 'death':
        return Colors.black;
      default:
        return Colors.grey;
    }
  }

  IconData _getOutcomeIcon(String outcome) {
    switch (outcome.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Icons.workspace_premium;
      case 'normal':
        return Icons.check_circle;
      case 'minimal':
        return Icons.check_circle_outline;
      case 'failure':
        return Icons.cancel;
      case 'death':
        return Icons.dangerous;
      default:
        return Icons.help_outline;
    }
  }
}

/// Type badge widget for story types
class _TypeBadge extends StatelessWidget {
  final String type;

  const _TypeBadge({required this.type});

  @override
  Widget build(BuildContext context) {
    final color = _getTypeColor(type);
    final icon = _getTypeIcon(type);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 0.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 10, color: color),
          const SizedBox(width: 2),
          Text(
            type.toUpperCase(),
            style: TextStyle(
              fontSize: 8,
              fontWeight: FontWeight.bold,
              color: color,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Color _getTypeColor(String type) {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Colors.purple;
      case 'daily':
        return Colors.blue;
      case 'repeatable':
        return Colors.green;
      case 'main':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Icons.looks_one;
      case 'daily':
        return Icons.today;
      case 'repeatable':
        return Icons.all_inclusive;
      case 'main':
        return Icons.star;
      default:
        return Icons.help_outline;
    }
  }
}

/// Small stat chip widget
class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _StatChip({
    required this.icon,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: color,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}