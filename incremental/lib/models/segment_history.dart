import 'package:eidolon_incremental/utils/json_parser.dart';

/// Segment history model for tracking completed story segments
class SegmentHistoryEntry {
  final String activeSegmentId;
  final String segmentId;
  final String storyInstanceId;
  final String storyId;
  final String segmentType;
  final String outcome;
  final Map<String, dynamic> skillXP;
  final Map<String, dynamic> attributeXP;
  final Map<String, dynamic>? challengeResults;
  final Map<String, dynamic>? combatState;
  final DateTime completedAt;
  final String? narrative;
  final int segmentNumber;

  SegmentHistoryEntry({
    required this.activeSegmentId,
    required this.segmentId,
    required this.storyInstanceId,
    required this.storyId,
    required this.segmentType,
    required this.outcome,
    required this.skillXP,
    required this.attributeXP,
    this.challengeResults,
    this.combatState,
    required this.completedAt,
    this.narrative,
    required this.segmentNumber,
  });

  factory SegmentHistoryEntry.fromJson(Map<String, dynamic> json) {
    return SegmentHistoryEntry(
      activeSegmentId: json['ActiveSegmentID'] ?? '',
      segmentId: json['SegmentID'] ?? '',
      storyInstanceId: json['StoryInstanceID'] ?? '',
      storyId: json['StoryID'] ?? '',
      segmentType: json['SegmentType'] ?? 'mechanical',
      outcome: json['Outcome'] ?? 'normal',
      skillXP: json['SkillXP'] ?? {},
      attributeXP: json['AttributeXP'] ?? {},
      challengeResults: json['ChallengeResults'],
      combatState: json['CombatState'],
      completedAt: json['CompletedAt'] != null
          ? DateTime.parse(json['CompletedAt'])
          : DateTime.now(),
      narrative: json['Narrative'],
      segmentNumber: json['SegmentNumber'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'ActiveSegmentID': activeSegmentId,
      'SegmentID': segmentId,
      'StoryInstanceID': storyInstanceId,
      'StoryID': storyId,
      'SegmentType': segmentType,
      'Outcome': outcome,
      'SkillXP': skillXP,
      'AttributeXP': attributeXP,
      if (challengeResults != null) 'ChallengeResults': challengeResults,
      if (combatState != null) 'CombatState': combatState,
      'CompletedAt': completedAt.toIso8601String(),
      if (narrative != null) 'Narrative': narrative,
      'SegmentNumber': segmentNumber,
    };
  }

  /// Check if this segment resulted in success
  bool get isSuccess =>
      outcome == 'exceptional' || outcome == 'normal' || outcome == 'minimal';

  /// Check if this segment resulted in failure
  bool get isFailure => outcome == 'failure' || outcome == 'death';

  /// Get total XP earned from this segment
  int get totalXP {
    return JsonParser.sumMapValues(skillXP) +
        JsonParser.sumMapValues(attributeXP);
  }

  /// Get a display-friendly outcome string
  String get outcomeDisplay {
    switch (outcome.toLowerCase()) {
      case 'exceptional':
        return 'Exceptional Success';
      case 'normal':
        return 'Success';
      case 'minimal':
        return 'Marginal Success';
      case 'failure':
        return 'Failed';
      case 'death':
        return 'Death';
      default:
        return outcome;
    }
  }

  /// Get the color associated with the outcome
  String getOutcomeColor() {
    switch (outcome.toLowerCase()) {
      case 'exceptional':
        return '#4CAF50'; // Green
      case 'normal':
        return '#2196F3'; // Blue
      case 'minimal':
        return '#FF9800'; // Orange
      case 'failure':
        return '#F44336'; // Red
      case 'death':
        return '#000000'; // Black
      default:
        return '#9E9E9E'; // Grey
    }
  }
}

/// Story history model for tracking completed stories
class StoryHistoryEntry {
  final String characterId;
  final String storyInstanceId;
  final String storyId;
  final String storyTitle;
  final DateTime startedAt;
  final DateTime? completedAt;
  final String finalOutcome;
  final List<SegmentHistoryEntry> segments;
  final Map<String, dynamic> totalSkillXP;
  final Map<String, dynamic> totalAttributeXP;

  StoryHistoryEntry({
    required this.characterId,
    required this.storyInstanceId,
    required this.storyId,
    required this.storyTitle,
    required this.startedAt,
    this.completedAt,
    required this.finalOutcome,
    required this.segments,
    required this.totalSkillXP,
    required this.totalAttributeXP,
  });

  factory StoryHistoryEntry.fromJson(Map<String, dynamic> json) {
    return StoryHistoryEntry(
      characterId: json['CharacterID'] ?? '',
      storyInstanceId: json['StoryInstanceID'] ?? '',
      storyId: json['StoryID'] ?? '',
      storyTitle: json['StoryTitle'] ?? 'Unknown Story',
      startedAt: json['StartedAt'] != null
          ? DateTime.parse(json['StartedAt'])
          : DateTime.now(),
      completedAt: json['CompletedAt'] != null
          ? DateTime.parse(json['CompletedAt'])
          : null,
      finalOutcome: json['FinalOutcome'] ?? 'abandoned',
      segments:
          (json['SegmentHistory'] as List<dynamic>?)
              ?.map((s) => SegmentHistoryEntry.fromJson(s))
              .toList() ??
          [],
      totalSkillXP: json['SkillXPAwarded'] ?? {},
      totalAttributeXP: json['AttributeXPAwarded'] ?? {},
    );
  }

  /// Check if the story was completed successfully
  bool get isCompleted => completedAt != null && finalOutcome != 'abandoned';

  /// Check if the story was abandoned
  bool get isAbandoned => finalOutcome == 'abandoned';

  /// Get the total duration of the story
  Duration get duration {
    final endTime = completedAt ?? DateTime.now();
    return endTime.difference(startedAt);
  }

  /// Get total XP earned from the story
  int get totalXP {
    return JsonParser.sumMapValues(totalSkillXP) +
        JsonParser.sumMapValues(totalAttributeXP);
  }
}
