/// Represents a completed story with all its metadata and segments
class StoryHistoryEntry {
  final String storyId;
  final String storyTitle;
  final String storyType;
  final DateTime completedAt;
  final String outcome;
  final Duration duration;
  final Map<String, int> rewards;
  final List<SegmentHistoryEntry> segments;
  final int totalXpGained;

  const StoryHistoryEntry({
    required this.storyId,
    required this.storyTitle,
    required this.storyType,
    required this.completedAt,
    required this.outcome,
    required this.duration,
    required this.rewards,
    required this.segments,
    required this.totalXpGained,
  });

  String get outcomeCategory {
    final normalized = outcome.toLowerCase();
    if (normalized == 'exceptional' || normalized == 'success' || normalized == 'minimal') {
      return 'success';
    }
    if (normalized == 'normal') {
      return 'normal';
    }
    if (normalized == 'failure' || normalized == 'death') {
      return 'failure';
    }
    return normalized;
  }

  String get displayOutcome {
    switch (outcome.toLowerCase()) {
      case 'exceptional':
        return 'Exceptional Success';
      case 'minimal':
        return 'Minimal Success';
      case 'success':
        return 'Success';
      case 'normal':
        return 'Normal Progress';
      case 'failure':
        return 'Failure';
      case 'death':
        return 'Death';
      default:
        return outcome.isEmpty ? 'Unknown' : outcome;
    }
  }

  bool get isSuccessful => outcomeCategory == 'success';
  bool get isFailed => outcomeCategory == 'failure';

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is StoryHistoryEntry && other.storyId == storyId && other.completedAt == completedAt;
  }

  @override
  int get hashCode => storyId.hashCode ^ completedAt.hashCode;
}

/// Represents an individual segment within a story
class SegmentHistoryEntry {
  final String segmentId;
  final String title;
  final String? subtitle;
  final String narrative;
  final String outcome;
  final DateTime? completedAt;
  final Map<String, dynamic> rawData;

  const SegmentHistoryEntry({
    required this.segmentId,
    required this.title,
    required this.narrative,
    required this.outcome,
    this.subtitle,
    this.completedAt,
    this.rawData = const {},
  });

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is SegmentHistoryEntry && other.segmentId == segmentId;
  }

  @override
  int get hashCode => segmentId.hashCode;
}

/// Statistics for story history
class StoryHistoryStats {
  final int totalStories;
  final int successfulStories;
  final int normalStories;
  final int failedStories;
  final int deathStories;
  final Duration totalTimePlayed;
  final Duration averageStoryDuration;
  final int totalXpGained;

  const StoryHistoryStats({
    required this.totalStories,
    required this.successfulStories,
    required this.normalStories,
    required this.failedStories,
    required this.deathStories,
    required this.totalTimePlayed,
    required this.averageStoryDuration,
    required this.totalXpGained,
  });

  double get successRate => totalStories > 0 ? successfulStories / totalStories : 0.0;
  double get failureRate => totalStories > 0 ? failedStories / totalStories : 0.0;
}
