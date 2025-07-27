import 'package:flutter/material.dart';

/// Segment outcome data from API
class SegmentOutcomeData {
  final String outcome;
  final String narrative;
  final Map<String, dynamic> effects;
  final String? nextSegmentID;
  final String? decision;
  final List<dynamic>? challengeResults;
  final Map<String, dynamic>? combatState;

  SegmentOutcomeData({
    required this.outcome,
    required this.narrative,
    required this.effects,
    this.nextSegmentID,
    this.decision,
    this.challengeResults,
    this.combatState,
  });
}

/// Widget to display segment outcome results
class OutcomeDisplay extends StatelessWidget {
  final SegmentOutcomeData outcome;
  final VoidCallback? onContinue;

  const OutcomeDisplay({
    super.key,
    required this.outcome,
    this.onContinue,
  });

  Color _getOutcomeColor(BuildContext context) {
    final theme = Theme.of(context);
    switch (outcome.outcome.toLowerCase()) {
      case 'death':
        return theme.colorScheme.error;
      case 'failure':
        return Colors.orange;
      case 'minimal':
        return Colors.yellow.shade700;
      case 'normal':
        return theme.colorScheme.primary;
      case 'exceptional':
        return Colors.green;
      default:
        return theme.colorScheme.onSurface;
    }
  }

  IconData _getOutcomeIcon() {
    switch (outcome.outcome.toLowerCase()) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
        return Icons.error_outline;
      case 'minimal':
        return Icons.check_circle_outline;
      case 'normal':
        return Icons.check_circle;
      case 'exceptional':
        return Icons.star;
      default:
        return Icons.help_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final outcomeColor = _getOutcomeColor(context);

    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  _getOutcomeIcon(),
                  size: 48,
                  color: outcomeColor,
                ),
                const SizedBox(width: 16),
                Text(
                  outcome.outcome.toUpperCase(),
                  style: theme.textTheme.headlineMedium?.copyWith(
                    color: outcomeColor,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            if (outcome.narrative.isNotEmpty) ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceVariant,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  outcome.narrative,
                  style: theme.textTheme.bodyLarge,
                  textAlign: TextAlign.justify,
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (outcome.effects.isNotEmpty) ...[
              Text(
                'Effects:',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              ...outcome.effects.entries.map((entry) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2.0),
                    child: Row(
                      children: [
                        Icon(
                          entry.value > 0 ? Icons.add : Icons.remove,
                          size: 16,
                          color: entry.value > 0 ? Colors.green : Colors.red,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${entry.key}: ${entry.value > 0 ? '+' : ''}${entry.value}',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: entry.value > 0 ? Colors.green : Colors.red,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  )),
              const SizedBox(height: 16),
            ],
            if (onContinue != null)
              ElevatedButton(
                onPressed: onContinue,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.all(16),
                ),
                child: Text(
                  outcome.nextSegmentId != null ? 'Continue Story' : 'Return to Stories',
                  style: theme.textTheme.bodyLarge,
                ),
              ),
          ],
        ),
      ),
    );
  }
}