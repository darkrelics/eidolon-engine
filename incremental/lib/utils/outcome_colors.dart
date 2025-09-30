import 'package:flutter/material.dart';

String? normalizedOutcomeType(dynamic outcome) {
  if (outcome == null) return null;
  if (outcome is String) {
    return outcome.toLowerCase();
  }
  if (outcome is Map && outcome['Type'] is String) {
    return (outcome['Type'] as String).toLowerCase();
  }
  return outcome.toString().toLowerCase();
}

Color outcomeAccentColor(ThemeData theme, dynamic outcome) {
  final type = normalizedOutcomeType(outcome);
  switch (type) {
    case 'death':
      return Colors.black;
    case 'failure':
    case 'failed':
      return theme.colorScheme.error;
    case 'minimal':
      return Colors.amber.shade600;
    case 'normal':
      return Colors.green.shade600;
    case 'exceptional':
    case 'success':
      return Colors.blue.shade500;
    default:
      return theme.colorScheme.primary;
  }
}

Color outcomeBackgroundColor(ThemeData theme, dynamic outcome) {
  final type = normalizedOutcomeType(outcome);
  final accent = outcomeAccentColor(theme, outcome);
  final alpha = type == 'death' ? 0.15 : 0.1;
  return accent.withValues(alpha: alpha);
}
