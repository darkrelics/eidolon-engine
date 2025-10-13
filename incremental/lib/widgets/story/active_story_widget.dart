import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/providers/timer_provider.dart';
import 'package:eidolon_incremental/utils/combat_narrative.dart';
import 'package:eidolon_incremental/utils/outcome_colors.dart';

/// Widget displaying the active story with segments
class ActiveStoryWidget extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onContinue;
  final VoidCallback? onRefresh;
  final bool isDecisionSubmitting;

  const ActiveStoryWidget({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onContinue,
    this.onRefresh,
    this.isDecisionSubmitting = false,
  });

  @override
  State<ActiveStoryWidget> createState() => _ActiveStoryWidgetState();
}

class _ActiveStoryWidgetState extends State<ActiveStoryWidget> {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final storyData = widget.character.storyState?['Story'] as Map<String, dynamic>?;
    final segmentData = widget.character.storyState?['ActiveSegment'] as Map<String, dynamic>?;

    if (storyData == null && segmentData == null) {
      return Center(
        child: Text('No active story', style: theme.textTheme.titleMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Story Card
          if (storyData != null) ...[_StoryCard(story: storyData), const SizedBox(height: 16)],

          // Action Buttons
          _ActionButtons(onAbandon: widget.onAbandonStory),
          const SizedBox(height: 20),

          // Active Segment
          if (segmentData != null) ...[
            _SimpleSegmentCard(
              key: ValueKey('active_segment_${segmentData['ActiveSegmentID'] ?? segmentData['SegmentID'] ?? segmentData.hashCode}'),
              segment: segmentData,
              isActive: true,
              characterName: widget.character.name,
              onDecisionSelect: widget.onDecisionSelect,
              isDecisionSubmitting: widget.isDecisionSubmitting,
              onTimeout: () {
                if (!mounted) return;
                // Allow UI to refresh timer visuals; network orchestration is handled elsewhere
                setState(() {});
              },
            ),
            const SizedBox(height: 20),
          ],

          // Previous Segments (newest first)
          if (widget.segmentHistory.isNotEmpty) ...[
            Text('Previous Segments', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            // Use ListView.builder for large lists (>20 items) to enable virtualization
            // Use direct mapping for small lists (<= 20 items) for better performance
            if (widget.segmentHistory.length > 20)
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: widget.segmentHistory.length,
                itemBuilder: (context, index) {
                  final segment = widget.segmentHistory[index];
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _SimpleSegmentCard(
                      segment: segment,
                      isActive: false,
                      characterName: widget.character.name,
                      isDecisionSubmitting: false,
                    ),
                  );
                },
              )
            else
              ...widget.segmentHistory.map((segment) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _SimpleSegmentCard(
                  segment: segment,
                  isActive: false,
                  characterName: widget.character.name,
                  isDecisionSubmitting: false,
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

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [theme.colorScheme.primaryContainer, theme.colorScheme.primaryContainer.withValues(alpha: 0.7)],
        ),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [BoxShadow(color: theme.colorScheme.shadow.withValues(alpha: 0.1), blurRadius: 8, offset: const Offset(0, 2))],
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.auto_stories, color: theme.colorScheme.onPrimaryContainer),
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
              Text(description, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onPrimaryContainer)),
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
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color, letterSpacing: 0.5),
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

class _ActionButtons extends StatelessWidget {
  final VoidCallback? onAbandon;

  const _ActionButtons({this.onAbandon});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
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
  final VoidCallback? onTimeout;
  final bool isDecisionSubmitting;
  final String? characterName;

  const _SimpleSegmentCard({
    super.key,
    required this.segment,
    required this.isActive,
    this.onDecisionSelect,
    this.onTimeout,
    this.isDecisionSubmitting = false,
    this.characterName,
  });

  static bool _isProcessingPlaceholder(String? value) {
    if (value == null) return false;
    final normalized = value.trim().toLowerCase();
    if (normalized.isEmpty) return false;
    if (normalized.startsWith('processing')) return true;
    return normalized == '...processing...' || normalized == 'processing your actions...';
  }

  static String _pickSegmentText(List<String?> candidates, {String? exclude, bool allowPlaceholders = false}) {
    final normalizedExclude = exclude?.trim().toLowerCase();
    for (final candidate in candidates) {
      if (candidate == null) continue;
      final trimmed = candidate.trim();
      if (trimmed.isEmpty) continue;
      if (!allowPlaceholders && _isProcessingPlaceholder(trimmed)) {
        continue;
      }
      if (normalizedExclude != null && trimmed.toLowerCase() == normalizedExclude) {
        continue;
      }
      return trimmed;
    }
    return '';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rawSegmentType = segment['SegmentType']?.toString() ?? 'mechanical';
    final segmentType = rawSegmentType.toLowerCase();
    final rawSegmentActivity = segment['SegmentActivity']?.toString();
    final rawSegmentTitle = segment['SegmentTitle']?.toString();
    final prompt = segment['Prompt']?.toString();

    var segmentTitle = _pickSegmentText([rawSegmentTitle, rawSegmentActivity, prompt]);
    if (segmentTitle.isEmpty) {
      segmentTitle = 'Processing...';
    }

    final supplementalStatus = _pickSegmentText([prompt, rawSegmentTitle], exclude: segmentTitle);
    final showSupplementalStatus = supplementalStatus.isNotEmpty;

    final outcome = segment['Outcome'];
    final endTimeStr = segment['EndTime']?.toString();
    final processingStatus = segment['ProcessingStatus']?.toString() ?? 'pending';

    DateTime? endTime;
    if (endTimeStr != null && endTimeStr.isNotEmpty) {
      try {
        endTime = DateTime.parse(endTimeStr).toUtc();
      } catch (_) {
        endTime = null;
      }
    }

    final statusStr = segment['Status']?.toString().toLowerCase();
    final isSegmentComplete = statusStr == 'complete' || statusStr == 'completed';
    final isStoryComplete = segment['StoryComplete'] == true;
    // For active segments, only consider segment completion status, not story completion
    // Story might be complete while the final segment is still running
    final isCompleteFlag = isActive ? isSegmentComplete : (isSegmentComplete || isStoryComplete);

    final dynamic timeRemainingValue = segment['TimeRemaining'];
    int? timeRemaining;
    if (timeRemainingValue is num) {
      timeRemaining = timeRemainingValue.toInt();
    } else if (timeRemainingValue is String) {
      timeRemaining = int.tryParse(timeRemainingValue);
    }

    bool hasTimerExpired = false;
    bool hasTimingInfo = false;

    if (timeRemaining != null) {
      hasTimingInfo = true;
      if (timeRemaining <= 0) {
        hasTimerExpired = true;
      }
    }

    if (endTime != null) {
      hasTimingInfo = true;
      final now = DateTime.now().toUtc();
      if (now.isAfter(endTime)) {
        hasTimerExpired = true;
      }
    }

    // Don't treat as expired just because it's processed - for active segments, wait for the timer
    // Only use this fallback for non-active (historical) segments with no timing info
    if (!isActive && !hasTimingInfo && processingStatus == 'processed') {
      hasTimerExpired = true;
    }

    // Display gating rules:
    // 1. Active segments: Show timer card until timer expires, even if ProcessingStatus="processed"
    // 2. Only reveal results when: segment is processed AND timer has expired
    // 3. Historical segments: Show completed card only if processed and NOT currently active
    final bool shouldRevealResults;
    if (isActive) {
      // Active segment: Only reveal when timer has expired AND segment is processed
      shouldRevealResults = hasTimerExpired && (processingStatus == 'processed' || isCompleteFlag);
      debugPrint('ActiveStoryWidget: Active segment gating - timerExpired=$hasTimerExpired, processed=${processingStatus == 'processed'}, complete=$isCompleteFlag, reveal=$shouldRevealResults');
    } else {
      // Historical segment: Reveal if processed (and it's not the active segment anymore)
      shouldRevealResults = processingStatus == 'processed' || isCompleteFlag;
      debugPrint('ActiveStoryWidget: Historical segment - processed=${processingStatus == 'processed'}, complete=$isCompleteFlag, reveal=$shouldRevealResults');
    }

    final bool waitingOnTimer = isActive && !shouldRevealResults;
    if (waitingOnTimer) {
      debugPrint('ActiveStoryWidget: Waiting on timer - showing processing indicator (timeRemaining=${timeRemaining ?? 'unknown'})');
    }

    var processingIndicatorText = '';
    if (waitingOnTimer) {
      final candidate = _pickSegmentText(
        [rawSegmentActivity, prompt, rawSegmentTitle],
        allowPlaceholders: true,
        exclude: segmentTitle,
      );
      processingIndicatorText = candidate.isEmpty || _isProcessingPlaceholder(candidate) ? 'Processing...' : candidate;
    }

    // Determine card color based on outcome
    Color cardColor;
    IconData icon;
    Color backgroundColor;

    if (shouldRevealResults && outcome != null) {
      cardColor = outcomeAccentColor(theme, outcome);
      backgroundColor = outcomeBackgroundColor(theme, outcome);
      icon = _resolveOutcomeIcon(outcome);
    } else {
      // Segment not processed yet or no outcome - use neutral colors
      cardColor = theme.colorScheme.primary;
      backgroundColor = isActive ? theme.colorScheme.primaryContainer.withValues(alpha: 0.1) : theme.colorScheme.surface;

      if (isActive) {
        icon = waitingOnTimer ? Icons.hourglass_empty : Icons.play_circle_outline;
      } else {
        icon = Icons.check_circle_outline;
      }
    }

    return Card(
      elevation: isActive ? 2 : 0,
      color: backgroundColor,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: isActive ? cardColor.withValues(alpha: 0.3) : Colors.transparent, width: isActive ? 2 : 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header row with SegmentTitle as title
            Row(
              children: [
                Icon(icon, color: isActive ? cardColor : theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    segmentTitle,
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: isActive ? cardColor : null),
                  ),
                ),
              ],
            ),

            // Show processing status for active segments
            if (waitingOnTimer) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: theme.colorScheme.tertiaryContainer.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(theme.colorScheme.tertiary),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      processingIndicatorText,
                      style: TextStyle(color: theme.colorScheme.tertiary, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
            ],

            // Show timer and SegmentActivity for active segments
            if (isActive && endTime != null) ...[
              const SizedBox(height: 12),
              _SegmentTimer(
                endTime: endTime.toIso8601String(),
                startTime: segment['StartTime'],
                duration: segment['SegmentDuration'] ?? segment['Duration'],
                onTimeout: onTimeout,
              ),
              if (showSupplementalStatus) ...[
                const SizedBox(height: 8),
                Text(supplementalStatus, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              ],
            ],

            if (isActive && endTime == null && waitingOnTimer && showSupplementalStatus) ...[
              const SizedBox(height: 12),
              Text(supplementalStatus, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ],

            // Show narrative for processed segments OR initial prompt for unprocessed active segments
            // ClientEvents contain the narrative for processed segments
            if ((shouldRevealResults && (segment['Narrative'] != null || segment['ClientEvents'] != null)) ||
                (waitingOnTimer && segment['Prompt'] != null)) ...[
              const SizedBox(height: 12),
              Builder(
                builder: (context) {
                  final narrative = segment['Narrative']?.toString() ?? '';
                  final promptText = segment['Prompt']?.toString() ?? '';
                  final clientEvents = segment['ClientEvents'] as List<dynamic>?;

                  // For processed segments, show narrative from ClientEvents or Narrative field
                  // For active unprocessed segments, show initial prompt
                  String displayText = '';
                  if (shouldRevealResults) {
                    if (clientEvents != null && clientEvents.isNotEmpty) {
                      // Get opponent name from combat state if available
                      final combatState = segment['CombatState'] as Map<String, dynamic>?;
                      final opponentName = combatState?['OpponentName'] as String?;

                      // Process each event, generating combat narratives where applicable
                      displayText = clientEvents
                          .map((event) {
                            if (event is Map<String, dynamic> && CombatNarrative.isCombatEvent(event)) {
                              return CombatNarrative.generateEventNarrative(
                                event,
                                characterName: characterName ?? 'You',
                                opponentName: opponentName,
                              );
                            }
                            return event['Description']?.toString() ?? '';
                          })
                          .where((desc) => desc.isNotEmpty)
                          .join('\n\n');
                    }
                    if (displayText.isEmpty && narrative.isNotEmpty) {
                      displayText = narrative;
                    }
                  } else {
                    displayText = promptText;
                  }

                  // Only show if we have text to display
                  if (displayText.isEmpty) {
                    if (waitingOnTimer && showSupplementalStatus) {
                      displayText = supplementalStatus;
                    } else {
                      return const SizedBox();
                    }
                  }

                  if (shouldRevealResults) {
                    return Text(displayText, style: theme.textTheme.bodyMedium, textAlign: TextAlign.justify);
                  }

                  return Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: theme.colorScheme.outline.withValues(alpha: 0.2)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (waitingOnTimer && promptText.isNotEmpty)
                          Text(
                            'Current Activity:',
                            style: theme.textTheme.labelMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.primary,
                            ),
                          ),
                        if (waitingOnTimer && promptText.isNotEmpty) const SizedBox(height: 4),
                        Text(displayText, style: theme.textTheme.bodyMedium, textAlign: TextAlign.justify),
                      ],
                    ),
                  );
                },
              ),
            ],

