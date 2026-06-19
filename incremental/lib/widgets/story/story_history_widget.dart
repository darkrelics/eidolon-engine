import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/utils/outcome_colors.dart';

/// Widget displaying completed story history
class StoryHistoryWidget extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final Function(String)? onStoryTap;

  const StoryHistoryWidget({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.onStoryTap,
  });

  @override
  State<StoryHistoryWidget> createState() => _StoryHistoryWidgetState();
}

class _StoryHistoryWidgetState extends State<StoryHistoryWidget> {
  String _filterOutcome = 'all';
  String _sortBy = 'recent';

  List<StoryHistoryEntry> _buildHistoryEntries() {
    if (widget.segmentHistory.isEmpty) {
      return const <StoryHistoryEntry>[];
    }

    final Map<String, List<Map<String, dynamic>>> segmentsByInstance = {};

    for (final segment in widget.segmentHistory) {
      final dynamic rawIdValue =
          segment['StoryInstanceID'] ?? segment['StoryID'];
      final rawInstanceId = (rawIdValue?.toString())?.trim();
      final key = (rawInstanceId != null && rawInstanceId.isNotEmpty)
          ? rawInstanceId
          : 'unknown';

      segmentsByInstance
          .putIfAbsent(key, () => <Map<String, dynamic>>[])
          .add(segment);
    }

    final history = <StoryHistoryEntry>[];

    for (final segments in segmentsByInstance.values) {
      if (segments.isEmpty) continue;

      segments.sort((a, b) {
        final aTime =
            _parseDate(a['CompletedAt']) ??
            _parseDate(a['EndTime']) ??
            _parseDate(a['StartTime']);
        final bTime =
            _parseDate(b['CompletedAt']) ??
            _parseDate(b['EndTime']) ??
            _parseDate(b['StartTime']);

        if (aTime == null && bTime == null) return 0;
        if (aTime == null) return -1;
        if (bTime == null) return 1;
        return aTime.compareTo(bTime);
      });

      final storyId = segments.first['StoryID']?.toString() ?? 'Unknown Story';
      final storyTitle = _selectStoryTitle(segments) ?? storyId;

      final startTime = _findEarliestDate(segments, 'StartTime');
      final completionTime = _findLatestCompletion(segments);

      final duration =
          (startTime != null &&
              completionTime != null &&
              !completionTime.isBefore(startTime))
          ? completionTime.difference(startTime)
          : Duration.zero;

      final outcome = _determineOutcome(segments);

      final totalXp = _calculateTotalXP(segments);
      final rewards = <String, int>{};
      if (totalXp > 0) {
        rewards['XP'] = totalXp;
      }

      history.add(
        StoryHistoryEntry(
          storyId: storyId,
          storyTitle: storyTitle,
          completedAt: completionTime ?? startTime ?? DateTime.now().toUtc(),
          outcome: outcome,
          duration: duration.isNegative ? Duration.zero : duration,
          rewards: rewards,
          segments: segments.length,
        ),
      );
    }

    history.sort((a, b) => b.completedAt.compareTo(a.completedAt));
    return history;
  }

  List<StoryHistoryEntry> _filteredEntries(List<StoryHistoryEntry> entries) {
    var filtered = List<StoryHistoryEntry>.from(entries);

    if (_filterOutcome != 'all') {
      filtered = filtered
          .where(
            (entry) => entry.outcomeCategory == _filterOutcome.toLowerCase(),
          )
          .toList();
    }

    switch (_sortBy) {
      case 'recent':
        filtered.sort((a, b) => b.completedAt.compareTo(a.completedAt));
        break;
      case 'oldest':
        filtered.sort((a, b) => a.completedAt.compareTo(b.completedAt));
        break;
      case 'duration':
        filtered.sort((a, b) => b.duration.compareTo(a.duration));
        break;
      case 'rewards':
        filtered.sort((a, b) {
          final aTotal = a.rewards.values.fold<int>(0, (sum, val) => sum + val);
          final bTotal = b.rewards.values.fold<int>(0, (sum, val) => sum + val);
          return bTotal.compareTo(aTotal);
        });
        break;
    }

    return filtered;
  }

