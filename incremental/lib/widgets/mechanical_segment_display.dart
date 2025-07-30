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
      case 'narrative':
        icon = Icons.book;
        iconColor = Colors.blue;
        break;
      case 'skillCheck':
        icon = Icons.psychology;
        iconColor = data['success'] == true ? Colors.green : Colors.orange;
        break;
      case 'combat':
        icon = Icons.sports_kabaddi;
        iconColor = Colors.red;
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

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes;
    final seconds = duration.inSeconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}