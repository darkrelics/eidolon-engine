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
      segmentId: json['SegmentID'] as String,
      success: json['Success'] as bool,
      criticalSuccess: json['CriticalSuccess'] as bool? ?? false,
      criticalFailure: json['CriticalFailure'] as bool? ?? false,
      outcomeText: json['OutcomeText'] as String,
      resourceChanges: Map<String, int>.from(json['ResourceChanges'] ?? {}),
      progressFlags: Map<String, bool>.from(json['ProgressFlags'] ?? {}),
      skillXPGained: Map<String, double>.from(
        (json['SkillXPAwarded'] ?? {}).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      attributeXPGained: Map<String, double>.from(
        (json['AttributeXPAwarded'] ?? {}).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      updatedCharacter: Character.fromJson(
        json['UpdatedCharacter'] as Map<String, dynamic>,
      ),
    );
  }
}
