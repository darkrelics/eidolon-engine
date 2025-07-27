import 'package:flutter/material.dart';

/// Widget to display countdown timer for story segments
class ProgressTimer extends StatelessWidget {
  final int timeRemaining;
  final int totalTime;

  const ProgressTimer({
    super.key,
    required this.timeRemaining,
    required this.totalTime,
  });

  String _formatTime(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  double get progress {
    if (totalTime <= 0) return 0.0;
    return (totalTime - timeRemaining) / totalTime;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Time Remaining',
          style: theme.textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: 120,
              height: 120,
              child: CircularProgressIndicator(
                value: progress,
                strokeWidth: 8,
                backgroundColor: theme.dividerColor,
                valueColor: AlwaysStoppedAnimation<Color>(
                  timeRemaining <= 30
                      ? theme.colorScheme.error
                      : theme.colorScheme.primary,
                ),
              ),
            ),
            Text(
              _formatTime(timeRemaining),
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: timeRemaining <= 30
                    ? theme.colorScheme.error
                    : theme.colorScheme.onSurface,
              ),
            ),
          ],
        ),
        if (timeRemaining <= 30) ...[
          const SizedBox(height: 8),
          Text(
            'Segment ending soon!',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.error,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ],
    );
  }
}