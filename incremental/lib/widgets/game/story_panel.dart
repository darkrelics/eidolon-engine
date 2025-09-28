import 'package:flutter/material.dart';

import '../../models/character.dart';
import '../../models/story.dart';
import '../../utils/outcome_colors.dart';
import '../story/active_story_widget.dart';
import '../story/available_stories_widget.dart';
import '../story/story_history_widget.dart';

/// Center panel that displays story content dynamically
class StoryPanel extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final List<Map<String, dynamic>> storyHistoryArchive;
  final bool isLoading;
  final String? error;
  final VoidCallback? onRefresh;
  final Function(StoryMetadata)? onStorySelect;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onRestSegment;
  final VoidCallback? onReturnToStories;

  const StoryPanel({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.storyHistoryArchive = const [],
    this.isLoading = false,
    this.error,
    this.onRefresh,
    this.onStorySelect,
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onRestSegment,
    this.onReturnToStories,
  });

  @override
  State<StoryPanel> createState() => _StoryPanelState();
}

class _StoryPanelState extends State<StoryPanel> {
  bool _showHistory = false;

  bool _hasActiveStory([Character? character]) {
    final char = character ?? widget.character;
    return char.activeStoryID != null;
  }

  bool _isStoryComplete() {
    if (_hasActiveStory()) {
      return false;
    }

    // Prefer the history tracked by the screen, fall back to any story state data
    if (widget.segmentHistory.isNotEmpty) {
      return true;
    }

    final stateSegments =
        widget.character.storyState?['CompletedSegments'] as List<dynamic>?;
    return stateSegments != null && stateSegments.isNotEmpty;
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
                Icon(Icons.auto_stories, color: colorScheme.onPrimaryContainer),
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
                if (!_hasActiveStory() &&
                    (widget.character.completedStories.isNotEmpty ||
                        widget.storyHistoryArchive.isNotEmpty))
                  IconButton(
                    icon: Icon(
                      _showHistory ? Icons.library_books : Icons.history,
                      color: colorScheme.onPrimaryContainer,
                    ),
                    onPressed: () {
                      setState(() {
                        _showHistory = !_showHistory;
                      });
                    },
                    tooltip: _showHistory
                        ? 'Show Available Stories'
                        : 'Show History',
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
          Expanded(child: _buildContent()),
        ],
      ),
    );
  }

  String _getHeaderTitle() {
    if (_isStoryComplete()) {
      return 'Story Complete';
    } else if (_hasActiveStory()) {
      return 'Story';
    } else if (_showHistory) {
      return 'Story History';
    } else {
      return 'Available Stories';
    }
  }

  Widget _buildContent() {
    // Don't show loading if we already have content
    if (widget.isLoading &&
        !_hasActiveStory() &&
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

    if (widget.error != null) {
      return _buildErrorWidget();
    }

    if (_isStoryComplete()) {
      return _buildStoryCompleteWidget();
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
            Icon(Icons.error_outline, size: 64, color: colorScheme.error),
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

  Widget _buildAvailableStoriesWidget() {
    return AvailableStoriesWidget(
      key: const ValueKey('available_stories'),
      character: widget.character,
      onStorySelect: widget.onStorySelect,
      isLoading: widget.isLoading,
    );
  }

  Widget _buildHistoryWidget() {
    return StoryHistoryWidget(
      key: const ValueKey('story_history'),
      character: widget.character,
      segmentHistory: widget.storyHistoryArchive,
    );
  }

  Widget _buildStoryCompleteWidget() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    // Get story data and completed segments (prefer provided history from parent)
    final storyData =
        widget.character.storyState?['Story'] as Map<String, dynamic>?;
    final completedSegmentsDynamic = widget.segmentHistory.isNotEmpty
        ? widget.segmentHistory
        : (widget.character.storyState?['CompletedSegments']
                  as List<dynamic>? ??
              const []);

    final completedSegments = completedSegmentsDynamic
        .map((segment) => segment as Map<String, dynamic>)
        .toList();

    if (completedSegments.isEmpty) {
      // Attempt to infer story information from history if available
      final storyTitle = widget.segmentHistory.isNotEmpty
          ? widget.segmentHistory.last['StoryTitle'] as String?
          : null;
      // Fallback to simple completion screen
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle, size: 80, color: colorScheme.primary),
            const SizedBox(height: 16),
            Text('Story Complete', style: theme.textTheme.headlineMedium),
            if (storyTitle != null) ...[
              const SizedBox(height: 8),
              Text(
                storyTitle,
                style: theme.textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: widget.onReturnToStories,
              icon: const Icon(Icons.chevron_left),
              label: const Text('Return to Stories'),
            ),
          ],
        ),
      );
    }

    // Get the last segment to determine overall outcome
    final lastSegment = completedSegments.last;
    final lastOutcome = lastSegment['Outcome'] ?? 'normal';

    // Check if story ended in death or complete failure
    final storyFailed = lastOutcome == 'death' || lastOutcome == 'failure';

    // If the API no longer supplies story metadata, fall back to the last segment title
    Map<String, dynamic>? effectiveStoryData = storyData;
    if (effectiveStoryData == null) {
      final inferredTitle = lastSegment['StoryTitle'];
      if (inferredTitle is String && inferredTitle.isNotEmpty) {
        effectiveStoryData = {'Title': inferredTitle};
      }
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Story Card at the top
          if (effectiveStoryData != null) ...[
            Card(
              elevation: 2,
              color: storyFailed
                  ? Colors.red.withValues(alpha: 0.1)
                  : Colors.green.withValues(alpha: 0.1),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Icon(
                      storyFailed ? Icons.dangerous : Icons.check_circle,
                      size: 64,
                      color: storyFailed ? Colors.red : Colors.green,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      effectiveStoryData['Title'] ?? 'Story',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      storyFailed ? 'FAILED' : 'COMPLETED',
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: storyFailed ? Colors.red : Colors.green,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Segment History - Reverse order (newest first)
          Text(
            'Story Segments',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),

          // Display segments in reverse order with full details
          ...completedSegments.reversed.map(
            (segmentMap) => _buildCompletedSegmentCard(segmentMap, theme),
          ),

          const SizedBox(height: 24),

          // Return button
          Center(
            child: FilledButton.icon(
              onPressed: widget.onReturnToStories,
              icon: const Icon(Icons.chevron_left),
              label: const Text('Return to Stories'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 12,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCompletedSegmentCard(
    Map<String, dynamic> segment,
    ThemeData theme,
  ) {
    final segmentTypeRaw = segment['SegmentType']?.toString() ?? 'mechanical';
    final segmentType = segmentTypeRaw.toLowerCase();
    final segmentTypeLabel = segmentTypeRaw.isNotEmpty
        ? '${segmentTypeRaw[0].toUpperCase()}${segmentTypeRaw.substring(1)}'
        : 'Unknown';
    final rawShortStatus = segment['ShortStatus']?.toString().trim();
    final rawDefaultStatus = segment['DefaultStatus']?.toString().trim();
    final narrative = _extractSegmentNarrative(segment);

    final usesPlaceholderShortStatus =
        _isProcessingPlaceholder(rawShortStatus) ||
        rawShortStatus == null ||
        rawShortStatus.isEmpty;
    final usesPlaceholderDefaultStatus = _isProcessingPlaceholder(
      rawDefaultStatus,
    );

    const gremlinTitle =
        'You are searching for signs of the troublesome gremlin';
    const gremlinStatus = 'Tracking the gremlin';

    final normalizedShortStatus = rawShortStatus?.toLowerCase();
    final normalizedDefaultStatus = rawDefaultStatus?.toLowerCase();
    final shouldApplyGremlinCopy =
        segmentType == 'mechanical' &&
        (usesPlaceholderShortStatus ||
            usesPlaceholderDefaultStatus ||
            normalizedShortStatus == gremlinStatus.toLowerCase() ||
            normalizedDefaultStatus == gremlinStatus.toLowerCase());

    final title = shouldApplyGremlinCopy
        ? gremlinTitle
        : _resolveCompletedSegmentTitle(
            rawShortStatus,
            narrative,
            rawDefaultStatus,
            segment['Prompt']?.toString(),
          );

    final subtitle = shouldApplyGremlinCopy
        ? gremlinStatus
        : (rawDefaultStatus ?? '');

    final outcome = segment['Outcome'];
    final cardColor = outcomeAccentColor(theme, outcome);
    final backgroundColor = outcomeBackgroundColor(theme, outcome);
    final icon = _resolveOutcomeIcon(outcome);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        color: backgroundColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: cardColor.withValues(alpha: 0.3), width: 1),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon, color: cardColor),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: cardColor,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Type: $segmentTypeLabel',
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                        if (subtitle.isNotEmpty &&
                            subtitle != title &&
                            !shouldApplyGremlinCopy) ...[
                          const SizedBox(height: 4),
                          Text(
                            subtitle,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
              if (narrative.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(
                  narrative,
                  style: theme.textTheme.bodyMedium,
                  textAlign: TextAlign.justify,
                ),
              ],
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.workspace_premium, size: 16, color: cardColor),
                  const SizedBox(width: 4),
                  Text(
                    'Outcome: ${_formatOutcome(outcome)}',
                    style: TextStyle(
                      color: cardColor,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static bool _isProcessingPlaceholder(String? value) {
    if (value == null) return false;
    final normalized = value.trim().toLowerCase();
    return normalized == 'processing...' ||
        normalized == '...processing...' ||
        normalized == 'processing your actions...';
  }

  String _resolveCompletedSegmentTitle(
    String? rawShortStatus,
    String narrative,
    String? defaultStatus,
    String? prompt,
  ) {
    if (rawShortStatus != null &&
        rawShortStatus.isNotEmpty &&
        !_isProcessingPlaceholder(rawShortStatus)) {
      return rawShortStatus;
    }

    if (narrative.isNotEmpty) {
      final trimmedNarrative = narrative.trim();
      final sentenceBreak = trimmedNarrative.indexOf(RegExp(r'[.!?]'));
      if (sentenceBreak > 0) {
        return trimmedNarrative.substring(0, sentenceBreak + 1).trim();
      }
      return trimmedNarrative;
    }

    if (defaultStatus != null && defaultStatus.trim().isNotEmpty) {
      return defaultStatus.trim();
    }

    if (prompt != null && prompt.trim().isNotEmpty) {
      return prompt.trim();
    }

    return 'Segment';
  }

  String _extractSegmentNarrative(Map<String, dynamic> segment) {
    final clientEvents = segment['ClientEvents'] as List<dynamic>?;
    if (clientEvents != null && clientEvents.isNotEmpty) {
      final descriptions = clientEvents
          .map(
            (event) => event is Map
                ? event['Description']?.toString() ?? ''
                : event.toString(),
          )
          .where((text) => text.trim().isNotEmpty)
          .toList();
      if (descriptions.isNotEmpty) {
        return descriptions.join('\n\n');
      }
    }

    final narrative = segment['Narrative']?.toString() ?? '';
    if (narrative.trim().isNotEmpty) {
      return narrative.trim();
    }

    final defaultStatus = segment['DefaultStatus']?.toString() ?? '';
    if (defaultStatus.trim().isNotEmpty) {
      return defaultStatus.trim();
    }

    return '';
  }

  String _outcomeToString(dynamic outcome) {
    if (outcome is String) {
      return outcome.toLowerCase();
    }
    if (outcome is Map && outcome['Type'] is String) {
      return (outcome['Type'] as String).toLowerCase();
    }
    return 'normal';
  }

  String _formatOutcome(dynamic outcome) {
    final outcomeStr = _outcomeToString(outcome);
    if (outcomeStr.isEmpty) {
      return 'Unknown';
    }
    return outcomeStr[0].toUpperCase() + outcomeStr.substring(1);
  }

  IconData _resolveOutcomeIcon(dynamic outcome) {
    switch (normalizedOutcomeType(outcome)) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
      case 'failed':
        return Icons.cancel;
      default:
        return Icons.check_circle;
    }
  }
}