            // Show outcome ONLY for processed segments
            if (shouldRevealResults && outcome != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.workspace_premium, size: 16, color: outcomeAccentColor(theme, outcome)),
                  const SizedBox(width: 4),
                  Text(
                    'Outcome: ${_formatOutcome(outcome)}',
                    style: TextStyle(color: outcomeAccentColor(theme, outcome), fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ],

            // Show chosen decision for completed decision segments
            if (segmentType == 'decision' && !isActive && segment['Decision'] != null && segment['DecisionOptions'] != null) ...[
              const SizedBox(height: 12),
              Builder(
                builder: (context) {
                  final decisionId = segment['Decision'] as String;
                  final decisionOptions = segment['DecisionOptions'] as Map<String, dynamic>;
                  final choiceData = decisionOptions[decisionId];

                  String choiceText;
                  String? description;

                  if (choiceData is Map<String, dynamic>) {
                    choiceText = choiceData['Text'] as String? ?? decisionId;
                    description = choiceData['Description'] as String?;
                  } else {
                    choiceText = decisionId.replaceAll('-', ' ').toUpperCase();
                  }

                  return Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primaryContainer.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.5)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(Icons.check_circle, size: 16, color: theme.colorScheme.primary),
                            const SizedBox(width: 6),
                            Text(
                              'Decision Made:',
                              style: theme.textTheme.labelMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: theme.colorScheme.primary,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (description != null) ...[
                          Text(
                            description,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 4),
                        ],
                        Text(
                          choiceText,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ],

            // Decision options for decision segments
            if (segmentType == 'decision' && isActive && segment['DecisionOptions'] != null) ...[
              const SizedBox(height: 12),
              if (segment['DecisionText'] != null) ...[
                Text(
                  segment['DecisionText'] as String,
                  style: const TextStyle(fontStyle: FontStyle.italic),
                ),
                const SizedBox(height: 12),
              ],
              ...((segment['DecisionOptions'] as Map<String, dynamic>).entries.map(
                (entry) {
                  final choiceData = entry.value;
                  String choiceText;
                  String? description;

                  // Support both legacy (string) and rich (object) formats
                  if (choiceData is Map<String, dynamic>) {
                    choiceText = choiceData['Text'] as String? ?? entry.key;
                    description = choiceData['Description'] as String?;
                  } else {
                    // Legacy format: display choice ID
                    choiceText = entry.key.replaceAll('-', ' ').toUpperCase();
                  }

                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (description != null) ...[
                          Text(
                            description,
                            style: theme.textTheme.bodyMedium,
                          ),
                          const SizedBox(height: 8),
                        ],
                        FilledButton(
                          onPressed: isDecisionSubmitting ? null : () => onDecisionSelect?.call(entry.key),
                          child: Text(choiceText),
                        ),
                      ],
                    ),
                  );
                },
              )),
            ],
          ],
        ),
      ),
    );
  }

  String _formatOutcome(dynamic outcome) {
    final outcomeStr = outcome is String ? outcome : outcome['Type'] ?? 'normal';
    return outcomeStr[0].toUpperCase() + outcomeStr.substring(1);
  }

  IconData _resolveOutcomeIcon(dynamic outcome) {
    switch (normalizedOutcomeType(outcome)) {
      case 'death':
        return Icons.dangerous;
      case 'failure':
      case 'failed':
        return Icons.cancel;
      default:
        return Icons.check_circle;
    }
  }
}

