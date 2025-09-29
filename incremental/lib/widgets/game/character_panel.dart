import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';

/// Left panel displaying character stats and information
class CharacterPanel extends StatelessWidget {
  final Character character;
  final VoidCallback? onRefresh;

  const CharacterPanel({super.key, required this.character, this.onRefresh});

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
                Icon(Icons.person, color: colorScheme.onPrimaryContainer),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    character.name,
                    style: theme.textTheme.titleLarge?.copyWith(
                      color: colorScheme.onPrimaryContainer,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                if (onRefresh != null)
                  IconButton(
                    icon: Icon(
                      Icons.refresh,
                      color: colorScheme.onPrimaryContainer,
                    ),
                    onPressed: onRefresh,
                    tooltip: 'Refresh Character',
                  ),
              ],
            ),
          ),

          // Content
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Archetype
                  _InfoRow(
                    label: 'Archetype',
                    value: character.archetypeName,
                    icon: Icons.category,
                  ),
                  const SizedBox(height: 16),

                  // Health Bar
                  _StatBar(
                    label: 'Health',
                    current: character.health,
                    max: character.maxHealth,
                    color: Colors.red,
                    icon: Icons.favorite,
                  ),
                  const SizedBox(height: 12),

                  // Essence Bar
                  _StatBar(
                    label: 'Essence',
                    current: character.essence,
                    max: character.maxEssence,
                    color: Colors.blue,
                    icon: Icons.water_drop,
                  ),
                  const SizedBox(height: 20),

                  // Attributes Section
                  _SectionHeader(title: 'Attributes'),
                  const SizedBox(height: 8),
                  ...character.attributes.entries.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: _StatRow(
                        label: _formatStatName(entry.key),
                        value: entry.value.toStringAsFixed(1),
                        icon: _getAttributeIcon(entry.key),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Skills Section
                  if (character.skills.isNotEmpty) ...[
                    _SectionHeader(title: 'Skills'),
                    const SizedBox(height: 8),
                    ...character.skills.entries.map(
                      (entry) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: _StatRow(
                          label: _formatStatName(entry.key),
                          value: entry.value.toStringAsFixed(1),
                          icon: _getSkillIcon(entry.key),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Resources Section
                  if (character.resources.isNotEmpty) ...[
                    _SectionHeader(title: 'Resources'),
                    const SizedBox(height: 8),
                    ...character.resources.entries.map(
                      (entry) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: _StatRow(
                          label: _formatStatName(entry.key),
                          value: entry.value.toString(),
                          icon: _getResourceIcon(entry.key),
                        ),
                      ),
                    ),
                  ],

                  // Last Updated
                  const SizedBox(height: 20),
                  Text(
                    'Last Updated: ${_formatDateTime(character.lastUpdated)}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatStatName(String name) {
    // Convert snake_case to Title Case
    return name
        .split('_')
        .map((word) => word[0].toUpperCase() + word.substring(1))
        .join(' ');
  }

  String _formatDateTime(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inMinutes < 1) {
      return 'Just now';
    } else if (difference.inHours < 1) {
      return '${difference.inMinutes} min ago';
    } else if (difference.inDays < 1) {
      return '${difference.inHours} hours ago';
    } else {
      return '${difference.inDays} days ago';
    }
  }

  IconData _getAttributeIcon(String attribute) {
    switch (attribute.toLowerCase()) {
      case 'strength':
        return Icons.fitness_center;
      case 'agility':
        return Icons.speed;
      case 'intelligence':
        return Icons.psychology;
      case 'wisdom':
        return Icons.auto_awesome;
      case 'charisma':
        return Icons.star;
      case 'constitution':
        return Icons.shield;
      default:
        return Icons.bar_chart;
    }
  }

  IconData _getSkillIcon(String skill) {
    switch (skill.toLowerCase()) {
      case 'melee':
        return Icons.sports_martial_arts;
      case 'ranged':
        return Icons.gps_fixed;
      case 'magic':
        return Icons.auto_fix_high;
      case 'stealth':
        return Icons.visibility_off;
      case 'perception':
        return Icons.visibility;
      case 'crafting':
        return Icons.build;
      default:
        return Icons.school;
    }
  }

  IconData _getResourceIcon(String resource) {
    switch (resource.toLowerCase()) {
      case 'gold':
      case 'coins':
        return Icons.monetization_on;
      case 'experience':
      case 'xp':
        return Icons.trending_up;
      case 'reputation':
        return Icons.military_tech;
      default:
        return Icons.inventory_2;
    }
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;

  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: theme.colorScheme.primary, width: 2),
        ),
      ),
      child: Text(
        title,
        style: theme.textTheme.titleSmall?.copyWith(
          fontWeight: FontWeight.bold,
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _InfoRow({
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        Text(
          value,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}

class _StatRow extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _StatRow({
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: 8),
        Expanded(child: Text(label, style: theme.textTheme.bodyMedium)),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: theme.colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.onPrimaryContainer,
            ),
          ),
        ),
      ],
    );
  }
}

class _StatBar extends StatelessWidget {
  final String label;
  final double current;
  final double max;
  final Color color;
  final IconData icon;

  const _StatBar({
    required this.label,
    required this.current,
    required this.max,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final percentage = max > 0 ? (current / max).clamp(0.0, 1.0) : 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 4),
            Text(label, style: theme.textTheme.bodySmall),
            const Spacer(),
            Text(
              '${current.toStringAsFixed(0)} / ${max.toStringAsFixed(0)}',
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: percentage,
            backgroundColor: color.withValues(alpha: 0.2),
            valueColor: AlwaysStoppedAnimation<Color>(color),
            minHeight: 8,
          ),
        ),
      ],
    );
  }
}
