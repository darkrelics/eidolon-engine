import 'package:flutter/material.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/utils/combat_narrative.dart';
import 'package:eidolon_incremental/utils/outcome_colors.dart';
import 'package:eidolon_incremental/widgets/story/active_story_widget.dart';
import 'package:eidolon_incremental/widgets/story/available_stories_widget.dart';
import 'package:eidolon_incremental/widgets/story/story_history_widget.dart';
import 'package:fluttericon/rpg_awesome_icons.dart';

/// Center panel that displays story content dynamically
class StoryPanel extends StatefulWidget {
  final Character character;
  final List<Map<String, dynamic>> segmentHistory;
  final List<Map<String, dynamic>> storyHistoryArchive;
  final bool isLoading;
  final String? error;
  final VoidCallback? onRefresh;
  final Function(StoryMetadata)? onStorySelect;
  final Function(String)? onDecisionSelect;
  final VoidCallback? onAbandonStory;
  final VoidCallback? onReturnToStories;
  final bool isDecisionSubmitting;

  const StoryPanel({
    super.key,
    required this.character,
    this.segmentHistory = const [],
    this.storyHistoryArchive = const [],
    this.isLoading = false,
    this.error,
    this.onRefresh,
    this.onStorySelect,
    this.onDecisionSelect,
    this.onAbandonStory,
    this.onReturnToStories,
    this.isDecisionSubmitting = false,
  });

  @override
  State<StoryPanel> createState() => _StoryPanelState();
}

class _StoryPanelState extends State<StoryPanel> {
  bool _showHistory = false;

  bool _hasActiveStory([Character? character]) {
    final char = character ?? widget.character;
    if (char.activeStoryID != null) return true;
    final active = char.storyState != null ? char.storyState!['ActiveSegment'] : null;
    return active != null;
  }

