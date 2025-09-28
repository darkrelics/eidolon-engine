/// Story metadata from API
class StoryMetadata {
  final String storyID;
  final String title;
  final String description;
  final String type;
  final bool available;
  final int cooldownRemaining;
  final int estimatedDuration;
  final Map<String, dynamic> prerequisites;
  final Map<String, num> difficultyMap;
  final Map<String, String> rewardTiers;
  final double baseXPMultiplier;

  StoryMetadata({
    required this.storyID,
    required this.title,
    required this.description,
    required this.type,
    required this.available,
    required this.cooldownRemaining,
    required this.estimatedDuration,
    required this.prerequisites,
    required this.difficultyMap,
    required this.rewardTiers,
    required this.baseXPMultiplier,
  });

  factory StoryMetadata.fromJson(Map<String, dynamic> json) {
    return StoryMetadata(
      storyID: json['StoryID'] as String,
      title: json['Title'] as String,
      description: json['Description'] as String,
      type: json['Type'] as String,
      available: json['Available'] as bool,
      cooldownRemaining: json['CooldownRemaining'] as int? ?? 0,
      estimatedDuration: json['EstimatedDuration'] as int? ?? 0,
      prerequisites: json['Prerequisites'] as Map<String, dynamic>? ?? {},
      difficultyMap: (json['DifficultyMap'] as Map<String, dynamic>? ?? {}).map(
        (key, value) => MapEntry(key, (value as num).toDouble()),
      ),
      rewardTiers: (json['RewardTiers'] as Map<String, dynamic>? ?? {}).map(
        (key, value) => MapEntry(key, value.toString()),
      ),
      baseXPMultiplier: (json['BaseXPMultiplier'] as num? ?? 0.5).toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'StoryID': storyID,
      'Title': title,
      'Description': description,
      'Type': type,
      'Available': available,
      'CooldownRemaining': cooldownRemaining,
      'EstimatedDuration': estimatedDuration,
      'Prerequisites': prerequisites,
      'DifficultyMap': difficultyMap,
      'RewardTiers': rewardTiers,
      'BaseXPMultiplier': baseXPMultiplier,
    };
  }
}

/// Story segment data
class StorySegment {
  final String segmentID;
  final String storyID;
  final String type;
  final int timeRemaining;
  final String? content;
  final List<SegmentOption>? options;
  final String? segmentTitle;
  final String? segmentActivity;
  final String? narrative;
  final String? opponentID;

  StorySegment({
    required this.segmentID,
    required this.storyID,
    required this.type,
    required this.timeRemaining,
    this.content,
    this.options,
    this.segmentTitle,
    this.segmentActivity,
    this.narrative,
    this.opponentID,
  });

  factory StorySegment.fromJson(Map<String, dynamic> json) {
    return StorySegment(
      segmentID: json['SegmentID'] as String,
      storyID: json['StoryID'] as String,
      type: json['Type'] as String,
      timeRemaining: json['TimeRemaining'] as int? ?? 0,
      content: json['Content'] as String?,
      options: (json['Options'] as List<dynamic>?)
          ?.map((o) => SegmentOption.fromJson(o as Map<String, dynamic>))
          .toList(),
      segmentTitle: json['SegmentTitle'] as String?,
      segmentActivity: json['SegmentActivity'] as String?,
      narrative: json['Narrative'] as String?,
      opponentID: json['OpponentID'] as String?,
    );
  }
}

/// Option for decision segments
class SegmentOption {
  final String id;
  final String text;

  SegmentOption({required this.id, required this.text});

  factory SegmentOption.fromJson(Map<String, dynamic> json) {
    return SegmentOption(
      id: json['Id'] as String,
      text: json['Text'] as String,
    );
  }
}
