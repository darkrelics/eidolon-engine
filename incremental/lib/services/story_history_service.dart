import 'package:eidolon_incremental/models/story_history.dart';

/// Service for processing and managing story history data
class StoryHistoryService {
  static const Duration _maxReasonableDuration = Duration(hours: 24);

  /// Processes raw segment data into structured story history entries
  List<StoryHistoryEntry> processStoryHistory(
    List<Map<String, dynamic>> rawSegments,
  ) {
    if (rawSegments.isEmpty) return const [];

    // Group segments by story instance
    final segmentsByStory = _groupSegmentsByStory(rawSegments);

    // Convert each story group into a StoryHistoryEntry
    final entries = <StoryHistoryEntry>[];
    for (final storySegments in segmentsByStory.values) {
      final entry = _createStoryHistoryEntry(storySegments);
      if (entry != null) {
        entries.add(entry);
      }
    }

    // Sort by completion date (newest first)
    entries.sort((a, b) => b.completedAt.compareTo(a.completedAt));

    return entries;
  }

  /// Calculates statistics from story history entries
  StoryHistoryStats calculateStats(List<StoryHistoryEntry> entries) {
    if (entries.isEmpty) {
      return const StoryHistoryStats(
        totalStories: 0,
        successfulStories: 0,
        normalStories: 0,
        failedStories: 0,
        deathStories: 0,
        totalTimePlayed: Duration.zero,
        averageStoryDuration: Duration.zero,
        totalXpGained: 0,
      );
    }

    final successfulStories = entries
        .where((e) => e.outcomeCategory == 'success')
        .length;
    final normalStories = entries
        .where((e) => e.outcomeCategory == 'normal')
        .length;
    final failedStories = entries.where((e) => e.outcome == 'failure').length;
    final deathStories = entries.where((e) => e.outcome == 'death').length;

    final totalTimePlayed = entries.fold<Duration>(
      Duration.zero,
      (sum, entry) => sum + entry.duration,
    );

    final averageDuration = entries.isNotEmpty
        ? Duration(
            milliseconds: totalTimePlayed.inMilliseconds ~/ entries.length,
          )
        : Duration.zero;

    final totalXpGained = entries.fold<int>(
      0,
      (sum, entry) => sum + entry.totalXpGained,
    );

    return StoryHistoryStats(
      totalStories: entries.length,
      successfulStories: successfulStories,
      normalStories: normalStories,
      failedStories: failedStories,
      deathStories: deathStories,
      totalTimePlayed: totalTimePlayed,
      averageStoryDuration: averageDuration,
      totalXpGained: totalXpGained,
    );
  }

  /// Filters story history entries based on outcome
  List<StoryHistoryEntry> filterByOutcome(
    List<StoryHistoryEntry> entries,
    String filter,
  ) {
    if (filter == 'all') return List.from(entries);

    return entries.where((entry) {
      switch (filter) {
        case 'success':
          return entry.outcomeCategory == 'success';
        case 'normal':
          return entry.outcomeCategory == 'normal';
        case 'failure':
          return entry.outcomeCategory == 'failure';
        default:
          return true;
      }
    }).toList();
  }

  /// Sorts story history entries
  List<StoryHistoryEntry> sortEntries(
    List<StoryHistoryEntry> entries,
    String sortBy,
  ) {
    final sorted = List<StoryHistoryEntry>.from(entries);

    switch (sortBy) {
      case 'recent':
        sorted.sort((a, b) => b.completedAt.compareTo(a.completedAt));
        break;
      case 'oldest':
        sorted.sort((a, b) => a.completedAt.compareTo(b.completedAt));
        break;
      case 'duration':
        sorted.sort((a, b) => b.duration.compareTo(a.duration));
        break;
      case 'rewards':
        sorted.sort((a, b) => b.totalXpGained.compareTo(a.totalXpGained));
        break;
    }

    return sorted;
  }

  Map<String, List<Map<String, dynamic>>> _groupSegmentsByStory(
    List<Map<String, dynamic>> segments,
  ) {
    final grouped = <String, List<Map<String, dynamic>>>{};

    for (final segment in segments) {
      final storyId =
          segment['StoryID']?.toString() ??
          segment['StoryInstanceID']?.toString() ??
          'unknown';
      grouped.putIfAbsent(storyId, () => []).add(segment);
    }

    return grouped;
  }

