import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';

class ExpandableDescription extends StatefulWidget {
  final String description;
  final int maxLines;

  const ExpandableDescription({
    super.key,
    required this.description,
    this.maxLines = 2,
  });

  @override
  State<ExpandableDescription> createState() => _ExpandableDescriptionState();
}

class _ExpandableDescriptionState extends State<ExpandableDescription> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AnimatedSize(
          duration: const Duration(milliseconds: 200),
          child: Text(
            widget.description,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
            maxLines: _expanded ? null : widget.maxLines,
            overflow: _expanded ? TextOverflow.visible : TextOverflow.ellipsis,
          ),
        ),
        if (widget.description.length > 100) // Only show if text is long
          TextButton(
            onPressed: () => setState(() => _expanded = !_expanded),
            style: TextButton.styleFrom(
              padding: EdgeInsets.zero,
              minimumSize: const Size(0, 30),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: Text(
              _expanded ? 'Show less' : 'Show more',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
          ),
      ],
    );
  }
}

class PrerequisitesDisplay extends StatelessWidget {
  final Map<String, dynamic> prerequisites;
  final Character character;

  const PrerequisitesDisplay({
    super.key,
    required this.prerequisites,
    required this.character,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final minSkills = prerequisites['minSkills'] as Map<String, dynamic>? ?? {};
    final requiredItems =
        prerequisites['requiredItems'] as List<dynamic>? ?? [];

    if (minSkills.isEmpty && requiredItems.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.lock_open,
                size: 16,
                color: theme.colorScheme.onSurfaceVariant,
              ),
              const SizedBox(width: 4),
              Text(
                'Requirements',
                style: theme.textTheme.labelMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          if (minSkills.isNotEmpty) ...[
            const SizedBox(height: 4),
            ...minSkills.entries.map((entry) {
              final skill = entry.key;
              final required = (entry.value as num).toDouble();
              final current = character.skills[skill] ?? 0.0;
              final met = current >= required;

              return Padding(
                padding: const EdgeInsets.only(left: 20, top: 2),
                child: Row(
                  children: [
                    Icon(
                      met ? Icons.check_circle : Icons.cancel,
                      size: 14,
                      color: met ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${skill.substring(0, 1).toUpperCase()}${skill.substring(1)}: ${required.toStringAsFixed(1)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: met ? null : theme.colorScheme.error,
                        decoration: met ? null : TextDecoration.lineThrough,
                      ),
                    ),
                    Text(
                      ' (${current.toStringAsFixed(1)})',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
          if (requiredItems.isNotEmpty) ...[
            const SizedBox(height: 4),
            ...requiredItems.map((item) {
              final hasItem = character.contents.contains(item);

              return Padding(
                padding: const EdgeInsets.only(left: 20, top: 2),
                child: Row(
                  children: [
                    Icon(
                      hasItem ? Icons.check_circle : Icons.cancel,
                      size: 14,
                      color: hasItem ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      item.toString(),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: hasItem ? null : theme.colorScheme.error,
                        decoration: hasItem ? null : TextDecoration.lineThrough,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}

class RewardsPreview extends StatelessWidget {
  final Map<String, String> rewardTiers;

  const RewardsPreview({super.key, required this.rewardTiers});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (rewardTiers.isEmpty) {
      return const SizedBox.shrink();
    }

    // Define the order for reward tiers from best to worst
    final tierOrder = [
      'Exceptional',
      'Excellent',
      'Good',
      'Normal',
      'Basic',
      'Minimal',
      'Failure',
      'Death',
    ];

    // Sort the reward tiers according to the defined order
    final sortedEntries = rewardTiers.entries.toList()
      ..sort((a, b) {
        final aIndex = tierOrder.indexWhere(
          (t) => t.toLowerCase() == a.key.toLowerCase(),
        );
        final bIndex = tierOrder.indexWhere(
          (t) => t.toLowerCase() == b.key.toLowerCase(),
        );

        // If not found in order list, put at the end
        final aOrder = aIndex == -1 ? tierOrder.length : aIndex;
        final bOrder = bIndex == -1 ? tierOrder.length : bIndex;

        return aOrder.compareTo(bOrder);
      });

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: theme.colorScheme.secondaryContainer.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.card_giftcard,
                size: 16,
                color: theme.colorScheme.secondary,
              ),
              const SizedBox(width: 4),
              Text(
                'Potential Rewards',
                style: theme.textTheme.labelMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.secondary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          ...sortedEntries.map((entry) {
            final tier = entry.key;
            final description = entry.value;
            final tierLabel = _getTierLabel(tier);
            final tierColor = _getTierColor(tier, theme);

            return Padding(
              padding: const EdgeInsets.only(left: 20, top: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '$tierLabel: ',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w500,
                      color: tierColor,
                    ),
                  ),
                  Expanded(
                    child: Text(description, style: theme.textTheme.bodySmall),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  String _getTierLabel(String tier) {
    switch (tier.toLowerCase()) {
      case 'exceptional':
        return '★★★';
      case 'excellent':
        return '★★★';
      case 'good':
        return '★★';
      case 'normal':
        return '★★';
      case 'basic':
        return '★';
      case 'minimal':
        return '★';
      case 'failure':
        return 'Failure';
      case 'death':
        return 'Death';
      default:
        return tier.substring(0, 1).toUpperCase() + tier.substring(1);
    }
  }

  Color _getTierColor(String tier, ThemeData theme) {
    switch (tier.toLowerCase()) {
      case 'exceptional':
        return Colors.amber;
      case 'excellent':
        return Colors.amber;
      case 'good':
        return theme.colorScheme.secondary;
      case 'normal':
        return theme.colorScheme.secondary;
      case 'basic':
        return theme.colorScheme.onSurfaceVariant;
      case 'minimal':
        return theme.colorScheme.onSurfaceVariant;
      case 'failure':
        return Colors.orange;
      case 'death':
        return Colors.red;
      default:
        return theme.colorScheme.onSurface;
    }
  }
}

class StoryTypeChip extends StatelessWidget {
  final String type;

  const StoryTypeChip({super.key, required this.type});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    Color backgroundColor;
    IconData icon;

    switch (type.toLowerCase()) {
      case 'one-time':
        backgroundColor = theme.colorScheme.primaryContainer;
        icon = Icons.stars;
        break;
      case 'daily':
        backgroundColor = theme.colorScheme.secondaryContainer;
        icon = Icons.today;
        break;
      case 'repeatable':
        backgroundColor = theme.colorScheme.tertiaryContainer;
        icon = Icons.refresh;
        break;
      default:
        backgroundColor = theme.colorScheme.surfaceContainerHighest;
        icon = Icons.help_outline;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12),
          const SizedBox(width: 2),
          Text(type, style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}
