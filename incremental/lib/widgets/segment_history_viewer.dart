import 'package:flutter/material.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/utils/outcome_colors.dart';

class SegmentHistoryViewer extends StatefulWidget {
  final String characterId;

  const SegmentHistoryViewer({super.key, required this.characterId});

  @override
  State<SegmentHistoryViewer> createState() => _SegmentHistoryViewerState();
}

class _SegmentHistoryViewerState extends State<SegmentHistoryViewer> {
  List<Map<String, dynamic>>? _history;
  bool _isLoading = true;
  String? _errorMessage;
  String? _expandedSegmentId;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final apiService = ApiService(authService: AuthService.instance);
      final history = await apiService.getSegmentHistory(
        characterId: widget.characterId,
      );

      setState(() {
        _history = history;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Adventure History'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loadHistory),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              'Failed to load history',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              _errorMessage!,
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _loadHistory,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_history == null || _history!.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.history,
              size: 64,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 16),
            Text(
              'No adventure history yet',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Complete some story segments to see your history',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _history!.length,
      itemBuilder: (context, index) {
        final segment = _history![index];
        return _buildHistoryCard(segment);
      },
    );
  }

  Widget _buildHistoryCard(Map<String, dynamic> segment) {
    final theme = Theme.of(context);
    final segmentId = segment['ActiveSegmentID'] as String;
    final isExpanded = _expandedSegmentId == segmentId;
    final segmentType = segment['SegmentType'] as String? ?? 'unknown';
    final storyTitle = segment['StoryTitle'] as String? ?? 'Unknown Story';
    final outcome = segment['Outcome'] as String?;
    final decision = segment['Decision'] as String?;
    final clientEvents = segment['ClientEvents'] as List<dynamic>?;
    final completedAt = segment['CompletedAt'] as String?;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Column(
        children: [
          ListTile(
            leading: CircleAvatar(
              backgroundColor: _getSegmentColor(segmentType, outcome),
              child: Icon(_getSegmentIcon(segmentType), color: Colors.white),
            ),
            title: Text(
              storyTitle,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _formatSegmentType(segmentType),
                  style: theme.textTheme.bodySmall,
                ),
                if (completedAt != null)
                  Text(
                    _formatCompletedTime(completedAt),
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (outcome != null)
                  Chip(
                    label: Text(
                      _formatOutcome(outcome),
                      style: const TextStyle(fontSize: 12),
                    ),
                    backgroundColor: outcomeAccentColor(
                      theme,
                      outcome,
                    ).withValues(alpha: 0.2),
                    side: BorderSide(
                      color: outcomeAccentColor(theme, outcome),
                      width: 1,
                    ),
                  ),
                IconButton(
                  icon: Icon(
                    isExpanded ? Icons.expand_less : Icons.expand_more,
                  ),
                  onPressed: () {
                    setState(() {
                      _expandedSegmentId = isExpanded ? null : segmentId;
                    });
                  },
                ),
              ],
            ),
            onTap: () {
              setState(() {
                _expandedSegmentId = isExpanded ? null : segmentId;
              });
            },
          ),
          if (isExpanded) ...[
            const Divider(height: 1),
            Container(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (decision != null) ...[
                    _buildDetailRow('Decision', decision),
                    const SizedBox(height: 12),
                  ],
                  if (clientEvents != null && clientEvents.isNotEmpty) ...[
                    Text(
                      'Events',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ...clientEvents.map(
                      (event) =>
                          _buildEventSummary(event as Map<String, dynamic>),
                    ),
                  ],
                  ..._buildItemsList(segment, theme),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$label: ', style: const TextStyle(fontWeight: FontWeight.bold)),
        Expanded(child: Text(value)),
      ],
    );
  }

  Widget _buildEventSummary(Map<String, dynamic> event) {
    final eventType =
        event['eventType'] as String? ?? event['EventType'] as String?;
    final title =
        event['title'] as String? ?? event['Title'] as String? ?? 'Event';
    final description =
        event['description'] as String? ??
        event['Description'] as String? ??
        '';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(
          context,
        ).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            _getEventIcon(eventType),
            size: 20,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                if (description.isNotEmpty)
                  Text(
                    description,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _getSegmentIcon(String segmentType) {
    switch (segmentType) {
      case 'decision':
        return Icons.fork_right;
      case 'mechanical':
        return Icons.settings;
      default:
        return Icons.help_outline;
    }
  }

  IconData _getEventIcon(String? eventType) {
    if (eventType == null) return Icons.circle;

    if (eventType.startsWith('combat')) {
      return Icons.shield;
    }

    switch (eventType) {
      case 'skillCheck':
        return Icons.psychology;
      case 'movement':
        return Icons.directions_walk;
      case 'discovery':
        return Icons.explore;
      default:
        return Icons.circle;
    }
  }

  Color _getSegmentColor(String segmentType, String? outcome) {
    if (outcome == 'exceptional') {
      return Colors.purple;
    }

    switch (segmentType) {
      case 'decision':
        return Colors.blue;
      case 'mechanical':
        return Colors.orange;
      default:
        return Colors.grey;
    }
  }

  String _formatSegmentType(String type) {
    return '${type[0].toUpperCase()}${type.substring(1)} Segment';
  }

  String _formatOutcome(String outcome) {
    return outcome[0].toUpperCase() + outcome.substring(1);
  }

  String _formatCompletedTime(String isoString) {
    final date = DateTime.parse(isoString);
    final now = DateTime.now();
    final difference = now.difference(date);

    if (difference.inDays > 0) {
      return '${difference.inDays} day${difference.inDays > 1 ? 's' : ''} ago';
    } else if (difference.inHours > 0) {
      return '${difference.inHours} hour${difference.inHours > 1 ? 's' : ''} ago';
    } else if (difference.inMinutes > 0) {
      return '${difference.inMinutes} minute${difference.inMinutes > 1 ? 's' : ''} ago';
    } else {
      return 'Just now';
    }
  }

  List<Widget> _buildItemsList(Map<String, dynamic> segment, ThemeData theme) {
    final characterUpdates =
        segment['CharacterUpdates'] as Map<String, dynamic>?;
    if (characterUpdates == null) {
      return [];
    }

    final grantedItemIDs = characterUpdates['GrantedItemIDs'] as List<dynamic>?;
    if (grantedItemIDs == null || grantedItemIDs.isEmpty) {
      return [];
    }

    return [
      const SizedBox(height: 12),
      Text(
        'Items Received',
        style: theme.textTheme.titleSmall?.copyWith(
          fontWeight: FontWeight.bold,
        ),
      ),
      const SizedBox(height: 8),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: grantedItemIDs.map((itemId) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest.withValues(
                alpha: 0.5,
              ),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: theme.colorScheme.outline.withValues(alpha: 0.5),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.category_outlined,
                  size: 14,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: 4),
                Text(
                  _formatItemId(itemId.toString()),
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          );
        }).toList(),
      ),
    ];
  }

  String _formatItemId(String itemId) {
    if (itemId.length > 8) {
      return 'Item ${itemId.substring(itemId.length - 8)}';
    }
    return 'Item $itemId';
  }
}
