/// Active segment data from API
class ActiveSegment {
  final String activeSegmentID;
  final String storyID;
  final String storyTitle;
  final String segmentID;
  final String segmentType;
  final String status;
  final int startTime;
  final int endTime;
  final List<dynamic>? challengeResults;
  final String? outcome;
  final String? decision;
  final Map<String, dynamic>? decisionOptions;
  final Map<String, dynamic>? combatState;

  ActiveSegment({
    required this.activeSegmentID,
    required this.storyID,
    required this.storyTitle,
    required this.segmentID,
    required this.segmentType,
    required this.status,
    required this.startTime,
    required this.endTime,
    this.challengeResults,
    this.outcome,
    this.decision,
    this.decisionOptions,
    this.combatState,
  });

  factory ActiveSegment.fromJson(Map<String, dynamic> json) {
    return ActiveSegment(
      activeSegmentID: json['ActiveSegmentID'] as String,
      storyID: json['StoryID'] as String,
      storyTitle: json['StoryTitle'] as String,
      segmentID: json['SegmentID'] as String,
      segmentType: json['SegmentType'] as String,
      status: json['Status'] as String,
      startTime: json['StartTime'] as int,
      endTime: json['EndTime'] as int,
      challengeResults: json['ChallengeResults'] as List<dynamic>?,
      outcome: json['Outcome'] as String?,
      decision: json['Decision'] as String?,
      decisionOptions: json['DecisionOptions'] as Map<String, dynamic>?,
      combatState: json['CombatState'] as Map<String, dynamic>?,
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
      'StartTime': startTime,
      'EndTime': endTime,
      if (challengeResults != null) 'ChallengeResults': challengeResults,
      if (outcome != null) 'Outcome': outcome,
      if (decision != null) 'Decision': decision,
      if (decisionOptions != null) 'DecisionOptions': decisionOptions,
      if (combatState != null) 'CombatState': combatState,
    };
  }

  /// Calculate remaining time in seconds
  int get remainingSeconds {
    final currentTime = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final remaining = endTime - currentTime;
    return remaining > 0 ? remaining : 0;
  }

  /// Check if segment timer has expired
  bool get isExpired => remainingSeconds <= 0;
}