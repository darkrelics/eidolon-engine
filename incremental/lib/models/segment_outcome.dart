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
