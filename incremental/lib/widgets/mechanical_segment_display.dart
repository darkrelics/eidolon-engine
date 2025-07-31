import 'dart:async';
import 'package:flutter/material.dart';
import '../models/active_segment.dart';

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
  State<MechanicalSegmentDisplay> createState() => _MechanicalSegmentDisplayState();
}

class _MechanicalSegmentDisplayState extends State<MechanicalSegmentDisplay> {
  int _currentEventIndex = -1;
  Timer? _eventTimer;
  Timer? _countdownTimer;
  Duration _timeRemaining = Duration.zero;
  bool _allEventsShown = false;

  @override
  void initState() {
    super.initState();
    _calculateTimeRemaining();
    _startCountdown();
    
    // If segment is already processed, show all events immediately
    if (widget.segment.processingStatus == 'processed' && 
        widget.segment.clientEvents != null) {
      setState(() {
        _currentEventIndex = widget.segment.clientEvents!.length - 1;
        _allEventsShown = true;
      });
    } else {
      // Otherwise, schedule progressive display
      _scheduleEventDisplay();
    }
  }

  @override
  void dispose() {
    _eventTimer?.cancel();
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _calculateTimeRemaining() {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final endTime = widget.segment.endTime;
    
    if (now >= endTime) {
      _timeRemaining = Duration.zero;
    } else {
      _timeRemaining = Duration(seconds: endTime - now);
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

  void _scheduleEventDisplay() {
    final events = widget.segment.clientEvents;
    if (events == null || events.isEmpty) return;
    
    // Calculate time between events
    final totalDuration = Duration(
      seconds: widget.segment.endTime - widget.segment.startTime,
    );
    final msPerEvent = totalDuration.inMilliseconds ~/ events.length;
    
    // Show first event immediately
    setState(() {
      _currentEventIndex = 0;
    });
    
    // Schedule remaining events
    if (events.length > 1) {
      _eventTimer = Timer.periodic(
        Duration(milliseconds: msPerEvent),
        (timer) {
          setState(() {
            _currentEventIndex++;
            
            if (_currentEventIndex >= events.length - 1) {
              _currentEventIndex = events.length - 1;
              _allEventsShown = true;
              timer.cancel();
            }
          });
        },
      );
    } else {
      _allEventsShown = true;
    }
  }

  Widget _buildEventCard(Map<String, dynamic> event) {
    final eventType = event['eventType'] as String?;
    final title = event['title'] as String? ?? 'Event';
    final description = event['description'] as String? ?? '';
    final data = event['data'] as Map<String, dynamic>? ?? {};
    
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
        icon = Icons.emoji_events;
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
            if (eventType != null && eventType.startsWith('combat') && data.isNotEmpty) ...[
              const SizedBox(height: 12),
              _buildCombatDetails(eventType, data),
            ],
          ],
        ),
      ),
    );
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
              Icon(
                Icons.timer,
                color: Theme.of(context).primaryColor,
              ),
              const SizedBox(width: 8),
              Text(
                _formatDuration(_timeRemaining),
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        
        // Status text
        Text(
          widget.segment.status,
          style: Theme.of(context).textTheme.bodyLarge,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        
        // Events list
        if (_currentEventIndex >= 0) ...[
          Expanded(
            child: ListView.builder(
              itemCount: _currentEventIndex + 1,
              itemBuilder: (context, index) {
                return AnimatedOpacity(
                  opacity: index <= _currentEventIndex ? 1.0 : 0.0,
                  duration: const Duration(milliseconds: 500),
                  child: _buildEventCard(events[index] as Map<String, dynamic>),
                );
              },
            ),
          ),
        ] else ...[
          const Expanded(
            child: Center(
              child: CircularProgressIndicator(),
            ),
          ),
        ],
        
        // Completion indicator
        if (_allEventsShown && _timeRemaining.inSeconds <= 0) ...[
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: widget.onComplete,
            icon: const Icon(Icons.arrow_forward),
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
            _buildCombatStat('Attacker', data['attacker'] as String? ?? 'Unknown'),
            _buildCombatStat('Defense', data['defense'] as String? ?? 'Unknown'),
            _buildCombatStat('Result', data['result'] as String? ?? 'Unknown'),
          ] else if (eventType == 'combatDamage') ...[
            if (data['source'] != null)
              _buildCombatStat('Source', data['source'] as String),
            _buildCombatStat('Damage', '${data['amount'] ?? 0}'),
            _buildCombatStat('Type', data['damageType'] as String? ?? 'Unknown'),
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
            ...data.entries.map((entry) => 
              _buildCombatStat(
                entry.key.replaceAll('_', ' ').split(' ')
                  .map((word) => word.isNotEmpty ? word[0].toUpperCase() + word.substring(1) : '')
                  .join(' '),
                entry.value.toString(),
              )
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
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 12,
            ),
          ),
          Text(
            value,
            style: const TextStyle(fontSize: 12),
          ),
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
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
        ...wounds.map((wound) => Padding(
          padding: const EdgeInsets.only(left: 12, top: 2),
          child: Text(
            '• ${wound['location'] ?? 'Unknown'} (${wound['damageType'] ?? 'Unknown'})',
            style: const TextStyle(fontSize: 11),
          ),
        )),
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
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
        ...loot.map((item) => Padding(
          padding: const EdgeInsets.only(left: 12, top: 2),
          child: Text(
            '• ${item['name'] ?? item.toString()}',
            style: const TextStyle(fontSize: 11),
          ),
        )),
      ],
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes;
    final seconds = duration.inSeconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}