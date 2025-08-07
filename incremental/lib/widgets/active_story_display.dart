import 'package:flutter/material.dart';
import '../models/active_segment.dart';

class ActiveStoryDisplay extends StatelessWidget {
  final Map<String, dynamic> story;
  final ActiveSegment currentSegment;
  final List<Map<String, dynamic>> previousSegments;
  final int timeRemaining;
  final Function()? onDecision;
  final Map<String, dynamic>? decisionOptions;

  const ActiveStoryDisplay({
    super.key,
    required this.story,
    required this.currentSegment,
    required this.previousSegments,
    required this.timeRemaining,
    this.onDecision,
    this.decisionOptions,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Story Card at top
        _buildStoryCard(theme),
        const SizedBox(height: 16),
        
        // Current Segment with timer and progress
        _buildCurrentSegmentCard(theme),
        const SizedBox(height: 16),
        
        // Previous segments
        if (previousSegments.isNotEmpty) ...[
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: Text(
              'Previous Segments',
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          ...previousSegments.reversed.map((segment) => 
            _buildPreviousSegmentCard(theme, segment)
          ),
        ],
      ],
    );
  }

  Widget _buildStoryCard(ThemeData theme) {
    return Card(
      elevation: 4,
      color: theme.colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.auto_stories,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    story['Title'] as String? ?? 'Unknown Story',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onPrimaryContainer,
                    ),
                  ),
                ),
                // Story type chip
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    story['StoryType'] as String? ?? 'unknown',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              story['Description'] as String? ?? '',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.8),
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCurrentSegmentCard(ThemeData theme) {
    // Calculate duration from start and end times
    final duration = currentSegment.endTime - currentSegment.startTime;
    final progress = duration > 0 
        ? 1.0 - (timeRemaining / duration)
        : 0.0;

    return Card(
      elevation: 8,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header with timer
          Container(
            padding: const EdgeInsets.all(16.0),
            decoration: BoxDecoration(
              color: theme.colorScheme.secondaryContainer,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Current Segment',
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Row(
                  children: [
                    Icon(
                      Icons.timer,
                      size: 20,
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _formatTime(timeRemaining),
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSecondaryContainer,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          
          // Progress bar
          LinearProgressIndicator(
            value: progress,
            minHeight: 4,
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
            valueColor: AlwaysStoppedAnimation<Color>(
              theme.colorScheme.primary,
            ),
          ),
          
          // Content
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Status
                Text(
                  currentSegment.defaultStatus ?? 'Processing...',
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 8),
                
                // Narrative text or decision options
                if (currentSegment.segmentType == 'narrative') ...[
                  Text(
                    currentSegment.defaultStatus ?? 'Story continues...',
                    style: theme.textTheme.bodyMedium,
                  ),
                ] else if (currentSegment.segmentType == 'decision' && 
                          decisionOptions != null) ...[
                  Text(
                    currentSegment.defaultStatus ?? 'Make a choice:',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 12),
                  ...decisionOptions!.entries.map((entry) => 
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8.0),
                      child: FilledButton.tonal(
                        onPressed: timeRemaining == 0 ? () {
                          // Handle decision selection
                          if (onDecision != null) onDecision!();
                        } : null,
                        child: Text(entry.key),
                      ),
                    ),
                  ),
                ] else ...[
                  Text(
                    currentSegment.defaultStatus ?? '',
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
                
                // Segment type indicator
                const SizedBox(height: 12),
                Row(
                  children: [
                    Icon(
                      _getSegmentTypeIcon(currentSegment.segmentType),
                      size: 16,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _formatSegmentType(currentSegment.segmentType),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreviousSegmentCard(ThemeData theme, Map<String, dynamic> segment) {
    final segmentType = segment['SegmentType'] as String? ?? 'narrative';
    
    final shortStatus = segment['ShortStatus'] as String? ?? 'Unknown segment';
    
    final outcome = segment['Outcome'] as String?;
    
    final clientEvents = segment['ClientEvents'] as List<dynamic>? ?? [];

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    shortStatus,
                    style: theme.textTheme.titleSmall,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (outcome != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: _getOutcomeColor(outcome).withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      outcome,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: _getOutcomeColor(outcome),
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
              ],
            ),
            
            // Events
            if (clientEvents.isNotEmpty) ...[
              const SizedBox(height: 8),
              ...clientEvents.take(3).map((event) {
                try {
                  // Ensure event is a Map
                  final eventMap = event as Map<String, dynamic>;
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          _getEventIcon(eventMap['eventType']),
                          size: 14,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            _formatEvent(eventMap),
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  );
                } catch (e) {
                  debugPrint('ActiveStoryDisplay: Error processing event: $e');
                  debugPrint('ActiveStoryDisplay: Event value: $event');
                  return const SizedBox.shrink();
                }
              }),
              if (clientEvents.length > 3)
                Text(
                  '... and ${clientEvents.length - 3} more events',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                    fontStyle: FontStyle.italic,
                  ),
                ),
            ],
            
            // Segment type
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(
                  _getSegmentTypeIcon(segmentType),
                  size: 14,
                  color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
                ),
                const SizedBox(width: 4),
                Text(
                  _formatSegmentType(segmentType),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.6),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  IconData _getSegmentTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'mechanical':
        return Icons.build;
      case 'decision':
        return Icons.alt_route;
      case 'narrative':
        return Icons.description;
      case 'rest':
        return Icons.bed;
      default:
        return Icons.help_outline;
    }
  }

  IconData _getEventIcon(String? eventType) {
    switch (eventType?.toLowerCase()) {
      case 'skillcheck':
        return Icons.psychology;
      case 'combat':
        return Icons.sports_martial_arts;
      case 'decision':
        return Icons.alt_route;
      case 'narrative':
        return Icons.description;
      case 'reward':
        return Icons.card_giftcard;
      default:
        return Icons.circle;
    }
  }

  String _formatSegmentType(String type) {
    return type.substring(0, 1).toUpperCase() + type.substring(1);
  }

  String _formatEvent(Map<String, dynamic> event) {
    try {
      final eventType = event['eventType'] as String?;
      final data = event['data'] as Map<String, dynamic>?;
      final description = event['description'] as String?;
      
      if (eventType == 'narrative') {
        return description ?? data?['text'] ?? 'Story continues...';
      } else if (eventType == 'skillCheck' && data != null) {
        final skill = data['skill'] ?? 'unknown';
        final passed = data['passed'] ?? false;
        return 'Skill check: $skill (${passed ? "passed" : "failed"})';
      } else if (eventType == 'combat' && data != null) {
        return 'Combat encounter';
      }
      
      return eventType ?? 'Unknown event';
    } catch (e) {
      debugPrint('ActiveStoryDisplay: Error formatting event: $e');
      debugPrint('ActiveStoryDisplay: Event data: $event');
      return 'Event processing error';
    }
  }

  Color _getOutcomeColor(String outcome) {
    switch (outcome.toLowerCase()) {
      case 'exceptional':
        return Colors.amber;
      case 'normal':
        return Colors.green;
      case 'minimal':
        return Colors.blue;
      case 'failure':
        return Colors.orange;
      case 'death':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  String _formatTime(int seconds) {
    final minutes = seconds ~/ 60;
    final secs = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }
}