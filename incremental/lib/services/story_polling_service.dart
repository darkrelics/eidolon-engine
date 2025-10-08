import 'dart:async';

import 'package:flutter/foundation.dart';
import 'api_service.dart';

/// Server-authoritative story polling service.
///
/// Uses GET /segment/status exclusively for all polling operations.
/// This endpoint includes:
/// - TimeRemaining (server-calculated)
/// - ActiveSegmentID (for completion detection)
/// - ProcessingStatus, narrative, outcomes
///
/// Design: 2 API calls per segment
/// - Initial check: GET /segment/status to get TimeRemaining
/// - Completion check: GET /segment/status after waiting TimeRemaining
class StoryPollingService {
  StoryPollingService({required ApiService apiService}) : _apiService = apiService;

  final ApiService _apiService;

  String? _characterId;
  Timer? _pollingTimer;
  bool _isPolling = false;
  int _consecutiveErrors = 0;
  static const int _maxConsecutiveErrors = 3;
  static const int _errorRetryDelaySeconds = 30;

  void dispose() {
    stopPolling();
  }

  void stopPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = null;
    _isPolling = false;
    _characterId = null;
    _consecutiveErrors = 0;
  }

  /// Start polling for the character's active story.
  ///
  /// Callbacks:
  /// - onStatusUpdate: Called with segment status data from GET /segment/status
  /// - onStoryComplete: Called when ActiveSegmentID becomes null
  /// - onError: Called when API errors occur
  void startPolling({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    if (_isPolling && _characterId == characterId) {
      debugPrint('StoryPollingService: Already polling for character $characterId');
      return;
    }

    stopPolling();
    _characterId = characterId;
    _isPolling = true;
    _consecutiveErrors = 0;

    debugPrint('StoryPollingService: Started polling for character $characterId');

    _pollOnce(
      characterId: characterId,
      onStatusUpdate: onStatusUpdate,
      onStoryComplete: onStoryComplete,
      onError: onError,
    );
  }

  /// Single poll iteration - gets status and schedules next check.
  Future<void> _pollOnce({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) async {
    if (!_isPolling || _characterId != characterId) {
      debugPrint('StoryPollingService: Polling stopped before execution');
      return;
    }

    try {
      // Single API call - GET /segment/status includes all needed data
      final segmentStatus = await _apiService.getSegmentStatus(characterId: characterId);

      // Reset error counter on successful call
      _consecutiveErrors = 0;

      // Update UI with segment status
      onStatusUpdate(segmentStatus);

      // Check if story is complete (ActiveSegmentID will be null)
      final activeSegmentId = segmentStatus['ActiveSegmentID'] as String?;
      if (activeSegmentId == null) {
        debugPrint('StoryPollingService: Story complete - stopping polling');
        stopPolling();
        onStoryComplete();
        return;
      }

      // Get server-calculated TimeRemaining
      final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;

      if (timeRemaining > 0) {
        // Segment in progress - wait exact duration then check again
        debugPrint('StoryPollingService: Segment in progress, checking again in $timeRemaining seconds');
        _scheduleNextPoll(
          Duration(seconds: timeRemaining),
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onStoryComplete: onStoryComplete,
          onError: onError,
        );
      } else {
        // Segment complete - brief delay then check for next segment
        debugPrint('StoryPollingService: Segment complete, checking for next segment in 2 seconds');
        _scheduleNextPoll(
          const Duration(seconds: 2),
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onStoryComplete: onStoryComplete,
          onError: onError,
        );
      }
    } catch (e) {
      debugPrint('StoryPollingService: Polling error: $e');
      _consecutiveErrors++;

      // Check for "no active segment" which indicates story completion
      final errorMsg = e.toString().toLowerCase();
      if (errorMsg.contains('no active segment') || errorMsg.contains('404')) {
        debugPrint('StoryPollingService: No active segment - story complete');
        stopPolling();
        onStoryComplete();
        return;
      }

      // Notify error handler
      onError?.call(e);

      // Stop polling after too many consecutive errors
      if (_consecutiveErrors >= _maxConsecutiveErrors) {
        debugPrint('StoryPollingService: Too many consecutive errors ($_consecutiveErrors) - stopping polling');
        stopPolling();
        return;
      }

      // Retry after 30 seconds on error
      debugPrint('StoryPollingService: Retrying in $_errorRetryDelaySeconds seconds (error count: $_consecutiveErrors)');
      _scheduleNextPoll(
        const Duration(seconds: _errorRetryDelaySeconds),
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onStoryComplete: onStoryComplete,
        onError: onError,
      );
    }
  }

  /// Schedule the next poll.
  void _scheduleNextPoll(
    Duration delay, {
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer(delay, () {
      _pollOnce(
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onStoryComplete: onStoryComplete,
        onError: onError,
      );
    });
  }
}
