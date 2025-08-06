import 'package:flutter/material.dart';
import '../../models/character.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../unified/decision_widget.dart';
import '../segments/mechanical_progress.dart';
import '../segments/outcome_display.dart';

/// Widget displaying the active story with segments
class ActiveStoryWidget extends StatefulWidget {
  final Character character;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onRestSegment;
  final VoidCallback? onContinue;

  const ActiveStoryWidget({
    super.key,
    required this.character,
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onRestSegment,
    this.onContinue,
  });

  @override
  State<ActiveStoryWidget> createState() => _ActiveStoryWidgetState();
}

class _ActiveStoryWidgetState extends State<ActiveStoryWidget> {
  bool _showSegmentHistory = false;
  List<Map<String, dynamic>> _segmentHistory = [];

  @override
  void initState() {
    super.initState();
    _loadSegmentHistory();
  }

  void _loadSegmentHistory() {
    // In a real implementation, this would load from API or local storage
    // For now, we'll use placeholder data if available
    if (widget.character.storyState?['SegmentHistory'] != null) {
      _segmentHistory = List<Map<String, dynamic>>.from(
        widget.character.storyState!['SegmentHistory'],
      );
    }
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
            _StoryCard(story: storyData).animate()
              .fadeIn(duration: 300.ms)
              .slideY(begin: -0.1, end: 0),
            const SizedBox(height: 16),
          ],

          // Action Buttons
          _ActionButtons(
            onRest: widget.onRestSegment,
            onAbandon: widget.onAbandonStory,
          ).animate()
            .fadeIn(delay: 100.ms, duration: 300.ms),
          const SizedBox(height: 20),

          // Current Segment
          if (segmentData != null) ...[
            _SectionHeader(
              title: 'Current Segment',
              icon: Icons.play_circle_outline,
            ),
            const SizedBox(height: 12),
            _CurrentSegment(
              segment: segmentData,
              onDecisionSelect: widget.onDecisionSelect,
              onContinue: widget.onContinue,
            ).animate()
              .fadeIn(delay: 200.ms, duration: 300.ms)
              .slideX(begin: 0.1, end: 0),
            const SizedBox(height: 20),
          ],

          // Segment History
          _SectionHeader(
            title: 'Previous Segments',
            icon: Icons.history,
            trailing: IconButton(
              icon: Icon(_showSegmentHistory
                  ? Icons.expand_less
                  : Icons.expand_more),
              onPressed: () {
                setState(() {
                  _showSegmentHistory = !_showSegmentHistory;
                });
              },
            ),
          ),
          const SizedBox(height: 12),
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            child: _showSegmentHistory
                ? _SegmentHistory(segments: _segmentHistory)
                : Text(
                    'Tap to view segment history',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
          ),
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

class _SectionHeader extends StatelessWidget {
  final String title;
  final IconData icon;
  final Widget? trailing;

  const _SectionHeader({
    required this.title,
    required this.icon,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.primary),
          const SizedBox(width: 8),
          Text(
            title,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.primary,
            ),
          ),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

class _CurrentSegment extends StatelessWidget {
  final Map<String, dynamic> segment;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onContinue;

  const _CurrentSegment({
    required this.segment,
    this.onDecisionSelect,
    this.onContinue,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final segmentType = segment['SegmentType'] ?? 'unknown';
    final status = segment['ShortStatus'] ?? 'Processing...';
    final longStatus = segment['LongStatus'] ?? '';
    final choices = segment['Choices'] as List?;
    final outcome = segment['Outcome'] as Map<String, dynamic>?;
    final processingStatus = segment['ProcessingStatus'];

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: theme.colorScheme.primary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Segment Header
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.1),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(11),
                topRight: Radius.circular(11),
              ),
            ),
            child: Row(
              children: [
                _SegmentTypeIcon(type: segmentType),
                const SizedBox(width: 8),
                Text(
                  _formatSegmentType(segmentType),
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                if (processingStatus != null)
                  _ProcessingStatusBadge(status: processingStatus),
              ],
            ),
          ),
          
          // Segment Content
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  status,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (longStatus.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    longStatus,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
                
                // Decision Choices
                if (segmentType == 'decision' && choices != null && choices.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  ...choices.map((choice) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _DecisionButton(
                      choice: choice,
                      onSelect: onDecisionSelect,
                    ),
                  )),
                ],
                
