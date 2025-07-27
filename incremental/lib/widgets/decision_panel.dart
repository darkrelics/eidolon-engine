import 'package:flutter/material.dart';

/// Decision option for story segments
class DecisionOption {
  final String id;
  final String text;

  const DecisionOption({
    required this.id,
    required this.text,
  });
}

/// Widget to display decision options for story segments
class DecisionPanel extends StatelessWidget {
  final List<DecisionOption> options;
  final Function(String) onDecisionSelected;
  final bool isLoading;

  const DecisionPanel({
    super.key,
    required this.options,
    required this.onDecisionSelected,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Choose Your Action',
              style: theme.textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            if (isLoading)
              const Center(
                child: CircularProgressIndicator(),
              )
            else
              ...options.map((option) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4.0),
                    child: ElevatedButton(
                      onPressed: () => onDecisionSelected(option.id),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.all(16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: Text(
                        option.text,
                        style: theme.textTheme.bodyLarge,
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )),
            if (options.isEmpty && !isLoading) ...[
              Icon(
                Icons.hourglass_empty,
                size: 48,
                color: theme.colorScheme.onSurfaceVariant,
              ),
              const SizedBox(height: 8),
              Text(
                'No decisions available',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}