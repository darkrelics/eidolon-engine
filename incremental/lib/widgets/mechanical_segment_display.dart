import 'dart:async';
import 'package:flutter/material.dart';
import '../models/active_segment.dart';
import '../utils/time_utils.dart';

/// Widget to display mechanical segment events progressively
class MechanicalSegmentDisplay extends StatefulWidget {
  final ActiveSegment segment;
  final VoidCallback? onComplete;

  const MechanicalSegmentDisplay({
    super.key,
    required this.segment,
    this.onComplete,
  });

  @override
  State<MechanicalSegmentDisplay> createState() =>
      _MechanicalSegmentDisplayState();
}

class _MechanicalSegmentDisplayState extends State<MechanicalSegmentDisplay> {
  int _currentEventIndex = -1;
  Timer? _eventTimer;
  Timer? _countdownTimer;
  Duration _timeRemaining = Duration.zero;
  bool _allEventsShown = false;
  String _currentNarrative = '';
  bool _showingDefaultNarrative = true;

  @override
  void initState() {
    super.initState();
    _calculateTimeRemaining();
    _startCountdown();

    // Set initial narrative
    _currentNarrative = widget.segment.segmentTitle ?? widget.segment.status;

    // If segment is already processed, show all events immediately
    if (widget.segment.processingStatus == 'processed' &&
        widget.segment.clientEvents != null) {
      setState(() {
        _currentEventIndex = widget.segment.clientEvents!.length - 1;
        _allEventsShown = true;
        _showingDefaultNarrative = false;
      });
    } else {
      // Otherwise, schedule progressive display
      _scheduleNarrativeProgression();
    }
  }

