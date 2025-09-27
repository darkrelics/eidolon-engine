import 'package:flutter/material.dart';

import '../../models/story.dart';
import '../../models/character.dart';

/// Widget displaying available stories for selection
class AvailableStoriesWidget extends StatefulWidget {
  final Character character;
  final Function(StoryMetadata)? onStorySelect;
  final bool isLoading;

  const AvailableStoriesWidget({
    super.key,
    required this.character,
    this.onStorySelect,
    this.isLoading = false,
  });

  @override
  State<AvailableStoriesWidget> createState() => _AvailableStoriesWidgetState();
}

class _AvailableStoriesWidgetState extends State<AvailableStoriesWidget> {
  String _filterType = 'all';
  String _sortBy = 'availability';

  List<StoryMetadata> get _stories {
    if (widget.character.availableStoriesDetails == null) {
      return [];
    }

    return widget.character.availableStoriesDetails!
        .map((story) => StoryMetadata.fromJson(story))
        .toList();
  }

  List<StoryMetadata> get _filteredStories {
    var stories = _stories;

    // Apply filter
    if (_filterType != 'all') {
      stories = stories
          .where(
            (story) => story.type.toLowerCase() == _filterType.toLowerCase(),
          )
          .toList();
    }

    // Apply sort
    switch (_sortBy) {
      case 'availability':
        stories.sort((a, b) {
          if (a.available && !b.available) return -1;
          if (!a.available && b.available) return 1;
          return a.cooldownRemaining.compareTo(b.cooldownRemaining);
        });
        break;
      case 'duration':
        stories.sort(
          (a, b) => a.estimatedDuration.compareTo(b.estimatedDuration),
        );
        break;
      case 'name':
        stories.sort((a, b) => a.title.compareTo(b.title));
        break;
    }

    return stories;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_stories.isEmpty) {
      return _buildEmptyState(context);
    }

    return Column(
      children: [
        // Filters and Sort
        _FilterBar(
          filterType: _filterType,
          sortBy: _sortBy,
          onFilterChanged: (value) {
            setState(() {
              _filterType = value;
            });
          },
          onSortChanged: (value) {
            setState(() {
              _sortBy = value;
            });
          },
        ),
        const SizedBox(height: 16),

        // Story Grid/List
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isWide = constraints.maxWidth > 600;

              if (isWide) {
                // Grid layout for wide screens
                return _buildGridView();
              } else {
                // List layout for narrow screens
                return _buildListView();
              }
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
            Icons.library_books_outlined,
            size: 80,
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 16),
          Text(
            'No Stories Available',
            style: theme.textTheme.headlineSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Check back later for new adventures',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGridView() {
    return GridView.builder(
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 400,
        childAspectRatio: 1.5,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
      ),
      itemCount: _filteredStories.length,
      itemBuilder: (context, index) {
        final story = _filteredStories[index];
        return _StoryCard(
          story: story,
          onTap: widget.onStorySelect != null
              ? () => widget.onStorySelect!(story)
              : null,
          isGrid: true,
        );
      },
    );
  }

  Widget _buildListView() {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _filteredStories.length,
      itemBuilder: (context, index) {
        final story = _filteredStories[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: _StoryCard(
            story: story,
            onTap: widget.onStorySelect != null
                ? () => widget.onStorySelect!(story)
                : null,
            isGrid: false,
          ),
        );
      },
    );
  }
}

class _FilterBar extends StatelessWidget {
  final String filterType;
  final String sortBy;
  final ValueChanged<String> onFilterChanged;
  final ValueChanged<String> onSortChanged;

