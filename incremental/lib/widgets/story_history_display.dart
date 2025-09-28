import 'package:flutter/material.dart';

import '../utils/outcome_colors.dart';

class StoryHistoryDisplay extends StatelessWidget {
  final List<Map<String, dynamic>> completedStories;
  final Function(Map<String, dynamic>) onStorySelected;

  const StoryHistoryDisplay({
    super.key,
    required this.completedStories,
    required this.onStorySelected,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (completedStories.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            children: [
              Icon(
                Icons.history,
                size: 48,
                color: theme.colorScheme.onSurfaceVariant.withValues(
                  alpha: 0.5,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'No completed stories yet',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Text(
            'Completed Stories',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        ...completedStories.map((story) => _buildStoryCard(context, story)),
      ],
    );
  }

  Widget _buildStoryCard(BuildContext context, Map<String, dynamic> story) {
    final theme = Theme.of(context);
    final outcome = story['Outcome'] as String? ?? 'completed';
    final segmentHistory = story['SegmentHistory'] as List? ?? [];
    final segmentCount = segmentHistory.length;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => onStorySelected(story),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
            children: [
              // Outcome icon
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: outcomeAccentColor(
                    theme,
                    outcome,
                  ).withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  _getOutcomeIcon(outcome),
                  color: outcomeAccentColor(theme, outcome),
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              // Story info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      story['Title'] as String? ?? 'Unknown Story',
                      style: theme.textTheme.titleSmall,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '$segmentCount segments • ${_formatOutcome(outcome)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    if (story['CompletedAt'] != null)
                      Text(
                        _formatDate(story['CompletedAt'] as int),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                  ],
                ),
              ),
              // Arrow
              Icon(
                Icons.chevron_right,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _getOutcomeIcon(String outcome) {
    switch (normalizedOutcomeType(outcome)) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
      case 'failed':
        return Icons.warning;
      default:
        return Icons.check_circle;
    }
  }

  String _formatOutcome(String outcome) {
    return outcome.substring(0, 1).toUpperCase() + outcome.substring(1);
  }

  String _formatDate(int timestamp) {
    final date = DateTime.fromMillisecondsSinceEpoch(timestamp * 1000);
    final now = DateTime.now();
    final difference = now.difference(date);

    if (difference.inDays > 7) {
      return '${date.day}/${date.month}/${date.year}';
    } else if (difference.inDays > 0) {
      return '${difference.inDays}d ago';
    } else if (difference.inHours > 0) {
      return '${difference.inHours}h ago';
    } else if (difference.inMinutes > 0) {
      return '${difference.inMinutes}m ago';
    } else {
      return 'Just now';
    }
  }
}