// Timer widget for active segments
class _SegmentTimer extends StatefulWidget {
  final String endTime;
  final String? startTime;
  final dynamic duration;
  final VoidCallback? onTimeout;

  const _SegmentTimer({required this.endTime, this.startTime, this.duration, this.onTimeout});

  @override
  State<_SegmentTimer> createState() => _SegmentTimerState();
}

class _SegmentTimerState extends State<_SegmentTimer> {
  int _remainingSeconds = 0;
  int _totalDuration = 60;
  DateTime? _endDateTime;
  DateTime? _startDateTime;
  bool _hasTimedOut = false;
  TimerProvider? _timerProvider;

  @override
  void initState() {
    super.initState();

    // Parse the end time
    _endDateTime = DateTime.parse(widget.endTime);

    // Parse start time if provided, otherwise calculate it
    if (widget.startTime != null) {
      try {
        _startDateTime = DateTime.parse(widget.startTime!);
        // Calculate total duration from actual start and end times
        _totalDuration = _endDateTime!.difference(_startDateTime!).inSeconds;
      } catch (e) {
        // If parsing fails, fall back to calculation method
        if (widget.duration != null) {
          _totalDuration = widget.duration is int ? widget.duration : int.tryParse(widget.duration.toString()) ?? 60;
        }
        _startDateTime = _endDateTime!.subtract(Duration(seconds: _totalDuration));
      }
    } else {
      // No start time provided, calculate based on duration
      if (widget.duration != null) {
        _totalDuration = widget.duration is int ? widget.duration : int.tryParse(widget.duration.toString()) ?? 60;
      }
      _startDateTime = _endDateTime!.subtract(Duration(seconds: _totalDuration));
    }

    _updateRemainingTime();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    // Get the TimerProvider and start listening to it
    final timerProvider = Provider.of<TimerProvider>(context, listen: false);
    if (_timerProvider != timerProvider) {
      _timerProvider?.removeListener(_onTimerUpdate);
      _timerProvider = timerProvider;
      _timerProvider?.addListener(_onTimerUpdate);
      _timerProvider?.startTimer();
    }
  }

