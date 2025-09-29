import 'package:flutter/material.dart';

import '../../models/story_history.dart';
import '../../services/story_history_service.dart';
import '../../utils/outcome_colors.dart';

/// Simplified story history widget that displays completed stories
class SimplifiedStoryHistoryWidget extends StatefulWidget {
  final List<Map<String, dynamic>> segmentHistory;

  const SimplifiedStoryHistoryWidget({super.key, this.segmentHistory = const []});

  @override
  State<SimplifiedStoryHistoryWidget> createState() => _SimplifiedStoryHistoryWidgetState();
}

class _SimplifiedStoryHistoryWidgetState extends State<SimplifiedStoryHistoryWidget> {
  final StoryHistoryService _service = StoryHistoryService();

  late List<StoryHistoryEntry> _entries;
  late StoryHistoryStats _stats;

  String _filterOutcome = 'all';
  String _sortBy = 'recent';

  @override
  void initState() {
    super.initState();
    _processData();
  }

  @override
  void didUpdateWidget(covariant SimplifiedStoryHistoryWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.segmentHistory != widget.segmentHistory) {
      _processData();
    }
  }

  void _processData() {
    _entries = _service.processStoryHistory(widget.segmentHistory);
    _stats = _service.calculateStats(_entries);
  }

  List<StoryHistoryEntry> _getFilteredAndSortedEntries() {
    var filtered = _service.filterByOutcome(_entries, _filterOutcome);
    return _service.sortEntries(filtered, _sortBy);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_entries.isEmpty) {
      return _buildEmptyState(theme);
    }

    final filteredEntries = _getFilteredAndSortedEntries();

    return Column(
      children: [
        // Filter and Sort Controls
        _FilterSortControls(
          filterOutcome: _filterOutcome,
          sortBy: _sortBy,
          onFilterChanged: (value) => setState(() => _filterOutcome = value),
          onSortChanged: (value) => setState(() => _sortBy = value),
        ),

        // Statistics Summary
        _StatisticsCard(stats: _stats),

        // Story List
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: filteredEntries.length,
            itemBuilder: (context, index) {
              final entry = filteredEntries[index];
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _StoryCard(entry: entry),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.history, size: 80, color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5)),
          const SizedBox(height: 16),
          Text('No Completed Stories', style: theme.textTheme.headlineSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          Text(
            'Complete a story to see its history here.',
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _FilterSortControls extends StatelessWidget {
  final String filterOutcome;
  final String sortBy;
  final ValueChanged<String> onFilterChanged;
  final ValueChanged<String> onSortChanged;

  const _FilterSortControls({
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
      color: theme.colorScheme.surfaceContainerHighest,
      child: Row(
        children: [
          // Filter Chips
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FilterChip(label: 'All', value: 'all', selected: filterOutcome == 'all', onSelected: onFilterChanged),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Success',
                    value: 'success',
                    selected: filterOutcome == 'success',
                    onSelected: onFilterChanged,
                    color: Colors.green,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Normal',
                    value: 'normal',
                    selected: filterOutcome == 'normal',
                    onSelected: onFilterChanged,
                    color: Colors.blue,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
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
          // Sort Menu
          PopupMenuButton<String>(
            icon: Icon(Icons.sort, color: theme.colorScheme.primary),
            onSelected: onSortChanged,
            itemBuilder: (context) => const [
              PopupMenuItem(value: 'recent', child: Text('Most Recent')),
              PopupMenuItem(value: 'oldest', child: Text('Oldest First')),
              PopupMenuItem(value: 'duration', child: Text('Duration')),
              PopupMenuItem(value: 'rewards', child: Text('Rewards')),
            ],
          ),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final String value;
  final bool selected;
  final ValueChanged<String> onSelected;
  final Color? color;

  const _FilterChip({required this.label, required this.value, required this.selected, required this.onSelected, this.color});

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
      ),
    );
  }
}

class _StatisticsCard extends StatelessWidget {
  final StoryHistoryStats stats;

  const _StatisticsCard({required this.stats});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [theme.colorScheme.primaryContainer, theme.colorScheme.primaryContainer.withValues(alpha: 0.5)],
        ),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Adventure Statistics',
            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: theme.colorScheme.onPrimaryContainer),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 16,
            runSpacing: 8,
            children: [
              _StatItem(icon: Icons.emoji_events, label: 'Successes', value: '${stats.successfulStories}', color: Colors.green),
              _StatItem(icon: Icons.change_circle, label: 'Normal', value: '${stats.normalStories}', color: Colors.blue),
              _StatItem(icon: Icons.report_problem, label: 'Failures', value: '${stats.failedStories}', color: Colors.orange),
              _StatItem(icon: Icons.close, label: 'Deaths', value: '${stats.deathStories}', color: Colors.red),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 16,
            children: [
              _StatItem(
                icon: Icons.timer,
                label: 'Total Time',
                value: _formatDuration(stats.totalTimePlayed),
                color: theme.colorScheme.primary,
              ),
              _StatItem(
                icon: Icons.insights,
                label: 'Avg Duration',
                value: _formatDuration(stats.averageStoryDuration),
                color: theme.colorScheme.primary,
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _formatDuration(Duration duration) {
    if (duration.inHours >= 1) {
      final hours = duration.inHours;
      final minutes = duration.inMinutes.remainder(60);
      return '${hours}h ${minutes}m';
    }
    if (duration.inMinutes >= 1) {
      return '${duration.inMinutes}m';
    }
    return '${duration.inSeconds}s';
  }
}

class _StatItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatItem({required this.icon, required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 4),
        Text(
          '$label: $value',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onPrimaryContainer, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }
}

class _StoryCard extends StatelessWidget {
  final StoryHistoryEntry entry;

  const _StoryCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Icon(_getOutcomeIcon(entry.outcome), color: outcomeAccentColor(theme, entry.outcome)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(entry.storyTitle, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                      const SizedBox(height: 2),
                      Text(
                        _formatDate(entry.completedAt),
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: outcomeAccentColor(theme, entry.outcome).withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: outcomeAccentColor(theme, entry.outcome)),
                  ),
                  child: Text(
                    entry.displayOutcome.toUpperCase(),
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: outcomeAccentColor(theme, entry.outcome)),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 12),

            // Stats Row
            Row(
              children: [
                _StatChip(icon: Icons.flag_outlined, label: '${entry.segments.length} segments'),
                const SizedBox(width: 8),
                _StatChip(icon: Icons.timer_outlined, label: _formatDuration(entry.duration)),
              ],
            ),

            // XP Rewards
            if (entry.totalXpGained > 0) ...[
              const SizedBox(height: 8),
              _StatChip(icon: Icons.trending_up, label: '+${entry.totalXpGained} XP', color: Colors.purple),
            ],
          ],
        ),
      ),
    );
  }

  IconData _getOutcomeIcon(String outcome) {
    switch (outcome.toLowerCase()) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
        return Icons.cancel;
      default:
        return Icons.check_circle;
    }
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

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color? color;

  const _StatChip({required this.icon, required this.label, this.color});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final chipColor = color ?? theme.colorScheme.primary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: chipColor.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(12)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: chipColor),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(fontSize: 12, color: chipColor, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}
