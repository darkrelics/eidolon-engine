import 'package:eidolon_incremental/utils/time_utils.dart';

/// Active segment data from API
class ActiveSegment {
  final String activeSegmentID;
  final String storyID;
  final String? storyTitle;
  final String segmentID;
  final String segmentType;
  final String status;
  final String? segmentTitle;
  final String? segmentActivity;
  final String startTime;
  final String endTime;
  final List<dynamic>? challengeResults;
  final String? outcome;
  final String? decision;
  final String? decisionText;
  final Map<String, dynamic>? decisionOptions;
  final Map<String, dynamic>? combatState;
  final List<dynamic>? clientEvents;
  final Map<String, dynamic>? characterUpdates;
  final String? processingStatus;

  ActiveSegment({
    required this.activeSegmentID,
    required this.storyID,
    this.storyTitle,
    required this.segmentID,
    required this.segmentType,
    required this.status,
    this.segmentTitle,
    this.segmentActivity,
    required this.startTime,
    required this.endTime,
    this.challengeResults,
    this.outcome,
    this.decision,
    this.decisionText,
    this.decisionOptions,
    this.combatState,
    this.clientEvents,
    this.characterUpdates,
    this.processingStatus,
  });

  factory ActiveSegment.fromJson(Map<String, dynamic> json) {
    return ActiveSegment(
      activeSegmentID: json['ActiveSegmentID'] as String,
      storyID: json['StoryID'] as String,
      storyTitle: json['StoryTitle'] as String?,
      segmentID: json['SegmentID'] as String,
      segmentType: json['SegmentType'] as String,
      status: json['Status'] as String,
      segmentTitle: json['SegmentTitle'] as String?,
      segmentActivity: json['SegmentActivity'] as String?,
      startTime: _normalizeIsoTimestamp(json['StartTime']),
      endTime: _normalizeIsoTimestamp(json['EndTime']),
      challengeResults: json['ChallengeResults'] as List<dynamic>?,
      outcome: _extractOutcome(json['Outcome']),
      decision: json['Decision'] as String?,
      decisionText: json['DecisionText'] as String?,
      decisionOptions: json['DecisionOptions'] as Map<String, dynamic>?,
      combatState: json['CombatState'] as Map<String, dynamic>?,
      clientEvents: json['ClientEvents'] as List<dynamic>?,
      characterUpdates: json['CharacterUpdates'] as Map<String, dynamic>?,
      processingStatus: json['ProcessingStatus'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'ActiveSegmentID': activeSegmentID,
      'StoryID': storyID,
      'StoryTitle': storyTitle,
      'SegmentID': segmentID,
      'SegmentType': segmentType,
      'Status': status,
      if (segmentTitle != null) 'SegmentTitle': segmentTitle,
      if (segmentActivity != null) 'SegmentActivity': segmentActivity,
      'StartTime': startTime,
      'EndTime': endTime,
      if (challengeResults != null) 'ChallengeResults': challengeResults,
      if (outcome != null) 'Outcome': outcome,
      if (decision != null) 'Decision': decision,
      if (decisionText != null) 'DecisionText': decisionText,
      if (decisionOptions != null) 'DecisionOptions': decisionOptions,
      if (combatState != null) 'CombatState': combatState,
      if (clientEvents != null) 'ClientEvents': clientEvents,
      if (characterUpdates != null) 'CharacterUpdates': characterUpdates,
      if (processingStatus != null) 'ProcessingStatus': processingStatus,
    };
  }

  /// Calculate remaining time in seconds
  int get remainingSeconds {
    return TimeUtils.secondsUntil(endTime);
  }

  /// Check if segment timer has expired
  bool get isExpired => TimeUtils.isPast(endTime);
}

String _normalizeIsoTimestamp(dynamic value) {
  if (value is String && value.trim().isNotEmpty) {
    return value;
  }

  if (value is num) {
    return TimeUtils.fromUnix(value.toInt());
  }

  // Return a timestamp 60 seconds in the future as safe fallback
  // This prevents immediate expiration if EndTime is invalid
  return TimeUtils.futureIso(60);
}

/// Extract outcome string from various formats.
///
/// Server may send Outcome as:
/// - String: "normal", "exceptional", etc.
/// - Map with Type field: {"Type": "normal", ...}
/// - null or empty
String? _extractOutcome(dynamic value) {
  if (value == null) {
    return null;
  }

  if (value is String) {
    return value.isNotEmpty ? value : null;
  }

  if (value is Map) {
    // Try common field names for outcome type
    final type =
        value['Type'] ?? value['type'] ?? value['Outcome'] ?? value['outcome'];
    if (type is String && type.isNotEmpty) {
      return type;
    }
    return null;
  }

  return null;
}