  @override
  void dispose() {
    _timerProvider?.removeListener(_onTimerUpdate);
    super.dispose();
  }

  void _onTimerUpdate() {
    if (!mounted || _endDateTime == null) return;

    final previousRemaining = _remainingSeconds;
    _updateRemainingTime();

    // Only trigger rebuild if the remaining time actually changed (seconds boundary)
    if (_remainingSeconds != previousRemaining) {
      setState(() {});
    }
  }

  void _updateRemainingTime() {
    if (_endDateTime == null) return;

    final now = _timerProvider?.currentTime ?? DateTime.now();
    final difference = _endDateTime!.difference(now);

    _remainingSeconds = difference.inSeconds > 0 ? difference.inSeconds : 0;

    // Trigger timeout callback when timer reaches zero
    if (_remainingSeconds == 0 && !_hasTimedOut) {
      _hasTimedOut = true;
      if (widget.onTimeout != null) {
        // Schedule callback after build completes
        WidgetsBinding.instance.addPostFrameCallback((_) {
          widget.onTimeout!();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // Calculate hours, minutes, and seconds
    final hours = _remainingSeconds ~/ 3600;
    final minutes = (_remainingSeconds % 3600) ~/ 60;
    final seconds = _remainingSeconds % 60;

    // Format time display based on whether we have hours
    String timeDisplay;
    if (hours > 0) {
      // Display hours:minutes:seconds when more than an hour
      timeDisplay =
          '${hours.toString().padLeft(2, '0')}:'
          '${minutes.toString().padLeft(2, '0')}:'
          '${seconds.toString().padLeft(2, '0')}';
    } else {
      // Display minutes:seconds when less than an hour
      timeDisplay =
          '${minutes.toString().padLeft(2, '0')}:'
          '${seconds.toString().padLeft(2, '0')}';
    }

    // Calculate progress based on elapsed time from start
    // Progress starts at 0 when segment begins and reaches 1.0 when it ends
    double progress = 0.0;
    if (_startDateTime != null && _endDateTime != null && _timerProvider != null) {
      progress = _timerProvider!.getProgress(_startDateTime!, _endDateTime!);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Progress bar
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: progress.clamp(0.0, 1.0),
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
            valueColor: AlwaysStoppedAnimation<Color>(theme.colorScheme.primary),
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
              timeDisplay,
              style: TextStyle(fontFamily: 'monospace', color: theme.colorScheme.onSurfaceVariant, fontSize: 14),
            ),
          ],
        ),
      ],
    );
  }
}
