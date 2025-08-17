import 'package:flutter/material.dart';

import '../../models/character.dart';

/// Widget displaying completed story history
class StoryHistoryWidget extends StatefulWidget {
  final Character character;
  final Function(String)? onStoryTap;

  const StoryHistoryWidget({
    super.key,
    required this.character,
    this.onStoryTap,
  });

  @override
  State<StoryHistoryWidget> createState() => _StoryHistoryWidgetState();
}

class _StoryHistoryWidgetState extends State<StoryHistoryWidget> {
  String _filterOutcome = 'all';
  String _sortBy = 'recent';
  
  // Mock history data - in production this would come from API
  List<StoryHistoryEntry> get _historyEntries {
    // For now, create mock entries from completed stories
    return widget.character.completedStories.asMap().entries.map((entry) {
      final index = entry.key;
      final storyId = entry.value;
      
      return StoryHistoryEntry(
        storyId: storyId,
        storyTitle: _extractStoryTitle(storyId),
        completedAt: DateTime.now().subtract(Duration(days: index * 2)),
        outcome: index % 3 == 0 ? 'success' : index % 3 == 1 ? 'normal' : 'failure',
        duration: Duration(minutes: 15 + (index * 5)),
        rewards: {
          'XP': 100 + (index * 50),
          'Gold': 50 + (index * 25),
        },
        segments: 5 + index,
      );
    }).toList();
  }
  
  String _extractStoryTitle(String storyId) {
    // Extract a readable title from story ID
    return storyId
        .replaceAll('-', ' ')
        .replaceAll('_', ' ')
        .split(' ')
        .map((word) => word.isNotEmpty 
            ? word[0].toUpperCase() + word.substring(1).toLowerCase()
            : word)
        .join(' ');
  }
  
  List<StoryHistoryEntry> get _filteredEntries {
    var entries = _historyEntries;
    
    // Apply filter
    if (_filterOutcome != 'all') {
      entries = entries.where((entry) => 
        entry.outcome.toLowerCase() == _filterOutcome.toLowerCase()
      ).toList();
    }
    
    // Apply sort
    switch (_sortBy) {
      case 'recent':
        entries.sort((a, b) => b.completedAt.compareTo(a.completedAt));
        break;
      case 'oldest':
        entries.sort((a, b) => a.completedAt.compareTo(b.completedAt));
        break;
      case 'duration':
        entries.sort((a, b) => b.duration.compareTo(a.duration));
        break;
      case 'rewards':
        entries.sort((a, b) {
          final aTotal = a.rewards.values.fold<int>(0, (sum, val) => sum + val);
          final bTotal = b.rewards.values.fold<int>(0, (sum, val) => sum + val);
          return bTotal.compareTo(aTotal);
        });
        break;
    }
    
    return entries;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.character.completedStories.isEmpty) {
      return _buildEmptyState(context);
    }
    