  @override
  void dispose() {
    _eventTimer?.cancel();
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _calculateTimeRemaining() {
    final remainingSeconds = TimeUtils.secondsUntil(widget.segment.endTime);

    if (remainingSeconds <= 0) {
      _timeRemaining = Duration.zero;
    } else {
      _timeRemaining = Duration(seconds: remainingSeconds);
    }
  }

  void _startCountdown() {
    _countdownTimer?.cancel();

    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _calculateTimeRemaining();

        if (_timeRemaining.inSeconds <= 0) {
          timer.cancel();
          if (_allEventsShown && widget.onComplete != null) {
            widget.onComplete!();
          }
        }
      });
    });
  }

  void _scheduleNarrativeProgression() {
    final events = widget.segment.clientEvents;
    if (events == null || events.isEmpty) {
      // No events, just show default narrative
      return;
    }

    final totalDuration = Duration(
      seconds: TimeUtils.durationBetween(
        widget.segment.startTime,
        widget.segment.endTime,
      ),
    );

    // Create a timeline of narrative changes
    final narrativeTimeline = _buildNarrativeTimeline(events, totalDuration);

    // Schedule narrative changes using precise timers instead of polling
    // This reduces CPU usage from 600 checks/minute to actual event count
    for (int i = 0; i < narrativeTimeline.length; i++) {
      final point = narrativeTimeline[i];
      final delay = point['time'] as Duration;

      // Schedule a timer for each narrative change
      Timer(delay, () {
        if (!mounted) return;

        setState(() {
          _currentNarrative = point['narrative'] as String;
          _showingDefaultNarrative = point['isDefault'] as bool;

          // If this point has an event to show, update the index
          if (point['eventIndex'] != null) {
            _currentEventIndex = point['eventIndex'] as int;
          }
        });

        // Check if this was the last event
        if (i == narrativeTimeline.length - 1) {
          _allEventsShown = true;
        }
      });
    }
  }

  List<Map<String, dynamic>> _buildNarrativeTimeline(
    List<dynamic> events,
    Duration totalDuration,
  ) {
    final timeline = <Map<String, dynamic>>[];

    // If we have events, space them throughout the duration
    if (events.isNotEmpty) {
      // Reserve time for final outcome (last 20% of duration)
      final activeTime = totalDuration.inMilliseconds * 0.8;
      final segmentDuration = activeTime / events.length;

      for (int i = 0; i < events.length; i++) {
        final event = events[i] as Map<String, dynamic>;
        final eventTime = Duration(milliseconds: (segmentDuration * i).round());

        // Add task start narrative
        if (event['description'] != null) {
          timeline.add({
            'time': eventTime,
            'narrative': event['description'] as String,
            'isDefault': false,
            'eventIndex': null,
          });
        }

        // Add event display slightly after narrative
        timeline.add({
          'time': eventTime + const Duration(seconds: 1),
          'narrative': event['description'] as String? ?? _currentNarrative,
          'isDefault': false,
          'eventIndex': i,
        });

        // Add idle period between events (if not the last event)
        if (i < events.length - 1) {
          final idleTime =
              eventTime +
              Duration(milliseconds: (segmentDuration * 0.7).round());
          timeline.add({
            'time': idleTime,
            'narrative': widget.segment.segmentTitle ?? widget.segment.status,
            'isDefault': true,
            'eventIndex': null,
          });
        }
      }

      // Add final outcome narrative
      final finalTime = Duration(
        milliseconds: (totalDuration.inMilliseconds * 0.9).round(),
      );
      timeline.add({
        'time': finalTime,
        'narrative': _getFinalNarrative(events),
        'isDefault': false,
        'eventIndex': null,
      });
    }

    return timeline;
  }

  String _getFinalNarrative(List<dynamic> events) {
    // Look for combat victory/defeat or other completion events
    for (final event in events.reversed) {
      final eventMap = event as Map<String, dynamic>;
      final eventType = eventMap['eventType'] as String?;

      if (eventType == 'combatVictory') {
        return 'You have emerged victorious!';
      } else if (eventType == 'combatDefeat') {
        return 'You have been defeated...';
      }
    }

    // Default completion message
    return 'You have completed this segment of your journey.';
  }

  Map<String, dynamic> _extractEventData(dynamic eventData) {
    if (eventData == null) {
      return {};
    }

    try {
      return eventData as Map<String, dynamic>;
    } catch (e) {
      debugPrint(
        'MechanicalSegmentDisplay: Error casting event data to Map: $e',
      );
      debugPrint(
        'MechanicalSegmentDisplay: Event data type: ${eventData.runtimeType}',
      );
      debugPrint('MechanicalSegmentDisplay: Event data value: $eventData');
      return {};
    }
  }

  Widget _buildEventCard(Map<String, dynamic> event) {
    try {
      final eventType = event['eventType'] as String?;
      final title = event['title'] as String? ?? 'Event';
      final description = event['description'] as String? ?? '';

      // Extract data using separate method
      final data = _extractEventData(event['data']);

      IconData icon;
      Color iconColor;

      switch (eventType) {
        case 'skillCheck':
          icon = Icons.psychology;
          iconColor = data['success'] == true ? Colors.green : Colors.orange;
          break;
        case 'combat':
          icon = Icons.shield;
          iconColor = Colors.red;
          break;
        case 'combatAttack':
          icon = Icons.sports_martial_arts;
          iconColor = Colors.deepOrange;
          break;
        case 'combatDefense':
          icon = Icons.shield_outlined;
          iconColor = Colors.blue;
          break;
        case 'combatDamage':
          icon = Icons.favorite;
          iconColor = Colors.red;
          break;
        case 'combatVictory':
          icon = Icons.workspace_premium;
          iconColor = Colors.amber;
          break;
        case 'combatDefeat':
          icon = Icons.heart_broken;
          iconColor = Colors.grey;
          break;
        default:
          icon = Icons.info;
          iconColor = Colors.grey;
      }

      return Card(
        margin: const EdgeInsets.symmetric(vertical: 8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: iconColor, size: 24),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              if (description.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  description,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
              if (eventType == 'skillCheck' && data.isNotEmpty) ...[
                const SizedBox(height: 12),
                _buildSkillCheckDetails(data),
              ],
              if (eventType != null &&
                  eventType.startsWith('combat') &&
                  data.isNotEmpty) ...[
                const SizedBox(height: 12),
                _buildCombatDetails(eventType, data),
              ],
            ],
          ),
        ),
      );
    } catch (e) {
      debugPrint('MechanicalSegmentDisplay: Error building event card: $e');
      debugPrint('MechanicalSegmentDisplay: Event: $event');
      // Return a simple error card
      return Card(
        margin: const EdgeInsets.symmetric(vertical: 8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(Icons.error_outline, color: Colors.red),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Error displaying event',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
      );
    }
  }

  Widget _buildSkillCheckDetails(Map<String, dynamic> data) {
    final skill = data['skill'] as String? ?? 'Unknown';
    final success = data['success'] as bool? ?? false;
    final effectiveScore = data['effectiveScore']?.toString() ?? '?';
    final difficulty = data['difficulty']?.toString() ?? '?';
    final sigma = data['sigma']?.toString() ?? '?';

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: success
            ? Colors.green.withValues(alpha: 0.1)
            : Colors.orange.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '${skill.toUpperCase()} CHECK: ',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              Text(
                success ? 'SUCCESS' : 'FAILURE',
                style: TextStyle(
                  color: success ? Colors.green : Colors.orange,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text('Score: $effectiveScore vs Difficulty: $difficulty'),
          Text('Result: $sigma sigma'),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final events = widget.segment.clientEvents ?? [];

    return Column(
      children: [
        // Timer display
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).primaryColor.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.timer, color: Theme.of(context).primaryColor),
              const SizedBox(width: 8),
              Text(
                _formatDuration(_timeRemaining),
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Narrative text
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: _showingDefaultNarrative
                ? Theme.of(context).colorScheme.surface
                : Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: _showingDefaultNarrative
                  ? Theme.of(context).dividerColor
                  : Theme.of(context).colorScheme.primary,
              width: 1,
            ),
          ),
          child: Text(
            _currentNarrative,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
              fontStyle: _showingDefaultNarrative
                  ? FontStyle.italic
                  : FontStyle.normal,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        const SizedBox(height: 16),

        // Events list
        if (_currentEventIndex >= 0) ...[
          Expanded(
            child: ListView.builder(
              itemCount: _currentEventIndex + 1,
              itemBuilder: (context, index) {
                try {
                  final eventData = events[index];
                  if (eventData is! Map<String, dynamic>) {
                    debugPrint(
                      'MechanicalSegmentDisplay: Event at index $index is not a Map',
                    );
                    debugPrint(
                      'MechanicalSegmentDisplay: Event type: ${eventData.runtimeType}',
                    );
                    return const SizedBox.shrink();
                  }

                  return AnimatedOpacity(
                    opacity: index <= _currentEventIndex ? 1.0 : 0.0,
                    duration: const Duration(milliseconds: 500),
                    child: AnimatedSlide(
                      offset: index == _currentEventIndex
                          ? Offset.zero
                          : const Offset(0, 0.1),
                      duration: const Duration(milliseconds: 300),
                      child: _buildEventCard(eventData),
                    ),
                  );
                } catch (e) {
                  debugPrint(
                    'MechanicalSegmentDisplay: Error displaying event at index $index: $e',
                  );
                  return const SizedBox.shrink();
                }
              },
            ),
          ),
        ] else if (widget.segment.processingStatus != 'processed') ...[
          const Expanded(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Processing your actions...'),
                ],
              ),
            ),
          ),
        ] else ...[
          const Expanded(child: SizedBox()),
        ],

        // Completion indicator
        if (_allEventsShown && _timeRemaining.inSeconds <= 0) ...[
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: widget.onComplete,
            icon: const Icon(Icons.chevron_right),
            label: const Text('Continue'),
          ),
        ],
      ],
    );
  }

  Widget _buildCombatDetails(String eventType, Map<String, dynamic> data) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: theme.colorScheme.error.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (eventType == 'combatAttack') ...[
            _buildCombatStat('Target', data['target'] as String? ?? 'Unknown'),
            _buildCombatStat('Attack', data['attack'] as String? ?? 'Unknown'),
            _buildCombatStat('Result', data['result'] as String? ?? 'Unknown'),
            if (data['damage'] != null)
              _buildCombatStat('Damage', '${data['damage']}'),
          ] else if (eventType == 'combatDefense') ...[
            _buildCombatStat(
              'Attacker',
              data['attacker'] as String? ?? 'Unknown',
            ),
            _buildCombatStat(
              'Defense',
              data['defense'] as String? ?? 'Unknown',
            ),
            _buildCombatStat('Result', data['result'] as String? ?? 'Unknown'),
          ] else if (eventType == 'combatDamage') ...[
            if (data['source'] != null)
              _buildCombatStat('Source', data['source'] as String),
            _buildCombatStat('Damage', '${data['amount'] ?? 0}'),
            _buildCombatStat(
              'Type',
              data['damageType'] as String? ?? 'Unknown',
            ),
            if (data['wounds'] != null && (data['wounds'] as List).isNotEmpty)
              _buildWoundsList(data['wounds'] as List),
          ] else if (eventType == 'combatVictory') ...[
            if (data['opponent'] != null)
              _buildCombatStat('Defeated', data['opponent'] as String),
            if (data['experience'] != null)
              _buildCombatStat('Experience', '+${data['experience']} XP'),
            if (data['loot'] != null && (data['loot'] as List).isNotEmpty)
              _buildLootList(data['loot'] as List),
          ] else if (eventType == 'combatDefeat') ...[
            if (data['opponent'] != null)
              _buildCombatStat('Defeated by', data['opponent'] as String),
            if (data['finalBlow'] != null)
              _buildCombatStat('Final blow', data['finalBlow'] as String),
          ] else ...[
            // Generic combat event
            ...data.entries.map(
              (entry) => _buildCombatStat(
                entry.key
                    .replaceAll('_', ' ')
                    .split(' ')
                    .map(
                      (word) => word.isNotEmpty
                          ? word[0].toUpperCase() + word.substring(1)
                          : '',
                    )
                    .join(' '),
                entry.value.toString(),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCombatStat(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text(
            '$label: ',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
          ),
          Text(value, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }

  Widget _buildWoundsList(List wounds) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 4),
        const Text(
          'Wounds received:',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
        ),
        ...wounds.map(
          (wound) => Padding(
            padding: const EdgeInsets.only(left: 12, top: 2),
            child: Text(
              '• ${wound['location'] ?? 'Unknown'} (${wound['damageType'] ?? 'Unknown'})',
              style: const TextStyle(fontSize: 11),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLootList(List loot) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 4),
        const Text(
          'Loot gained:',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
        ),
        ...loot.map(
          (item) => Padding(
            padding: const EdgeInsets.only(left: 12, top: 2),
            child: Text(
              '• ${item['name'] ?? item.toString()}',
              style: const TextStyle(fontSize: 11),
            ),
          ),
        ),
      ],
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes;
    final seconds = duration.inSeconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}