  const _FilterBar({
    required this.filterType,
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
          // Filter Chips
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FilterChip(
                    label: 'All',
                    value: 'all',
                    selected: filterType == 'all',
                    onSelected: onFilterChanged,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Daily',
                    value: 'daily',
                    selected: filterType == 'daily',
                    onSelected: onFilterChanged,
                    color: Colors.blue,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'One-Time',
                    value: 'one-time',
                    selected: filterType == 'one-time',
                    onSelected: onFilterChanged,
                    color: Colors.purple,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Repeatable',
                    value: 'repeatable',
                    selected: filterType == 'repeatable',
                    onSelected: onFilterChanged,
                    color: Colors.green,
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
                value: 'availability',
                child: Row(
                  children: const [
                    Icon(Icons.check_circle, size: 18),
                    SizedBox(width: 8),
                    Text('Availability'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'duration',
                child: Row(
                  children: const [
                    Icon(Icons.schedule, size: 18),
                    SizedBox(width: 8),
                    Text('Duration'),
                  ],
                ),
              ),
              PopupMenuItem(
                value: 'name',
                child: Row(
                  children: const [
                    Icon(Icons.sort_by_alpha, size: 18),
                    SizedBox(width: 8),
                    Text('Name'),
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

class _FilterChip extends StatelessWidget {
  final String label;
  final String value;
  final bool selected;
  final ValueChanged<String> onSelected;
  final Color? color;

  const _FilterChip({
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
      ),
    );
  }
}

class _StoryCard extends StatelessWidget {
  final StoryMetadata story;
  final VoidCallback? onTap;
  final bool isGrid;

  const _StoryCard({required this.story, this.onTap, required this.isGrid});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isAvailable = story.available;

    return Card(
      elevation: isAvailable ? 4 : 1,
      child: InkWell(
        onTap: isAvailable ? onTap : null,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            gradient: isAvailable
                ? LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      theme.colorScheme.surface,
                      theme.colorScheme.primaryContainer.withValues(alpha: 0.3),
                    ],
                  )
                : null,
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        story.title,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isAvailable
                              ? null
                              : theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: isGrid ? 1 : 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    _StoryTypeBadge(type: story.type),
                  ],
                ),
                const SizedBox(height: 8),

                // Description
                Expanded(
                  child: Text(
                    story.description,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: isAvailable
                          ? theme.colorScheme.onSurfaceVariant
                          : theme.colorScheme.onSurfaceVariant.withValues(
                              alpha: 0.6,
                            ),
                    ),
                    maxLines: isGrid ? 2 : 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(height: 12),

                // Footer
                Row(
                  children: [
                    // Duration
                    Icon(
                      Icons.schedule,
                      size: 16,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _formatDuration(story.estimatedDuration),
                      style: theme.textTheme.bodySmall,
                    ),
                    const Spacer(),
                    // Availability Status
                    _AvailabilityIndicator(
                      available: isAvailable,
                      cooldown: story.cooldownRemaining,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDuration(int seconds) {
    if (seconds < 60) return '< 1 min';
    if (seconds < 3600) return '${seconds ~/ 60} min';
    final hours = seconds ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;
    return minutes > 0 ? '${hours}h ${minutes}m' : '${hours}h';
  }
}

class _StoryTypeBadge extends StatelessWidget {
  final String type;

  const _StoryTypeBadge({required this.type});

  @override
  Widget build(BuildContext context) {
    final color = _getTypeColor(type);
    final icon = _getTypeIcon(type);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            type.toUpperCase(),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: color,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Color _getTypeColor(String type) {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Colors.purple;
      case 'daily':
        return Colors.blue;
      case 'repeatable':
        return Colors.green;
      case 'main':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Icons.looks_one;
      case 'daily':
        return Icons.today;
      case 'repeatable':
        return Icons.all_inclusive;
      case 'main':
        return Icons.star;
      default:
        return Icons.help_outline;
    }
  }
}

class _AvailabilityIndicator extends StatelessWidget {
  final bool available;
  final int cooldown;

  const _AvailabilityIndicator({
    required this.available,
    required this.cooldown,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (!available && cooldown > 0) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.timer_off, size: 16, color: theme.colorScheme.error),
          const SizedBox(width: 4),
          Text(
            _formatCooldown(cooldown),
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.error,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      );
    } else if (available) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.green.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.green),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.play_circle_outline, size: 16, color: Colors.green),
            const SizedBox(width: 4),
            Text(
              'AVAILABLE',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.bold,
                color: Colors.green,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
      );
    } else {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.lock_outline,
            size: 16,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 4),
          Text(
            'LOCKED',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      );
    }
  }

  String _formatCooldown(int seconds) {
    if (seconds < 60) return '${seconds}s';
    if (seconds < 3600) return '${seconds ~/ 60}m';
    if (seconds < 86400) return '${seconds ~/ 3600}h';
    return '${seconds ~/ 86400}d';
  }
}
