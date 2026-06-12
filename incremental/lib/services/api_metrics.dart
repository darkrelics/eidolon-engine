import 'package:flutter/foundation.dart';

/// Simple API metrics collection for tracking polling behavior.
///
/// Used to measure baseline API call patterns and verify optimization improvements.
/// This is a temporary instrumentation class for debugging R3-T1.
class ApiMetrics {
  static final Map<String, int> _callCounts = {};
  static final List<_ApiCall> _callHistory = [];
  static DateTime? _segmentStartTime;
  static int _segmentNumber = 0;

  /// Record an API call with endpoint and optional details
  static void recordCall(String endpoint, {String? details}) {
    final now = DateTime.now();
    final call = _ApiCall(
      timestamp: now,
      endpoint: endpoint,
      details: details,
      segmentNumber: _segmentNumber,
    );

    _callHistory.add(call);
    _callCounts[endpoint] = (_callCounts[endpoint] ?? 0) + 1;

    // Calculate elapsed time since segment start
    String elapsed = '';
    if (_segmentStartTime != null) {
      final duration = now.difference(_segmentStartTime!);
      elapsed = ' (+${duration.inSeconds}s)';
    }

    debugPrint(
      '[API-METRICS] ${_formatTime(now)}$elapsed: $endpoint${details != null ? ' ($details)' : ''} [total: ${_callCounts[endpoint]}]',
    );
  }

  /// Mark the start of a new segment
  static void startSegment() {
    _segmentNumber++;
    _segmentStartTime = DateTime.now();
    _callCounts.clear();

    debugPrint('');
    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('[API-METRICS] SEGMENT #$_segmentNumber STARTED');
    debugPrint('[API-METRICS] Time: ${_formatTime(_segmentStartTime!)}');
    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('');
  }

  /// Mark the end of current segment and print summary
  static void endSegment() {
    if (_segmentStartTime == null) {
      debugPrint(
        '[API-METRICS] Warning: endSegment called without startSegment',
      );
      return;
    }

    final endTime = DateTime.now();
    final duration = endTime.difference(_segmentStartTime!);
    final totalCalls = _callCounts.values.fold(0, (sum, count) => sum + count);

    debugPrint('');
    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('[API-METRICS] SEGMENT #$_segmentNumber COMPLETE');
    debugPrint(
      '[API-METRICS] Duration: ${duration.inSeconds}s (${duration.inMinutes}m ${duration.inSeconds % 60}s)',
    );
    debugPrint('[API-METRICS] Total API calls: $totalCalls');
    debugPrint('───────────────────────────────────────────────────────────');

    if (_callCounts.isNotEmpty) {
      debugPrint('[API-METRICS] Breakdown by endpoint:');
      final sortedEntries = _callCounts.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));

      for (final entry in sortedEntries) {
        final percentage = (entry.value / totalCalls * 100).toStringAsFixed(1);
        debugPrint(
          '[API-METRICS]   ${entry.key}: ${entry.value} calls ($percentage%)',
        );
      }
    } else {
      debugPrint('[API-METRICS] No API calls recorded');
    }

    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('');

    // Reset for next segment. Clearing _callCounts is important so that a
    // bogus second endSegment() call (which would still be caught by the
    // _segmentStartTime guard above, but defensively) cannot report stale counts.
    _segmentStartTime = null;
    _callCounts.clear();
  }

  /// Get total call count for current segment
  static int getTotalCalls() {
    return _callCounts.values.fold(0, (sum, count) => sum + count);
  }

  /// Get call count for specific endpoint
  static int getCallCount(String endpoint) {
    return _callCounts[endpoint] ?? 0;
  }

  /// Get full call history for analysis (for debugging/testing only)
  @visibleForTesting
  static List<Map<String, dynamic>> getCallHistory({int? forSegment}) {
    final calls = forSegment == null
        ? _callHistory
        : _callHistory.where((call) => call.segmentNumber == forSegment);

    return List.unmodifiable(
      calls.map(
        (call) => {
          'timestamp': call.timestamp.toIso8601String(),
          'endpoint': call.endpoint,
          'details': call.details,
          'segmentNumber': call.segmentNumber,
        },
      ),
    );
  }

  /// Clear all metrics
  static void reset() {
    _callCounts.clear();
    _callHistory.clear();
    _segmentStartTime = null;
    _segmentNumber = 0;
    debugPrint('[API-METRICS] Metrics reset');
  }

  /// Print current session summary
  static void printSessionSummary() {
    if (_callHistory.isEmpty) {
      debugPrint('[API-METRICS] No API calls recorded in this session');
      return;
    }

    final segmentGroups = <int, List<_ApiCall>>{};
    for (final call in _callHistory) {
      segmentGroups.putIfAbsent(call.segmentNumber, () => []).add(call);
    }

    debugPrint('');
    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('[API-METRICS] SESSION SUMMARY');
    debugPrint('[API-METRICS] Total segments tracked: ${segmentGroups.length}');
    debugPrint('[API-METRICS] Total API calls: ${_callHistory.length}');
    debugPrint('───────────────────────────────────────────────────────────');

    for (final segmentNum in segmentGroups.keys.toList()..sort()) {
      final calls = segmentGroups[segmentNum]!;
      final callsByEndpoint = <String, int>{};

      for (final call in calls) {
        callsByEndpoint[call.endpoint] =
            (callsByEndpoint[call.endpoint] ?? 0) + 1;
      }

      debugPrint('[API-METRICS] Segment #$segmentNum: ${calls.length} calls');
      for (final entry in callsByEndpoint.entries) {
        debugPrint('[API-METRICS]   ${entry.key}: ${entry.value}');
      }
    }

    debugPrint('═══════════════════════════════════════════════════════════');
    debugPrint('');
  }

  static String _formatTime(DateTime time) {
    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}.'
        '${(time.millisecond ~/ 100).toString()}';
  }
}

/// Internal class to track individual API calls
class _ApiCall {
  final DateTime timestamp;
  final String endpoint;
  final String? details;
  final int segmentNumber;

  _ApiCall({
    required this.timestamp,
    required this.endpoint,
    this.details,
    required this.segmentNumber,
  });

  @override
  String toString() {
    final time = ApiMetrics._formatTime(timestamp);
    return '$time: $endpoint${details != null ? ' ($details)' : ''}';
  }
}