    return Column(
      children: [
        // Filter and Sort Bar
        _FilterSortBar(
          filterOutcome: _filterOutcome,
          sortBy: _sortBy,
          onFilterChanged: (value) {
            setState(() {
              _filterOutcome = value;
            });
          },
          onSortChanged: (value) {
            setState(() {
              _sortBy = value;
            });
          },
        ),
        const SizedBox(height: 16),
        
        // Statistics Summary
        _StatisticsSummary(entries: _historyEntries),
        const SizedBox(height: 16),
        
        // History List
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: _filteredEntries.length,
            itemBuilder: (context, index) {
              final entry = _filteredEntries[index];
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _HistoryEntryCard(
                  entry: entry,
                  onTap: widget.onStoryTap != null
                      ? () => widget.onStoryTap!(entry.storyId)
                      : null,
                ),
              );
            },
          ),
        ),
      ],
    );
  }
  
  Widget _buildEmptyState(BuildContext context) {
    final theme = Theme.of(context);
    
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.history,
            size: 80,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 16),
          Text(
            'No Completed Stories',
            style: theme.textTheme.headlineSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Your completed adventures will appear here',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterSortBar extends StatelessWidget {
  final String filterOutcome;
  final String sortBy;
  final ValueChanged<String> onFilterChanged;
  final ValueChanged<String> onSortChanged;

  const _FilterSortBar({
    required this.filterOutcome,
    required this.sortBy,
    required this.onFilterChanged,
    required this.onSortChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          // Filter Dropdown
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  Icon(
                    Icons.filter_alt,
                    size: 18,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  _OutcomeFilterChip(
                    label: 'All',
                    value: 'all',
                    selected: filterOutcome == 'all',
                    onSelected: onFilterChanged,
                  ),
                  const SizedBox(width: 8),
                  _OutcomeFilterChip(
                    label: 'Success',
                    value: 'success',
                    selected: filterOutcome == 'success',
                    onSelected: onFilterChanged,
                    color: Colors.green,
                  ),
                  const SizedBox(width: 8),
                  _OutcomeFilterChip(
                    label: 'Normal',
                    value: 'normal',
                    selected: filterOutcome == 'normal',
                    onSelected: onFilterChanged,
                    color: Colors.blue,
                  ),
                  const SizedBox(width: 8),
                  _OutcomeFilterChip(
                    label: 'Failure',
                    value: 'failure',
                    selected: filterOutcome == 'failure',
                    onSelected: onFilterChanged,
                    color: Colors.red,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 16),
          // Sort Dropdown
          PopupMenuButton<String>(
            icon: Icon(
              Icons.sort,
              color: theme.colorScheme.primary,
            ),
            tooltip: 'Sort by',
            onSelected: onSortChanged,
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'recent',
                child: Row(
                  children: const [
                    Icon(Icons.schedule, size: 18),
                    SizedBox(width: 8),
                    Text('Most Recent'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'oldest',
                child: Row(
                  children: const [
                    Icon(Icons.history, size: 18),
                    SizedBox(width: 8),
                    Text('Oldest First'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'duration',
                child: Row(
                  children: const [
                    Icon(Icons.timer, size: 18),
                    SizedBox(width: 8),
                    Text('Duration'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'rewards',
                child: Row(
                  children: const [
                    Icon(Icons.card_giftcard, size: 18),
                    SizedBox(width: 8),
                    Text('Rewards'),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _OutcomeFilterChip extends StatelessWidget {
  final String label;
  final String value;
  final bool selected;
  final ValueChanged<String> onSelected;
  final Color? color;

  const _OutcomeFilterChip({
    required this.label,
    required this.value,
    required this.selected,
    required this.onSelected,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final chipColor = color ?? theme.colorScheme.primary;
    
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onSelected(value),
      selectedColor: chipColor.withValues(alpha: 0.2),
      checkmarkColor: chipColor,
      labelStyle: TextStyle(
        color: selected ? chipColor : theme.colorScheme.onSurfaceVariant,
        fontWeight: selected ? FontWeight.bold : FontWeight.normal,
        fontSize: 12,
      ),
    );
  }
}

class _StatisticsSummary extends StatelessWidget {
  final List<StoryHistoryEntry> entries;

  const _StatisticsSummary({required this.entries});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    if (entries.isEmpty) return const SizedBox();
    
    final totalStories = entries.length;
    final successCount = entries.where((e) => e.outcome == 'success').length;
    final totalXP = entries.fold<int>(
      0, (sum, e) => sum + (e.rewards['XP'] ?? 0)
    );
    final totalGold = entries.fold<int>(
      0, (sum, e) => sum + (e.rewards['Gold'] ?? 0)
    );
    final totalTime = entries.fold<Duration>(
      Duration.zero, (sum, e) => sum + e.duration
    );
    
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.colorScheme.primaryContainer,
            theme.colorScheme.primaryContainer.withValues(alpha: 0.5),
          ],
        ),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withValues(alpha: 0.1),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Adventure Statistics',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.onPrimaryContainer,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _StatItem(
                  icon: Icons.flag,
                  label: 'Completed',
                  value: totalStories.toString(),
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
              Expanded(
                child: _StatItem(
                  icon: Icons.emoji_events,
                  label: 'Success Rate',
                  value: '${((successCount / totalStories) * 100).toStringAsFixed(0)}%',
                  color: Colors.green,
                ),
              ),
              Expanded(
                child: _StatItem(
                  icon: Icons.timer,
                  label: 'Total Time',
                  value: _formatDuration(totalTime),
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _StatItem(
                  icon: Icons.trending_up,
                  label: 'Total XP',
                  value: _formatNumber(totalXP),
                  color: Colors.purple,
                ),
              ),
              Expanded(
                child: _StatItem(
                  icon: Icons.monetization_on,
                  label: 'Total Gold',
                  value: _formatNumber(totalGold),
                  color: Colors.orange,
                ),
              ),
              Expanded(
                child: _StatItem(
                  icon: Icons.insights,
                  label: 'Avg Duration',
                  value: _formatDuration(
                    Duration(minutes: totalTime.inMinutes ~/ totalStories),
                  ),
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _formatDuration(Duration duration) {
    if (duration.inHours > 0) {
      return '${duration.inHours}h ${duration.inMinutes % 60}m';
    }
    return '${duration.inMinutes}m';
  }

  String _formatNumber(int number) {
    if (number >= 1000000) {
      return '${(number / 1000000).toStringAsFixed(1)}M';
    } else if (number >= 1000) {
      return '${(number / 1000).toStringAsFixed(1)}K';
    }
    return number.toString();
  }
}

class _StatItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatItem({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Column(
      children: [
        Icon(icon, size: 20, color: color),
        const SizedBox(height: 4),
        Text(
          value,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: color.withValues(alpha: 0.8),
          ),
        ),
      ],
    );
  }
}

class _HistoryEntryCard extends StatelessWidget {
  final StoryHistoryEntry entry;
  final VoidCallback? onTap;

  const _HistoryEntryCard({
    required this.entry,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Card(
      elevation: 2,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  _OutcomeIcon(outcome: entry.outcome),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.storyTitle,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _formatDate(entry.completedAt),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _OutcomeBadge(outcome: entry.outcome),
                ],
              ),
              const SizedBox(height: 12),
              
              // Stats Row
              Row(
                children: [
                  _EntryStatChip(
                    icon: Icons.flag_outlined,
                    label: '${entry.segments} segments',
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  _EntryStatChip(
                    icon: Icons.timer_outlined,
                    label: _formatDuration(entry.duration),
                    color: theme.colorScheme.primary,
                  ),
                ],
              ),
              
              // Rewards
              if (entry.rewards.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: entry.rewards.entries.map((reward) {
                    return _RewardChip(
                      type: reward.key,
                      value: reward.value,
                    );
                  }).toList(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);
    
    if (difference.inDays == 0) {
      if (difference.inHours == 0) {
        return '${difference.inMinutes} minutes ago';
      }
      return '${difference.inHours} hours ago';
    } else if (difference.inDays == 1) {
      return 'Yesterday';
    } else if (difference.inDays < 7) {
      return '${difference.inDays} days ago';
    } else if (difference.inDays < 30) {
      return '${difference.inDays ~/ 7} weeks ago';
    } else {
      return '${date.day}/${date.month}/${date.year}';
    }
  }

  String _formatDuration(Duration duration) {
    if (duration.inHours > 0) {
      return '${duration.inHours}h ${duration.inMinutes % 60}m';
    }
    return '${duration.inMinutes}m';
  }
}

class _OutcomeIcon extends StatelessWidget {
  final String outcome;

  const _OutcomeIcon({required this.outcome});

  @override
  Widget build(BuildContext context) {
    IconData icon;
    Color color;
    
    switch (outcome.toLowerCase()) {
      case 'success':
      case 'exceptional':
        icon = Icons.emoji_events;
        color = Colors.green;
        break;
      case 'normal':
        icon = Icons.check_circle;
        color = Colors.blue;
        break;
      case 'failure':
        icon = Icons.cancel;
        color = Colors.red;
        break;
      default:
        icon = Icons.help_outline;
        color = Colors.grey;
    }
    
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(icon, color: color, size: 24),
    );
  }
}

class _OutcomeBadge extends StatelessWidget {
  final String outcome;

  const _OutcomeBadge({required this.outcome});

  @override
  Widget build(BuildContext context) {
    Color color;
    
    switch (outcome.toLowerCase()) {
      case 'success':
      case 'exceptional':
        color = Colors.green;
        break;
      case 'normal':
        color = Colors.blue;
        break;
      case 'failure':
        color = Colors.red;
        break;
      default:
        color = Colors.grey;
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color),
      ),
      child: Text(
        outcome.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.bold,
          color: color,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

class _EntryStatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _EntryStatChip({
    required this.icon,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

class _RewardChip extends StatelessWidget {
  final String type;
  final int value;

  const _RewardChip({
    required this.type,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    IconData icon;
    Color color;
    
    switch (type.toLowerCase()) {
      case 'xp':
      case 'experience':
        icon = Icons.trending_up;
        color = Colors.purple;
        break;
      case 'gold':
      case 'coins':
        icon = Icons.monetization_on;
        color = Colors.orange;
        break;
      default:
        icon = Icons.card_giftcard;
        color = theme.colorScheme.primary;
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            '+$value $type',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

// Data model for history entries
class StoryHistoryEntry {
  final String storyId;
  final String storyTitle;
  final DateTime completedAt;
  final String outcome;
  final Duration duration;
  final Map<String, int> rewards;
  final int segments;

  StoryHistoryEntry({
    required this.storyId,
    required this.storyTitle,
    required this.completedAt,
    required this.outcome,
    required this.duration,
    required this.rewards,
    required this.segments,
  });
}