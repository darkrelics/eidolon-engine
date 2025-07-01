import 'character.dart';

/// Segment outcome from server after challenge resolution.
/// All calculations performed server-side.
class SegmentOutcome {
  final String segmentId;
  final bool success;
  final bool criticalSuccess;
  final bool criticalFailure;
  final String outcomeText;
  final Map<String, int> resourceChanges;
  final Map<String, bool> progressFlags;
  final Map<String, double> skillXPGained;
  final Map<String, double> attributeXPGained;
  final Character updatedCharacter;

  SegmentOutcome({
    required this.segmentId,
    required this.success,
    required this.criticalSuccess,
    required this.criticalFailure,
    required this.outcomeText,
    required this.resourceChanges,
    required this.progressFlags,
    required this.skillXPGained,
    required this.attributeXPGained,
    required this.updatedCharacter,
  });

  factory SegmentOutcome.fromJson(Map<String, dynamic> json) {
    return SegmentOutcome(
      segmentId: json['segmentId'] as String,
      success: json['success'] as bool,
      criticalSuccess: json['criticalSuccess'] as bool? ?? false,
      criticalFailure: json['criticalFailure'] as bool? ?? false,
      outcomeText: json['outcomeText'] as String,
      resourceChanges: Map<String, int>.from(json['resourceChanges'] ?? {}),
      progressFlags: Map<String, bool>.from(json['progressFlags'] ?? {}),
      skillXPGained: Map<String, double>.from(
        (json['skillXPGained'] ?? {}).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      attributeXPGained: Map<String, double>.from(
        (json['attributeXPGained'] ?? {}).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      updatedCharacter: Character.fromJson(
        json['updatedCharacter'] as Map<String, dynamic>,
      ),
    );
  }
}

/// Active segment being played
class ActiveSegment {
  final String segmentId;
  final String passageName;
  final String text;
  final DateTime startedAt;
  final int duration;
  final Map<String, int> requirements;
  final Challenge challenge;

  ActiveSegment({
    required this.segmentId,
    required this.passageName,
    required this.text,
    required this.startedAt,
    required this.duration,
    required this.requirements,
    required this.challenge,
  });

  /// Calculate remaining time in seconds
  int get remainingSeconds {
    final elapsed = DateTime.now().difference(startedAt).inSeconds;
    final remaining = duration - elapsed;
    return remaining > 0 ? remaining : 0;
  }

  /// Check if segment timer has expired
  bool get isExpired => remainingSeconds <= 0;

  factory ActiveSegment.fromJson(Map<String, dynamic> json) {
    return ActiveSegment(
      segmentId: json['segmentId'] as String,
      passageName: json['passageName'] as String,
      text: json['text'] as String,
      startedAt: DateTime.parse(json['startedAt'] as String),
      duration: json['duration'] as int,
      requirements: Map<String, int>.from(json['requirements'] ?? {}),
      challenge: Challenge.fromJson(json['challenge'] as Map<String, dynamic>),
    );
  }
}

/// Challenge definition from story schema
class Challenge {
  final String skill;
  final String attribute;
  final int difficulty;

  Challenge({
    required this.skill,
    required this.attribute,
    required this.difficulty,
  });

  factory Challenge.fromJson(Map<String, dynamic> json) {
    return Challenge(
      skill: json['skill'] as String,
      attribute: json['attribute'] as String,
      difficulty: json['difficulty'] as int,
    );
  }
}