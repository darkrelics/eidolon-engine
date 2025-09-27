import 'package:flutter/material.dart';
import '../models/active_segment.dart';
import '../utils/time_utils.dart';

class RestSegmentDisplay extends StatelessWidget {
  final ActiveSegment activeSegment;

  const RestSegmentDisplay({super.key, required this.activeSegment});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isCompleted = activeSegment.status == 'completed';

    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header with icon
            Row(
              children: [
                Icon(Icons.hotel, size: 32, color: theme.colorScheme.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Resting',
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        'Healing wounds and recovering strength',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Rest benefits or completion status
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isCompleted
                    ? theme.colorScheme.primaryContainer
                    : theme.colorScheme.surfaceContainerHighest.withValues(
                        alpha: 0.5,
                      ),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (isCompleted) ...[
                    Row(
                      children: [
                        Icon(
                          Icons.check_circle,
                          color: theme.colorScheme.primary,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          'Rest Complete',
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: theme.colorScheme.onPrimaryContainer,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Your wounds have healed over time.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ] else ...[
                    Text(
                      'Resting Progress',
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    // Progress indicator
                    _buildProgressIndicator(context),
                    const SizedBox(height: 12),
                    Text(
                      'While resting:',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    _buildBenefitItem(
                      context,
                      Icons.favorite,
                      'Wounds heal naturally over time',
                      Colors.red,
                    ),
                    _buildBenefitItem(
                      context,
                      Icons.shield,
                      'Defenses recover to full strength',
                      Colors.blue,
                    ),
                    _buildBenefitItem(
                      context,
                      Icons.flash_on,
                      'Energy regenerates',
                      Colors.orange,
                    ),
                  ],
                ],
              ),
            ),

            // Time remaining
            if (!isCompleted)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.access_time,
                      size: 20,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Time remaining: ${_formatTimeRemaining()}',
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressIndicator(BuildContext context) {
    final total = TimeUtils.durationBetween(
      activeSegment.startTime,
      activeSegment.endTime,
    );
    final elapsed = TimeUtils.secondsSince(activeSegment.startTime);
    final progress = total > 0 ? (elapsed / total).clamp(0.0, 1.0) : 0.0;

    return Column(
      children: [
        LinearProgressIndicator(
          value: progress,
          minHeight: 8,
          backgroundColor: Theme.of(
            context,
          ).colorScheme.surfaceContainerHighest,
        ),
        const SizedBox(height: 4),
        Text(
          '${(progress * 100).toInt()}% complete',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }

  Widget _buildBenefitItem(
    BuildContext context,
    IconData icon,
    String text,
    Color iconColor,
  ) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: 16, color: iconColor),
          const SizedBox(width: 8),
          Text(text, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  String _formatTimeRemaining() {
    final remaining = TimeUtils.secondsUntil(activeSegment.endTime);

    if (remaining <= 0) return 'Complete';

    final minutes = remaining ~/ 60;
    final seconds = remaining % 60;

    if (minutes > 0) {
      return '$minutes:${seconds.toString().padLeft(2, '0')}';
    }
    return '${seconds}s';
  }
}