  StoryHistoryEntry? _createStoryHistoryEntry(
    List<Map<String, dynamic>> segments,
  ) {
    if (segments.isEmpty) return null;

    // Sort segments by completion time
    segments.sort(_compareSegmentsByTime);

    final storyId = segments.first['StoryID']?.toString() ?? 'unknown';
    final storyTitle = _selectStoryTitle(segments);
    final storyType = segments.first['StoryType']?.toString() ?? 'story';

    final startTime = _findEarliestTime(segments);
    final completionTime = _findLatestCompletionTime(segments);

    if (completionTime == null) return null;

    final duration = _calculateDuration(startTime, completionTime);
    final outcome = _determineOutcome(segments);
    final rewards = _calculateRewards(segments);
    final totalXpGained = _calculateTotalXP(segments);
    final segmentEntries = _createSegmentEntries(segments);

    return StoryHistoryEntry(
      storyId: storyId,
      storyTitle: storyTitle,
      storyType: storyType,
      completedAt: completionTime,
      outcome: outcome,
      duration: duration,
      rewards: rewards,
      segments: segmentEntries,
      totalXpGained: totalXpGained,
    );
  }

  List<SegmentHistoryEntry> _createSegmentEntries(
    List<Map<String, dynamic>> segments,
  ) {
    return segments.map((segment) {
      final segmentId =
          segment['SegmentID']?.toString() ??
          segment['ActiveSegmentID']?.toString() ??
          'unknown';
      final title = _extractSegmentTitle(segment);
      final subtitle = _extractSegmentSubtitle(segment);
      final narrative = _extractSegmentNarrative(segment);
      final outcome = segment['Outcome']?.toString() ?? 'normal';
      final completedAt = _parseDate(
        segment['CompletedAt'] ?? segment['EndTime'],
      );

      return SegmentHistoryEntry(
        segmentId: segmentId,
        title: title,
        subtitle: subtitle,
        narrative: narrative,
        outcome: outcome,
        completedAt: completedAt,
        rawData: segment,
      );
    }).toList();
  }

  String _selectStoryTitle(List<Map<String, dynamic>> segments) {
    for (final segment in segments) {
      final rawTitle = segment['StoryTitle'];
      if (rawTitle != null) {
        final title = rawTitle.toString().trim();
        if (title.isNotEmpty) {
          return title;
        }
      }
    }
    return 'Unknown Story';
  }

  DateTime? _findEarliestTime(List<Map<String, dynamic>> segments) {
    DateTime? earliest;
    for (final segment in segments) {
      final time = _parseDate(segment['StartTime'] ?? segment['CreatedAt']);
      if (time != null && (earliest == null || time.isBefore(earliest))) {
        earliest = time;
      }
    }
    return earliest;
  }

  DateTime? _findLatestCompletionTime(List<Map<String, dynamic>> segments) {
    DateTime? latest;
    for (final segment in segments) {
      final time = _parseDate(
        segment['CompletedAt'] ?? segment['EndTime'] ?? segment['ProcessedAt'],
      );
      if (time != null && (latest == null || time.isAfter(latest))) {
        latest = time;
      }
    }
    return latest;
  }

  Duration _calculateDuration(DateTime? start, DateTime? end) {
    if (start == null || end == null) return Duration.zero;

    final duration = end.difference(start);
    if (duration.isNegative) return Duration.zero;
    if (duration > _maxReasonableDuration) return _maxReasonableDuration;

    return duration;
  }

  String _determineOutcome(List<Map<String, dynamic>> segments) {
    // Check the last segment's outcome first
    for (final segment in segments.reversed) {
      final rawOutcome = segment['Outcome'];
      if (rawOutcome != null) {
        final outcome = rawOutcome.toString().trim();
        if (outcome.isNotEmpty) {
          return outcome;
        }
      }
    }
    return 'unknown';
  }

