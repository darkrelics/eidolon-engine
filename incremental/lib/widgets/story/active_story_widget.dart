import 'dart:async';
import 'package:flutter/material.dart';
import '../../models/character.dart';

/// Widget displaying the active story with segments
class ActiveStoryWidget extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onRestSegment;
  final VoidCallback? onContinue;

  const ActiveStoryWidget({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onRestSegment,
    this.onContinue,
  });

  @override
  State<ActiveStoryWidget> createState() => _ActiveStoryWidgetState();
}

class _ActiveStoryWidgetState extends State<ActiveStoryWidget> {
  @override
  void initState() {
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final storyData = widget.character.storyState?['Story'] as Map<String, dynamic>?;
    final segmentData = widget.character.storyState?['ActiveSegment'] as Map<String, dynamic>?;

    if (storyData == null && segmentData == null) {
      return Center(
        child: Text(
          'No active story',
          style: theme.textTheme.titleMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Story Card
          if (storyData != null) ...[
            _StoryCard(story: storyData),
            const SizedBox(height: 16),
          ],

          // Action Buttons
          _ActionButtons(
            onRest: widget.onRestSegment,
            onAbandon: widget.onAbandonStory,
          ),
          const SizedBox(height: 20),

          // Active Segment
          if (segmentData != null) ...[
            _SimpleSegmentCard(
              segment: segmentData,
              isActive: true,
              onDecisionSelect: widget.onDecisionSelect,
            ),
            const SizedBox(height: 20),
          ],

          // Previous Segments (show in reverse order - newest first)
          if (widget.segmentHistory.isNotEmpty) ...[  
            Text(
              'Previous Segments',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            ...widget.segmentHistory.reversed.map((segment) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _SimpleSegmentCard(
                segment: segment,
                isActive: false,
              ),
            )),
          ],
        ],
      ),
    );
  }
}

class _StoryCard extends StatelessWidget {
  final Map<String, dynamic> story;

  const _StoryCard({required this.story});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = story['Title'] ?? 'Unknown Story';
    final description = story['Description'] ?? '';
    final type = story['Type'] ?? 'story';
    final progress = story['Progress'] as Map<String, dynamic>?;

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.colorScheme.primaryContainer,
            theme.colorScheme.primaryContainer.withValues(alpha: 0.7),
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
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.auto_stories,
                  color: theme.colorScheme.onPrimaryContainer,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleLarge?.copyWith(
                      color: theme.colorScheme.onPrimaryContainer,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                _TypeBadge(type: type),
              ],
            ),
            if (description.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                description,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ],
            if (progress != null) ...[
              const SizedBox(height: 12),
              _ProgressIndicator(progress: progress),
            ],
          ],
        ),
      ),
    );
  }
}

class _TypeBadge extends StatelessWidget {
  final String type;

  const _TypeBadge({required this.type});

  @override
  Widget build(BuildContext context) {
    final color = _getTypeColor(type);
    final icon = _getTypeIcon(type);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
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
              fontSize: 11,
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
        return Colors.orange;
      case 'repeatable':
        return Colors.green;
      default:
        return Colors.blueGrey;
    }
  }

  IconData _getTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Icons.looks_one;
      case 'daily':
        return Icons.today;
      case 'repeatable':
        return Icons.replay;
      default:
        return Icons.auto_stories;
    }
  }
}

class _ProgressIndicator extends StatelessWidget {
  final Map<String, dynamic> progress;

  const _ProgressIndicator({required this.progress});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final current = progress['Current'] ?? 0;
    final total = progress['Total'] ?? 1;
    final percentage = total > 0 ? (current / total).clamp(0.0, 1.0) : 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Progress',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.8),
              ),
            ),
            Text(
              '$current / $total segments',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.8),
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
            backgroundColor: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.2),
            valueColor: AlwaysStoppedAnimation<Color>(
              theme.colorScheme.onPrimaryContainer,
            ),
            minHeight: 8,
          ),
        ),
      ],
    );
  }
}

class _ActionButtons extends StatelessWidget {
  final VoidCallback? onRest;
  final VoidCallback? onAbandon;

  const _ActionButtons({this.onRest, this.onAbandon});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (onRest != null)
          OutlinedButton.icon(
            onPressed: onRest,
            icon: const Icon(Icons.hotel),
            label: const Text('Rest'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            ),
          ),
        if (onRest != null && onAbandon != null)
          const SizedBox(width: 12),
        if (onAbandon != null)
          OutlinedButton.icon(
            onPressed: onAbandon,
            icon: const Icon(Icons.exit_to_app),
            label: const Text('Abandon'),
            style: OutlinedButton.styleFrom(
              foregroundColor: theme.colorScheme.error,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            ),
          ),
      ],
    );
  }
}

// New simplified segment card
class _SimpleSegmentCard extends StatelessWidget {
  final Map<String, dynamic> segment;
  final bool isActive;
  final Function(String)? onDecisionSelect;