  DateTime? _parseDate(Object? value) {
    if (value is DateTime) return value.toUtc();
    if (value is num) {
      final timestamp = value.toDouble();
      if (timestamp.isNaN) return null;
      if (timestamp > 1000000000000) {
        return DateTime.fromMillisecondsSinceEpoch(
          timestamp.round(),
          isUtc: true,
        );
      }
      return DateTime.fromMillisecondsSinceEpoch(
        (timestamp * 1000).round(),
        isUtc: true,
      );
    }
    if (value is String && value.isNotEmpty) {
      try {
        final trimmed = value.trim();
        final numeric = double.tryParse(trimmed);
        if (numeric != null) {
          return _parseDate(numeric);
        }
        return DateTime.parse(trimmed).toUtc();
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  DateTime? _findEarliestDate(
    List<Map<String, dynamic>> segments,
    String field,
  ) {
    DateTime? earliest;
    for (final segment in segments) {
      final candidate = _parseDate(segment[field]);
      if (candidate == null) continue;
      if (earliest == null || candidate.isBefore(earliest)) {
        earliest = candidate;
      }
    }
    return earliest;
  }

  DateTime? _findLatestCompletion(List<Map<String, dynamic>> segments) {
    DateTime? latest;
    for (final segment in segments) {
      final candidate =
          _parseDate(segment['ProcessedAt']) ??
          _parseDate(segment['CompletedAt']) ??
          _parseDate(segment['EndTime']);
      if (candidate == null) continue;
      if (latest == null || candidate.isAfter(latest)) {
        latest = candidate;
      }
    }
    return latest;
  }

  String _determineOutcome(List<Map<String, dynamic>> segments) {
    for (final segment in segments.reversed) {
      final outcome = segment['Outcome'];
      if (outcome is String && outcome.isNotEmpty) {
        return outcome;
      }
    }
    return 'unknown';
  }

  int _calculateTotalXP(List<Map<String, dynamic>> segments) {
    int total = 0;

    void accumulate(dynamic value) {
      if (value is Map) {
        for (final entry in value.values) {
          if (entry is num) {
            total += entry.round();
          }
        }
      }
    }

    for (final segment in segments) {
      accumulate(segment['SkillXPAwarded']);
      accumulate(segment['AttributeXPAwarded']);

      final characterUpdates = segment['CharacterUpdates'];
      if (characterUpdates is Map) {
        accumulate(characterUpdates['SkillsAwarded']);
        accumulate(characterUpdates['AttributesAwarded']);
      }
    }

    return total;
  }

  String? _selectStoryTitle(List<Map<String, dynamic>> segments) {
    for (final segment in segments) {
      final title = segment['StoryTitle'];
      if (title is String && title.trim().isNotEmpty) {
        return title.trim();
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final historyEntries = _buildHistoryEntries();
    if (historyEntries.isEmpty) {
      return _buildEmptyState(context);
    }

    final filteredEntries = _filteredEntries(historyEntries);

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
        _StatisticsSummary(entries: historyEntries),
        const SizedBox(height: 16),

        // History List
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: filteredEntries.length,
            itemBuilder: (context, index) {
              final entry = filteredEntries[index];
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
    final hasCompletedStories = widget.character.completedStories.isNotEmpty;
    final message = hasCompletedStories
        ? 'Story history is currently unavailable. Try refreshing your character.'
        : 'Complete a story to see its history here.';

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
            message,
            textAlign: TextAlign.center,
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
            icon: Icon(Icons.sort, color: theme.colorScheme.primary),
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
    final successCount = entries
        .where((entry) => entry.outcomeCategory == 'success')
        .length;
    final normalCount = entries
        .where((entry) => entry.outcomeCategory == 'normal')
        .length;
    final deathCount = entries
        .where((entry) => entry.outcome.toLowerCase() == 'death')
        .length;
    final rawFailureCount = entries
        .where((entry) => entry.outcome.toLowerCase() == 'failure')
        .length;
    final inferredFailures =
        totalStories -
        (successCount + normalCount + rawFailureCount + deathCount);
    final failureCount = math.max(0, rawFailureCount + inferredFailures);

    final totalTime = entries.fold<Duration>(
      Duration.zero,
      (sum, entry) => sum + entry.duration,
    );
    final averageDuration = totalStories > 0
        ? Duration(milliseconds: totalTime.inMilliseconds ~/ totalStories)
        : Duration.zero;

    final stats = <_OutcomeStatDefinition>[
      _OutcomeStatDefinition(
        icon: Icons.emoji_events,
        label: 'Successes',
        value: successCount,
        color: Colors.green,
      ),
      _OutcomeStatDefinition(
        icon: Icons.change_circle,
        label: 'Normal Progress',
        value: normalCount,
        color: theme.colorScheme.primary,
      ),
      _OutcomeStatDefinition(
        icon: Icons.report_problem,
        label: 'Failures',
        value: failureCount,
        color: Colors.orange,
      ),
      _OutcomeStatDefinition(
        icon: Icons.close,
        label: 'Deaths',
        value: deathCount,
        color: theme.colorScheme.error,
      ),
    ];

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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Adventure Statistics',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
              Text(
                'Total Runs: $totalStories',
                style: theme.textTheme.labelMedium?.copyWith(
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final availableWidth = constraints.maxWidth;
              const spacing = 12.0;
              final isNarrow = availableWidth < 360;
              final itemWidth = isNarrow
                  ? availableWidth
                  : (availableWidth - spacing) / 2;

              return Wrap(
                spacing: spacing,
                runSpacing: spacing,
                children: stats
                    .map(
                      (stat) => _OutcomeStatCard(
                        width: itemWidth,
                        icon: stat.icon,
                        label: stat.label,
                        value: stat.value,
                        color: stat.color,
                      ),
                    )
                    .toList(),
              );
            },
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              _SummaryChip(
                icon: Icons.timer,
                label: 'Total Time',
                value: _formatDuration(totalTime),
              ),
              _SummaryChip(
                icon: Icons.insights,
                label: 'Avg Duration',
                value: _formatDuration(averageDuration),
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

class _OutcomeStatDefinition {
  final IconData icon;
  final String label;
  final int value;
  final Color color;

  const _OutcomeStatDefinition({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });
}

class _OutcomeStatCard extends StatelessWidget {
  final double width;
  final IconData icon;
  final String label;
  final int value;
  final Color color;

  const _OutcomeStatCard({
    required this.width,
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      width: width,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface.withValues(alpha: 0.7),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.4), width: 1),
        ),
        child: Row(
          children: [
            Icon(icon, size: 20, color: color),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant.withValues(
                        alpha: 0.85,
                      ),
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    value.toString(),
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: color,
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
}

class _SummaryChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _SummaryChip({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Chip(
      avatar: Icon(icon, size: 18, color: theme.colorScheme.primary),
      label: Text('$label: $value'),
      backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.7),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: theme.colorScheme.outline.withValues(alpha: 0.2),
        ),
      ),
    );
  }
}

class _HistoryEntryCard extends StatelessWidget {
  final StoryHistoryEntry entry;
  final VoidCallback? onTap;

  const _HistoryEntryCard({required this.entry, this.onTap});

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
                  _OutcomeIcon(entry: entry),
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
                  _OutcomeBadge(entry: entry),
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
                    return _RewardChip(type: reward.key, value: reward.value);
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
  final StoryHistoryEntry entry;

  const _OutcomeIcon({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final outcomeType = normalizedOutcomeType(entry.outcome) ?? 'unknown';
    final color = outcomeAccentColor(theme, entry.outcome);

    IconData icon;
    switch (outcomeType) {
      case 'death':
        icon = Icons.dangerous;
        break;
      case 'failure':
      case 'failed':
        icon = Icons.cancel;
        break;
      default:
        icon = Icons.check_circle;
        break;
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
  final StoryHistoryEntry entry;

  const _OutcomeBadge({required this.entry});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = outcomeAccentColor(theme, entry.outcome);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color),
      ),
      child: Text(
        entry.displayOutcome.toUpperCase(),
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
          Text(label, style: TextStyle(fontSize: 12, color: color)),
        ],
      ),
    );
  }
}

class _RewardChip extends StatelessWidget {
  final String type;
  final int value;

  const _RewardChip({required this.type, required this.value});

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

  String get outcomeCategory {
    final normalized = outcome.toLowerCase();
    if (normalized == 'exceptional' ||
        normalized == 'success' ||
        normalized == 'minimal') {
      return 'success';
    }
    if (normalized == 'normal') {
      return 'normal';
    }
    if (normalized == 'failure' || normalized == 'death') {
      return 'failure';
    }
    return normalized;
  }

  String get displayOutcome {
    switch (outcome.toLowerCase()) {
      case 'exceptional':
        return 'Exceptional Success';
      case 'minimal':
        return 'Minimal Success';
      case 'success':
        return 'Success';
      case 'normal':
        return 'Normal Progress';
      case 'failure':
        return 'Failure';
      case 'death':
        return 'Death';
      default:
        return outcome.isEmpty ? 'Unknown' : outcome;
    }
  }
}