  Map<String, int> _calculateRewards(List<Map<String, dynamic>> segments) {
    final rewards = <String, int>{};
    int totalXp = 0;

    for (final segment in segments) {
      totalXp += _calculateTotalXP([segment]);
    }

    if (totalXp > 0) {
      rewards['XP'] = totalXp;
    }

    return rewards;
  }

  int _calculateTotalXP(List<Map<String, dynamic>> segments) {
    int total = 0;

    void accumulate(dynamic value) {
      if (value is Map) {
        for (final entry in value.values) {
          if (entry is num) {
            total += entry.round();
          }
        }
      }
    }

    for (final segment in segments) {
      accumulate(segment['SkillXPAwarded']);
      accumulate(segment['AttributeXPAwarded']);

      final characterUpdates = segment['CharacterUpdates'];
      if (characterUpdates is Map) {
        accumulate(characterUpdates['SkillsAwarded']);
        accumulate(characterUpdates['AttributesAwarded']);
      }
    }

    return total;
  }

  String _extractSegmentTitle(Map<String, dynamic> segment) {
    final candidates = [
      segment['SegmentTitle']?.toString(),
      segment['SegmentActivity']?.toString(),
      _extractFirstSentence(_extractSegmentNarrative(segment)),
    ];

    for (final candidate in candidates) {
      if (candidate != null &&
          candidate.trim().isNotEmpty &&
          !_isProcessingPlaceholder(candidate)) {
        return candidate.trim();
      }
    }

    return 'Segment';
  }

  String? _extractSegmentSubtitle(Map<String, dynamic> segment) {
    final title = _extractSegmentTitle(segment);
    final candidates = [
      segment['SegmentActivity']?.toString(),
      segment['Prompt']?.toString(),
    ];

    for (final candidate in candidates) {
      if (candidate != null &&
          candidate.trim().isNotEmpty &&
          !_isProcessingPlaceholder(candidate) &&
          candidate.trim().toLowerCase() != title.toLowerCase()) {
        return candidate.trim();
      }
    }

    return null;
  }

  String _extractSegmentNarrative(Map<String, dynamic> segment) {
    final clientEvents = segment['ClientEvents'] as List<dynamic>?;
    if (clientEvents != null && clientEvents.isNotEmpty) {
      final descriptions = clientEvents
          .map(
            (event) => event is Map
                ? event['Description']?.toString() ?? ''
                : event.toString(),
          )
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

    return '';
  }

  String _extractFirstSentence(String text) {
    if (text.isEmpty) return '';

    final match = RegExp(r'^[^.!?]*[.!?]').firstMatch(text);
    return match?.group(0)?.trim() ?? text;
  }

  bool _isProcessingPlaceholder(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized.isEmpty) return false;
    if (normalized.startsWith('processing')) return true;
    return normalized == '...processing...' ||
        normalized == 'processing your actions...';
  }

  DateTime? _parseDate(dynamic value) {
    if (value is DateTime) return value.toUtc();
    if (value is num) {
      final timestamp = value.toDouble();
      if (timestamp.isNaN) return null;
      if (timestamp > 1000000000000) {
        return DateTime.fromMillisecondsSinceEpoch(
          timestamp.round(),
          isUtc: true,
        );
      }
      return DateTime.fromMillisecondsSinceEpoch(
        (timestamp * 1000).round(),
        isUtc: true,
      );
    }
    if (value is String && value.isNotEmpty) {
      try {
        final trimmed = value.trim();
        final numeric = double.tryParse(trimmed);
        if (numeric != null) {
          return _parseDate(numeric);
        }
        return DateTime.parse(trimmed).toUtc();
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  int _compareSegmentsByTime(Map<String, dynamic> a, Map<String, dynamic> b) {
    final aTime = _parseDate(
      a['CompletedAt'] ?? a['EndTime'] ?? a['StartTime'],
    );
    final bTime = _parseDate(
      b['CompletedAt'] ?? b['EndTime'] ?? b['StartTime'],
    );

    if (aTime == null && bTime == null) return 0;
    if (aTime == null) return -1;
    if (bTime == null) return 1;
    return aTime.compareTo(bTime);
  }
}