                // Mechanical Processing
                if (segmentType == 'mechanical') ...[
                  const SizedBox(height: 16),
                  MechanicalSegmentProgress(
                    status: status,
                    processingStatus: processingStatus,
                    estimatedDuration: const Duration(minutes: 1),
                  ),
                ],
                
                // Outcome Display
                if (outcome != null) ...[
                  const SizedBox(height: 16),
                  AnimatedOutcomeDisplay(
                    outcome: outcome,
                    onDismiss: onContinue,
                  ),
                ],
                
                // Continue Button
                if (segmentType == 'rest' || 
                    (segmentType == 'mechanical' && processingStatus == 'processed')) ...[
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: onContinue,
                    icon: const Icon(Icons.arrow_forward),
                    label: const Text('Continue'),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatSegmentType(String type) {
    return type[0].toUpperCase() + type.substring(1);
  }
}

class _SegmentTypeIcon extends StatelessWidget {
  final String type;

  const _SegmentTypeIcon({required this.type});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    IconData icon;
    Color color;

    switch (type.toLowerCase()) {
      case 'decision':
        icon = Icons.psychology;
        color = Colors.blue;
        break;
      case 'mechanical':
        icon = Icons.settings;
        color = Colors.orange;
        break;
      case 'rest':
        icon = Icons.hotel;
        color = Colors.green;
        break;
      case 'narrative':
        icon = Icons.auto_stories;
        color = Colors.purple;
        break;
      default:
        icon = Icons.help_outline;
        color = theme.colorScheme.onSurfaceVariant;
    }

    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Icon(icon, size: 18, color: color),
    );
  }
}

class _ProcessingStatusBadge extends StatelessWidget {
  final String status;

  const _ProcessingStatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Color color;
    IconData icon;

    switch (status.toLowerCase()) {
      case 'processing':
        color = Colors.orange;
        icon = Icons.hourglass_empty;
        break;
      case 'processed':
        color = Colors.green;
        icon = Icons.check_circle;
        break;
      case 'failed':
        color = Colors.red;
        icon = Icons.error;
        break;
      default:
        color = theme.colorScheme.onSurfaceVariant;
        icon = Icons.info;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            status.toUpperCase(),
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
}

class _DecisionButton extends StatelessWidget {
  final Map<String, dynamic> choice;
  final Function(String)? onSelect;

  const _DecisionButton({
    required this.choice,
    this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final choiceId = choice['ChoiceID'] ?? '';
    final text = choice['Text'] ?? 'Choose';
    final description = choice['Description'] ?? '';
    final difficulty = choice['Difficulty'];

    return Card(
      elevation: 2,
      child: InkWell(
        onTap: onSelect != null ? () async {
          final selectedChoice = await DecisionWidget.showDialog(
            context: context,
            choices: {choiceId: choice},
            title: 'Confirm Your Choice',
            showDifficulty: true,
          );
          if (selectedChoice != null) {
            onSelect!(selectedChoice);
          }
        } : null,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      text,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    if (description.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        description,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (difficulty != null) ...[
                const SizedBox(width: 8),
                _DifficultyBadge(difficulty: difficulty),
              ],
              const SizedBox(width: 8),
              Icon(
                Icons.arrow_forward_ios,
                size: 16,
                color: theme.colorScheme.primary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DifficultyBadge extends StatelessWidget {
  final dynamic difficulty;

  const _DifficultyBadge({required this.difficulty});

  @override
  Widget build(BuildContext context) {
    final level = difficulty is int ? difficulty : 0;
    final color = _getDifficultyColor(level);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(
          3,
          (index) => Icon(
            Icons.star,
            size: 12,
            color: index < level ? color : color.withValues(alpha: 0.3),
          ),
        ),
      ),
    );
  }

  Color _getDifficultyColor(int level) {
    switch (level) {
      case 1:
        return Colors.green;
      case 2:
        return Colors.orange;
      case 3:
        return Colors.red;
      default:
        return Colors.grey;
    }
  }
}

class _OutcomeDisplay extends StatelessWidget {
  final Map<String, dynamic> outcome;

  const _OutcomeDisplay({required this.outcome});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final type = outcome['Type'] ?? 'unknown';
    final description = outcome['Description'] ?? '';
    final rewards = outcome['Rewards'] as Map<String, dynamic>?;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _getOutcomeColor(type).withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: _getOutcomeColor(type),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                _getOutcomeIcon(type),
                color: _getOutcomeColor(type),
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                _formatOutcomeType(type),
                style: theme.textTheme.titleSmall?.copyWith(
                  color: _getOutcomeColor(type),
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          if (description.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              description,
              style: theme.textTheme.bodyMedium,
            ),
          ],
          if (rewards != null && rewards.isNotEmpty) ...[
            const SizedBox(height: 8),
            _RewardsDisplay(rewards: rewards),
          ],
        ],
      ),
    );
  }

  Color _getOutcomeColor(String type) {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Colors.green;
      case 'normal':
        return Colors.blue;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      case 'death':
        return Colors.red.shade900;
      default:
        return Colors.grey;
    }
  }

