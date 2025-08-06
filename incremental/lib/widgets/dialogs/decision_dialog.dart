import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Dialog for confirming story decisions
class DecisionConfirmationDialog extends StatelessWidget {
  final Map<String, dynamic> choice;
  final VoidCallback onConfirm;

  const DecisionConfirmationDialog({
    super.key,
    required this.choice,
    required this.onConfirm,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final text = choice['Text'] ?? 'Make a choice';
    final description = choice['Description'] ?? '';
    final difficulty = choice['Difficulty'];
    final requirements = choice['Requirements'] as Map<String, dynamic>?;

    return Dialog(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 500),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: theme.colorScheme.primaryContainer,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(28),
                  topRight: Radius.circular(28),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.psychology,
                    color: theme.colorScheme.onPrimaryContainer,
                    size: 28,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Confirm Decision',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
            ).animate()
              .fadeIn(duration: 200.ms)
              .slideY(begin: -0.1, end: 0),

            // Content
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Choice Text
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: theme.colorScheme.primary.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.format_quote,
                              color: theme.colorScheme.primary,
                              size: 20,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                text,
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        ),
                        if (description.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text(
                            description,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ).animate()
                    .fadeIn(delay: 100.ms)
                    .slideX(begin: -0.05, end: 0),

                  // Difficulty Indicator
                  if (difficulty != null) ...[
                    const SizedBox(height: 16),
                    _DifficultyIndicator(difficulty: difficulty)
                        .animate()
                        .fadeIn(delay: 200.ms),
                  ],

                  // Requirements
                  if (requirements != null && requirements.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    _RequirementsDisplay(requirements: requirements)
                        .animate()
                        .fadeIn(delay: 250.ms),
                  ],

                  const SizedBox(height: 20),

                  // Warning
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.warningContainer,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.info_outline,
                          color: theme.colorScheme.onWarningContainer,
                          size: 20,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'This action cannot be undone',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onWarningContainer,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ).animate()
                    .fadeIn(delay: 300.ms)
                    .shake(delay: 500.ms, duration: 300.ms),
                ],
              ),
            ),

            // Actions
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainer,
                borderRadius: const BorderRadius.only(
                  bottomLeft: Radius.circular(28),
                  bottomRight: Radius.circular(28),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.icon(
                    onPressed: () {
                      Navigator.of(context).pop();
                      onConfirm();
                    },
                    icon: const Icon(Icons.check),
                    label: const Text('Confirm'),
                  ).animate()
                    .scale(delay: 400.ms, duration: 200.ms),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Future<bool> show({
    required BuildContext context,
    required Map<String, dynamic> choice,
  }) async {
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => DecisionConfirmationDialog(
        choice: choice,
        onConfirm: () => Navigator.of(context).pop(true),
      ),
    );
    return result ?? false;
  }
}

class _DifficultyIndicator extends StatelessWidget {
  final dynamic difficulty;

  const _DifficultyIndicator({required this.difficulty});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final level = difficulty is int ? difficulty : 0;
    final color = _getDifficultyColor(level);
    final label = _getDifficultyLabel(level);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(Icons.speed, color: color, size: 20),
          const SizedBox(width: 8),
          Text(
            'Difficulty: $label',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: color,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Spacer(),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(
              3,
              (index) => Padding(
                padding: const EdgeInsets.only(left: 2),
                child: Icon(
                  Icons.star,
                  size: 16,
                  color: index < level ? color : color.withValues(alpha: 0.2),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _getDifficultyColor(int level) {
    switch (level) {
      case 1:
        return Colors.green;
      case 2:
        return Colors.orange;
      case 3:
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  String _getDifficultyLabel(int level) {
    switch (level) {
      case 1:
        return 'Easy';
      case 2:
        return 'Moderate';
      case 3:
        return 'Hard';
      default:
        return 'Unknown';
    }
  }
}

class _RequirementsDisplay extends StatelessWidget {
  final Map<String, dynamic> requirements;

  const _RequirementsDisplay({required this.requirements});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: theme.colorScheme.error.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.lock_outline,
                color: theme.colorScheme.error,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                'Requirements',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...requirements.entries.map((entry) => Padding(
                padding: const EdgeInsets.only(left: 28, top: 4),
                child: Row(
                  children: [
                    Icon(
                      Icons.chevron_right,
                      size: 16,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${entry.key}: ${entry.value}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.error,
                      ),
                    ),
                  ],
                ),
              )),
        ],
      ),
    );
  }
}

extension ColorExtension on ColorScheme {
  Color get warningContainer => Colors.orange.withValues(alpha: 0.2);
  Color get onWarningContainer => Colors.orange.shade900;
}