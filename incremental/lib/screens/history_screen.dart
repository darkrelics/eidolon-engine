import 'package:flutter/material.dart';

/// Story history data
class StoryHistory {
  final String characterID;
  final String storyID;
  final String storyTitle;
  final String? startedAt;
  final String? finishedAt;
  final String storyType;
  final List<dynamic> segmentHistory;
  final String? finalOutcome;
  final int abandonedCount;

  StoryHistory({
    required this.characterID,
    required this.storyID,
    required this.storyTitle,
    this.startedAt,
    this.finishedAt,
    required this.storyType,
    required this.segmentHistory,
    this.finalOutcome,
    required this.abandonedCount,
  });

  factory StoryHistory.fromJson(Map<String, dynamic> json) {
    return StoryHistory(
      characterID: json['CharacterID'] as String,
      storyID: json['StoryID'] as String,
      storyTitle: json['StoryTitle'] as String,
      startedAt: json['StartedAt'] as String?,
      finishedAt: json['FinishedAt'] as String?,
      storyType: json['StoryType'] as String,
      segmentHistory: json['SegmentHistory'] as List<dynamic>? ?? [],
      finalOutcome: json['FinalOutcome'] as String?,
      abandonedCount: json['AbandonedCount'] as int? ?? 0,
    );
  }

  bool get isCompleted => finalOutcome != null && finalOutcome != 'abandoned';
}

/// Screen to display completed story history
class HistoryScreen extends StatefulWidget {
  final String characterId;

  const HistoryScreen({
    super.key,
    required this.characterId,
  });

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  Future<List<StoryHistory>>? _historyFuture;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  void _loadHistory() {
    setState(() {
      _historyFuture = _fetchHistory();
    });
  }

  Future<List<StoryHistory>> _fetchHistory() async {
    try {
      // Note: This endpoint would need to be implemented in the API
      // For now, returning empty list
      // final response = await _apiService.getStoryHistory(widget.characterId);
      // return response.map((h) => StoryHistory.fromJson(h)).toList();
      return [];
    } catch (e) {
      // Error is already shown in the UI, just log it
      debugPrint('Error loading history: $e');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Story History'),
        backgroundColor: theme.colorScheme.inversePrimary,
      ),
      body: FutureBuilder<List<StoryHistory>>(
        future: _historyFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.error_outline,
                    size: 64,
                    color: theme.colorScheme.error,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Failed to load history',
                    style: theme.textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    snapshot.error.toString(),
                    style: theme.textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _loadHistory,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          final histories = snapshot.data ?? [];

          if (histories.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.history,
                    size: 64,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'No Story History',
                    style: theme.textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Complete some stories to see them here!',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: histories.length,
            itemBuilder: (context, index) {
              final history = histories[index];
              return _HistoryCard(history: history);
            },
          );
        },
      ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  final StoryHistory history;

  const _HistoryCard({required this.history});

  IconData _getOutcomeIcon() {
    switch (history.finalOutcome?.toLowerCase()) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
        return Icons.error_outline;
      case 'minimal':
        return Icons.check_circle_outline;
      case 'normal':
        return Icons.check_circle;
      case 'exceptional':
        return Icons.star;
      case 'abandoned':
        return Icons.cancel;
      default:
        return Icons.help_outline;
    }
  }

  Color _getOutcomeColor(BuildContext context) {
    final theme = Theme.of(context);
    switch (history.finalOutcome?.toLowerCase()) {
      case 'death':
        return theme.colorScheme.error;
      case 'failure':
        return Colors.orange;
      case 'minimal':
        return Colors.yellow.shade700;
      case 'normal':
        return theme.colorScheme.primary;
      case 'exceptional':
        return Colors.green;
      case 'abandoned':
        return theme.colorScheme.onSurfaceVariant;
      default:
        return theme.colorScheme.onSurface;
    }
  }

  String _formatDate(String? dateStr) {
    if (dateStr == null) return 'Unknown';
    try {
      final date = DateTime.parse(dateStr);
      return '${date.month}/${date.day}/${date.year}';
    } catch (e) {
      return dateStr;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final outcomeColor = _getOutcomeColor(context);

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    history.storyTitle,
                    style: theme.textTheme.titleLarge,
                  ),
                ),
                Icon(
                  _getOutcomeIcon(),
                  color: outcomeColor,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Chip(
                  label: Text(history.storyType),
                  visualDensity: VisualDensity.compact,
                ),
                const SizedBox(width: 8),
                if (history.finalOutcome != null)
                  Chip(
                    label: Text(history.finalOutcome!.toUpperCase()),
                    backgroundColor: outcomeColor.withValues(alpha: 0.2),
                    labelStyle: TextStyle(color: outcomeColor),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Started: ${_formatDate(history.startedAt)}',
              style: theme.textTheme.bodyMedium,
            ),
            if (history.finishedAt != null)
              Text(
                'Finished: ${_formatDate(history.finishedAt)}',
                style: theme.textTheme.bodyMedium,
              ),
            if (history.abandonedCount > 0)
              Text(
                'Abandoned ${history.abandonedCount} time${history.abandonedCount > 1 ? 's' : ''}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            if (history.segmentHistory.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                '${history.segmentHistory.length} segments completed',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}