  bool _isStoryComplete() {
    final char = widget.character;

    // If character has an active story, it's not complete
    if (char.activeStoryID != null) {
      return false;
    }

    // Story is complete if:
    // 1. No active story ID (cleared by server on completion)
    // 2. AND we have either segment history or completed segments in story state
    final hasSegmentHistory = widget.segmentHistory.isNotEmpty;
    final stateSegments = char.storyState?['CompletedSegments'] as List<dynamic>?;
    final hasCompletedSegments = stateSegments != null && stateSegments.isNotEmpty;

    return hasSegmentHistory || hasCompletedSegments;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      margin: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: colorScheme.primaryContainer,
              borderRadius: const BorderRadius.only(topLeft: Radius.circular(12), topRight: Radius.circular(12)),
            ),
            child: Row(
              children: [
                Icon(Icons.auto_stories_outlined, color: colorScheme.onPrimaryContainer),
                const SizedBox(width: 8),
                Text(
                  _getHeaderTitle(),
                  style: theme.textTheme.titleLarge?.copyWith(color: colorScheme.onPrimaryContainer, fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                // History toggle button
                if (!_hasActiveStory() && (widget.character.completedStories.isNotEmpty || widget.storyHistoryArchive.isNotEmpty))
                  IconButton(
                    icon: Icon(_showHistory ? Icons.auto_stories_outlined : Icons.receipt_outlined, color: colorScheme.onPrimaryContainer),
                    onPressed: () {
                      setState(() {
                        _showHistory = !_showHistory;
                      });
                    },
                    tooltip: _showHistory ? 'Show Available Stories' : 'Show History',
                  ),
                if (widget.onRefresh != null)
                  IconButton(
                    icon: Icon(Icons.refresh, color: colorScheme.onPrimaryContainer),
                    onPressed: widget.onRefresh,
                    tooltip: 'Refresh',
                  ),
              ],
            ),
          ),

          // Content
          Expanded(child: _buildContent()),
        ],
      ),
    );
  }

  String _getHeaderTitle() {
    if (_isStoryComplete()) {
      return 'Story Complete';
    } else if (_hasActiveStory()) {
      return 'Story';
    } else if (_showHistory) {
      return 'Story History';
    } else {
      return 'Available Stories';
    }
  }

  Widget _buildContent() {
    // Don't show loading if we already have content
    if (widget.isLoading && !_hasActiveStory() && widget.character.availableStoriesDetails == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(
              'Loading stories...',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      );
    }

    if (widget.error != null) {
      return _buildErrorWidget();
    }

    if (_isStoryComplete()) {
      return _buildStoryCompleteWidget();
    }

    if (_hasActiveStory()) {
      return _buildActiveStoryWidget();
    }

    if (_showHistory) {
      return _buildHistoryWidget();
    }

    return _buildAvailableStoriesWidget();
  }

  Widget _buildErrorWidget() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 64, color: colorScheme.error),
            const SizedBox(height: 16),
            Text('Error Loading Stories', style: theme.textTheme.titleMedium?.copyWith(color: colorScheme.error)),
            const SizedBox(height: 8),
            Text(
              widget.error!,
              style: theme.textTheme.bodyMedium?.copyWith(color: colorScheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
            if (widget.onRefresh != null) ...[
              const SizedBox(height: 24),
              FilledButton.icon(onPressed: widget.onRefresh, icon: const Icon(Icons.refresh), label: const Text('Retry')),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildActiveStoryWidget() {
    return ActiveStoryWidget(
      key: ValueKey('active_story_${widget.character.storyState?.hashCode}'),
      character: widget.character,
      segmentHistory: widget.segmentHistory,
      onDecisionSelect: widget.onDecisionSelect,
      onAbandonStory: widget.onAbandonStory,
      onRefresh: widget.onRefresh,
      isDecisionSubmitting: widget.isDecisionSubmitting,
    );
  }

  Widget _buildAvailableStoriesWidget() {
    return AvailableStoriesWidget(
      key: const ValueKey('available_stories'),
      character: widget.character,
      onStorySelect: widget.onStorySelect,
      isLoading: widget.isLoading,
    );
  }

  Widget _buildHistoryWidget() {
    return StoryHistoryWidget(
      key: const ValueKey('story_history'),
      character: widget.character,
      segmentHistory: widget.storyHistoryArchive,
    );
  }

  Widget _buildStoryCompleteWidget() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    // Get story data and completed segments (prefer provided history from parent)
    final storyData = widget.character.storyState?['Story'] as Map<String, dynamic>?;
    final completedSegmentsDynamic = widget.segmentHistory.isNotEmpty
        ? widget.segmentHistory
        : (widget.character.storyState?['CompletedSegments'] as List<dynamic>? ?? const []);

    final completedSegments = completedSegmentsDynamic.map((segment) => segment as Map<String, dynamic>).toList();

    if (completedSegments.isEmpty) {
      // Attempt to infer story information from history if available
      final storyTitle = widget.segmentHistory.isNotEmpty ? widget.segmentHistory.last['StoryTitle'] as String? : null;
      // Fallback to simple completion screen
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(RpgAwesome.trophy, size: 80, color: colorScheme.primary),
            const SizedBox(height: 16),
            Text('Story Complete', style: theme.textTheme.headlineMedium),
            if (storyTitle != null) ...[
              const SizedBox(height: 8),
              Text(storyTitle, style: theme.textTheme.titleMedium, textAlign: TextAlign.center),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: widget.onReturnToStories,
              icon: const Icon(Icons.chevron_left),
              label: const Text('Return to Stories'),
            ),
          ],
        ),
      );
    }

    // Get the last segment to determine overall outcome
    final lastSegment = completedSegments.last;
    final lastOutcome = lastSegment['Outcome'] ?? 'normal';

    // Check if story ended in death or complete failure
    final storyFailed = lastOutcome == 'death' || lastOutcome == 'failure';

    // If the API no longer supplies story metadata, fall back to the last segment title
    Map<String, dynamic>? effectiveStoryData = storyData;
    if (effectiveStoryData == null) {
      final inferredTitle = lastSegment['StoryTitle'];
      if (inferredTitle is String && inferredTitle.isNotEmpty) {
        effectiveStoryData = {'Title': inferredTitle};
      }
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Story Card at the top
          if (effectiveStoryData != null) ...[
            Card(
              elevation: 2,
              color: storyFailed ? Colors.red.withValues(alpha: 0.1) : Colors.green.withValues(alpha: 0.1),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Icon(
                      storyFailed ? RpgAwesome.skull : RpgAwesome.trophy,
                      size: 64,
                      color: storyFailed ? Colors.red : Colors.green,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      effectiveStoryData['Title'] ?? 'Story',
                      style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      storyFailed ? 'FAILED' : 'COMPLETED',
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: storyFailed ? Colors.red : Colors.green,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Segment History - Reverse order (newest first)
          Text('Story Segments', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),

          // Display segments in reverse order with full details
          ...completedSegments.reversed.map((segmentMap) => _buildCompletedSegmentCard(segmentMap, theme)),

          const SizedBox(height: 24),

          // Return button
          Center(
            child: FilledButton.icon(
              onPressed: widget.onReturnToStories,
              icon: const Icon(Icons.chevron_left),
              label: const Text('Return to Stories'),
              style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCompletedSegmentCard(Map<String, dynamic> segment, ThemeData theme) {
    final rawSegmentActivity = segment['SegmentActivity']?.toString().trim();
    final rawSegmentTitle = segment['SegmentTitle']?.toString().trim();
    final rawProcessingStatus = segment['ProcessingStatus']?.toString().toLowerCase();
    final isProcessed = rawProcessingStatus == 'processed';
    final narrative = _extractSegmentNarrative(segment);

    final prompt = segment['Prompt']?.toString();

    final title = _resolveCompletedSegmentTitle(rawSegmentTitle, narrative, rawSegmentActivity, prompt);

    final subtitle = _resolveCompletedSegmentSubtitle(rawSegmentActivity, rawSegmentTitle, prompt, title, isProcessed: isProcessed);

    final outcome = segment['Outcome'];
    final cardColor = outcomeAccentColor(theme, outcome);
    final backgroundColor = outcomeBackgroundColor(theme, outcome);
    final icon = _resolveOutcomeIcon(outcome);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        color: backgroundColor,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: cardColor.withValues(alpha: 0.3), width: 1),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon, color: cardColor),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: cardColor),
                        ),
                        const SizedBox(height: 4),
                        if (subtitle.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(subtitle, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
              if (narrative.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(narrative, style: theme.textTheme.bodyMedium, textAlign: TextAlign.justify),
              ],
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(RpgAwesome.gem_pendant, size: 16, color: cardColor),
                  const SizedBox(width: 4),
                  Text(
                    'Outcome: ${_formatOutcome(outcome)}',
                    style: TextStyle(color: cardColor, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static bool _isProcessingPlaceholder(String? value) {
    if (value == null) return false;
    final normalized = value.trim().toLowerCase();
    if (normalized.isEmpty) return false;
    if (normalized.startsWith('processing')) return true;
    return normalized == '...processing...' || normalized == 'processing your actions...';
  }

  String _resolveCompletedSegmentTitle(String? rawSegmentTitle, String narrative, String? segmentActivity, String? prompt) {
    if (rawSegmentTitle != null && rawSegmentTitle.isNotEmpty && !_isProcessingPlaceholder(rawSegmentTitle)) {
      return rawSegmentTitle;
    }

    if (narrative.isNotEmpty) {
      final trimmedNarrative = narrative.trim();
      final sentenceBreak = trimmedNarrative.indexOf(RegExp(r'[.!?]'));
      if (sentenceBreak > 0) {
        return trimmedNarrative.substring(0, sentenceBreak + 1).trim();
      }
      return trimmedNarrative;
    }

    if (segmentActivity != null && segmentActivity.trim().isNotEmpty) {
      return segmentActivity.trim();
    }

    if (prompt != null && prompt.trim().isNotEmpty) {
      return prompt.trim();
    }

    return 'Segment';
  }

  String _resolveCompletedSegmentSubtitle(
    String? rawSegmentActivity,
    String? segmentTitle,
    String? prompt,
    String title, {
    required bool isProcessed,
  }) {
    final candidates = <String?>[rawSegmentActivity, segmentTitle, prompt];

    final normalizedTitle = title.trim().toLowerCase();

    for (final candidate in candidates) {
      if (candidate == null) continue;
      final trimmed = candidate.trim();
      if (trimmed.isEmpty) continue;
      if (_isProcessingPlaceholder(trimmed)) {
        // Skip placeholders and generic copy once a segment is completed.
        continue;
      }
      if (trimmed.toLowerCase() == normalizedTitle) continue;
      return trimmed;
    }

    // If nothing else is suitable and the short status was a placeholder
    // while the segment is still processing, fall back to a generic label.
    if (!isProcessed &&
        rawSegmentActivity != null &&
        rawSegmentActivity.trim().isNotEmpty &&
        !_isProcessingPlaceholder(rawSegmentActivity)) {
      return rawSegmentActivity.trim();
    }

    return '';
  }

  String _extractSegmentNarrative(Map<String, dynamic> segment) {
    final clientEvents = segment['ClientEvents'] as List<dynamic>?;
    if (clientEvents != null && clientEvents.isNotEmpty) {
      final characterName = widget.character.name;
      final opponentName = _extractOpponentName(segment);

      final descriptions = clientEvents
          .map((event) {
            if (event is! Map<String, dynamic>) {
              return event.toString();
            }

            // Check if this is a combat event and use combat narrative
            if (CombatNarrative.isCombatEvent(event)) {
              return CombatNarrative.generateEventNarrative(
                event,
                characterName: characterName,
                opponentName: opponentName,
              );
            }

            // Otherwise use the standard description
            return event['Description']?.toString() ?? '';
          })
          .where((text) => text.trim().isNotEmpty)
          .toList();

      if (descriptions.isNotEmpty) {
        return descriptions.join('\n\n');
      }
    }

    final narrative = segment['Narrative']?.toString() ?? '';
    if (narrative.trim().isNotEmpty) {
      return narrative.trim();
    }

    final segmentTitle = segment['SegmentTitle']?.toString() ?? '';
    if (segmentTitle.trim().isNotEmpty) {
      return segmentTitle.trim();
    }

    return '';
  }

  String _extractOpponentName(Map<String, dynamic> segment) {
    // Try to extract opponent name from segment data
    final opponentData = segment['Opponent'] as Map<String, dynamic>?;
    if (opponentData != null) {
      final name = opponentData['Name'] ?? opponentData['OpponentName'];
      if (name is String && name.isNotEmpty) {
        return name;
      }
    }

    // Check ClientEvents for opponent information
    final clientEvents = segment['ClientEvents'] as List<dynamic>?;
    if (clientEvents != null) {
      for (final event in clientEvents) {
        if (event is Map<String, dynamic> && CombatNarrative.isCombatEvent(event)) {
          final data = event['Data'] as Map<String, dynamic>?;
          final oppOffensive = data?['OpponentOffensive'] as Map<String, dynamic>?;
          if (oppOffensive != null) {
            final name = oppOffensive['Name'];
            if (name is String && name.isNotEmpty) {
              return name;
            }
          }
        }
      }
    }

    return 'the opponent';
  }

  String _outcomeToString(dynamic outcome) {
    if (outcome is String) {
      return outcome.toLowerCase();
    }
    if (outcome is Map && outcome['Type'] is String) {
      return (outcome['Type'] as String).toLowerCase();
    }
    return 'normal';
  }

  String _formatOutcome(dynamic outcome) {
    final outcomeStr = _outcomeToString(outcome);
    if (outcomeStr.isEmpty) {
      return 'Unknown';
    }
    return outcomeStr[0].toUpperCase() + outcomeStr.substring(1);
  }

  IconData _resolveOutcomeIcon(dynamic outcome) {
    switch (normalizedOutcomeType(outcome)) {
      case 'death':
        return RpgAwesome.skull;
      case 'failure':
      case 'failed':
        return RpgAwesome.broken_heart;
      default:
        return RpgAwesome.trophy;
    }
  }
}