  IconData _getOutcomeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Icons.check_circle;
      case 'normal':
        return Icons.check;
      case 'minimal':
        return Icons.warning;
      case 'failure':
        return Icons.cancel;
      case 'death':
        return Icons.dangerous;
      default:
        return Icons.help_outline;
    }
  }

  String _formatOutcomeType(String type) {
    return type[0].toUpperCase() + type.substring(1);
  }
}

class _RewardsDisplay extends StatelessWidget {
  final Map<String, dynamic> rewards;

  const _RewardsDisplay({required this.rewards});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Wrap(
      spacing: 8,
      runSpacing: 4,
      children: rewards.entries.map((entry) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: theme.colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _getRewardIcon(entry.key),
                size: 14,
                color: theme.colorScheme.onPrimaryContainer,
              ),
              const SizedBox(width: 4),
              Text(
                '+${entry.value} ${_formatRewardName(entry.key)}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onPrimaryContainer,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  IconData _getRewardIcon(String reward) {
    switch (reward.toLowerCase()) {
      case 'xp':
      case 'experience':
        return Icons.trending_up;
      case 'gold':
      case 'coins':
        return Icons.monetization_on;
      case 'item':
      case 'items':
        return Icons.inventory_2;
      default:
        return Icons.card_giftcard;
    }
  }

  String _formatRewardName(String name) {
    return name[0].toUpperCase() + name.substring(1);
  }
}

class _SegmentHistory extends StatelessWidget {
  final List<Map<String, dynamic>> segments;

  const _SegmentHistory({required this.segments});

  @override
  Widget build(BuildContext context) {
    if (segments.isEmpty) {
      return Text(
        'No previous segments',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
          fontStyle: FontStyle.italic,
        ),
      );
    }

    return Column(
      children: segments.asMap().entries.map((entry) {
        final index = entry.key;
        final segment = entry.value;
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: _HistorySegmentCard(
            segment: segment,
            index: segments.length - index,
          ).animate()
            .fadeIn(delay: Duration(milliseconds: 50 * index))
            .slideX(begin: -0.05, end: 0),
        );
      }).toList(),
    );
  }
}

class _HistorySegmentCard extends StatelessWidget {
  final Map<String, dynamic> segment;
  final int index;

  const _HistorySegmentCard({
    required this.segment,
    required this.index,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final type = segment['SegmentType'] ?? 'unknown';
    final status = segment['ShortStatus'] ?? '';
    final outcome = segment['Outcome'] as Map<String, dynamic>?;

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: theme.colorScheme.outline.withValues(alpha: 0.2),
        ),
      ),
      child: ExpansionTile(
        leading: CircleAvatar(
          radius: 16,
          backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.2),
          child: Text(
            '$index',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.primary,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        title: Row(
          children: [
            _SegmentTypeIcon(type: type),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                status,
                style: theme.textTheme.bodyMedium,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        subtitle: outcome != null
            ? Text(
                'Outcome: ${outcome['Type'] ?? 'Unknown'}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: _getOutcomeColor(outcome['Type'] ?? ''),
                ),
              )
            : null,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (segment['LongStatus'] != null) ...[
                  Text(
                    segment['LongStatus'],
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 8),
                ],
                if (outcome != null)
                  _OutcomeDisplay(outcome: outcome),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Color _getOutcomeColor(String type) {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Colors.green;
      case 'normal':
        return Colors.blue;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }
}