  const _SimpleSegmentCard({
    required this.segment,
    required this.isActive,
    this.onDecisionSelect,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final segmentType = segment['SegmentType'] ?? 'mechanical';
    final shortStatus = segment['ShortStatus'] ?? 'Processing...';
    final defaultStatus = segment['DefaultStatus'] ?? '';
    final outcome = segment['Outcome'];
    final endTime = segment['EndTime'];
    
    // Determine card color based on outcome
    Color cardColor;
    IconData icon;
    Color backgroundColor;
    
    // Check outcome for color
    final outcomeStr = outcome is String ? outcome : outcome?['Type'];
    if (outcomeStr != null) {
      switch (outcomeStr.toLowerCase()) {
        case 'death':
          cardColor = Colors.black;
          backgroundColor = Colors.black.withValues(alpha: 0.15);
          icon = Icons.dangerous;
          break;
        case 'failure':
        case 'failed':
          cardColor = Colors.red;
          backgroundColor = Colors.red.withValues(alpha: 0.1);
          icon = Icons.cancel;
          break;
        default:
          // All other outcomes (exceptional, normal, minimal, etc.) are green
          cardColor = Colors.green;
          backgroundColor = Colors.green.withValues(alpha: 0.1);
          icon = Icons.check_circle;
      }
    } else {
      // No outcome yet - use default theme colors
      cardColor = theme.colorScheme.primary;
      backgroundColor = theme.colorScheme.surface;
      icon = isActive ? Icons.play_circle_outline : Icons.check_circle_outline;
    }

    return Card(
      elevation: isActive ? 2 : 0,
      color: backgroundColor,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isActive ? cardColor.withValues(alpha: 0.3) : Colors.transparent,
          width: isActive ? 2 : 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header row with ShortStatus as title
            Row(
              children: [
                Icon(icon, color: isActive ? cardColor : theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    shortStatus,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: isActive ? cardColor : null,
                    ),
                  ),
                ),
              ],
            ),
            
            // Show timer and DefaultStatus for active segments
            if (isActive && endTime != null) ...[
              const SizedBox(height: 12),
              _SegmentTimer(
                endTime: endTime,
                duration: segment['SegmentDuration'] ?? segment['Duration'],
              ),
              if (defaultStatus.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  defaultStatus,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
            
            // Show outcome for completed segments
            if (outcome != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(
                    Icons.workspace_premium,
                    size: 16,
                    color: _getOutcomeColor(outcome),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'Outcome: ${_formatOutcome(outcome)}',
                    style: TextStyle(
                      color: _getOutcomeColor(outcome),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ],
            
            // Decision options for decision segments
            if (segmentType == 'decision' && isActive && segment['DecisionOptions'] != null) ...[
              const SizedBox(height: 12),
              ...((segment['DecisionOptions'] as Map<String, dynamic>).entries.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: FilledButton(
                    onPressed: () => onDecisionSelect?.call(entry.key),
                    child: Text(entry.key.replaceAll('-', ' ').toUpperCase()),
                  ),
                ),
              )),
            ],
          ],
        ),
      ),
    );
  }
  
  Color _getOutcomeColor(dynamic outcome) {
    final outcomeStr = outcome is String ? outcome : outcome['Type'] ?? 'normal';
    switch (outcomeStr.toLowerCase()) {
      case 'exceptional':
        return Colors.purple;
      case 'normal':
        return Colors.green;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }
  
  String _formatOutcome(dynamic outcome) {
    final outcomeStr = outcome is String ? outcome : outcome['Type'] ?? 'normal';
    return outcomeStr[0].toUpperCase() + outcomeStr.substring(1);
  }
}

// Timer widget for active segments
class _SegmentTimer extends StatefulWidget {
  final String endTime;
  final dynamic duration;
  
  const _SegmentTimer({
    required this.endTime,
    this.duration,
  });
  
  @override
  State<_SegmentTimer> createState() => _SegmentTimerState();
}

class _SegmentTimerState extends State<_SegmentTimer> {
  late Timer _timer;
  int _remainingSeconds = 0;
  int _totalDuration = 60;
  
  @override
  void initState() {
    super.initState();
    // Get total duration from segment data
    if (widget.duration != null) {
      _totalDuration = widget.duration is int ? widget.duration : int.tryParse(widget.duration.toString()) ?? 60;
    }
    _updateRemainingTime();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _updateRemainingTime());
  }
  
  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }
  
  void _updateRemainingTime() {
    if (!mounted) return;
    
    // Parse ISO 8601 timestamp
    final endDateTime = DateTime.parse(widget.endTime);
    final now = DateTime.now();
    final difference = endDateTime.difference(now);
    
    setState(() {
      _remainingSeconds = difference.inSeconds > 0 ? difference.inSeconds : 0;
    });
  }
  
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final minutes = _remainingSeconds ~/ 60;
    final seconds = _remainingSeconds % 60;
    final progress = _totalDuration > 0 
        ? (_totalDuration - _remainingSeconds) / _totalDuration 
        : 0.0;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Progress bar
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: progress.clamp(0.0, 1.0),
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
            valueColor: AlwaysStoppedAnimation<Color>(
              theme.colorScheme.primary,
            ),
            minHeight: 6,
          ),
        ),
        const SizedBox(height: 8),
        // Timer display
        Row(
          children: [
            Icon(Icons.timer, size: 16, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: 4),
            Text(
              '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}',
              style: TextStyle(
                fontFamily: 'monospace',
                color: theme.colorScheme.onSurfaceVariant,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ],
    );
  }
}