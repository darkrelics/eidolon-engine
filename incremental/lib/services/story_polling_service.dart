import 'dart:async';

import 'package:flutter/foundation.dart';
import 'api_service.dart';

/// Server-authoritative story polling service.
///
/// Polling strategy:
/// 1. GET /segment/status immediately to check current state
/// 2. If ProcessingStatus='pending', use server's PollAfter field for next check
/// 3. If ProcessingStatus='processed', wait for TimeRemaining to reach 0
/// 4. GET /character to reload character state (wounds, XP, etc.)
/// 5. GET /segment/status to check for next segment
/// 6. Repeat until story complete (404 response)
class StoryPollingService {
  StoryPollingService({required ApiService apiService}) : _apiService = apiService;

  final ApiService _apiService;

  String? _characterId;
  Timer? _pollingTimer;
  bool _isPolling = false;
  int _consecutiveErrors = 0;
  static const int _maxConsecutiveErrors = 3;
  static const int _errorRetryDelaySeconds = 30;
  static const int _defaultPollDelaySeconds = 60;  // Fallback if no PollAfter

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
  /// - onCharacterReload: Called with updated character from GET /character (at segment boundaries)
  /// - onStoryComplete: Called when ActiveSegmentID becomes null
  /// - onError: Called when API errors occur
  void startPolling({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function(Map<String, dynamic> character) onCharacterReload,
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

    // Check immediately to get current status and PollAfter guidance from server
    _pollOnce(
      characterId: characterId,
      onStatusUpdate: onStatusUpdate,
      onCharacterReload: onCharacterReload,
      onStoryComplete: onStoryComplete,
      onError: onError,
    );
  }

  /// Single poll iteration - gets status and schedules next check.
  Future<void> _pollOnce({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function(Map<String, dynamic> character) onCharacterReload,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) async {
    if (!_isPolling || _characterId != characterId) {
      debugPrint('StoryPollingService: Polling stopped before execution');
      return;
    }

    try {
      // Get segment status
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

      // Check ProcessingStatus to determine next action
      final processingStatus = (segmentStatus['ProcessingStatus'] as String?)?.toLowerCase() ?? '';
      final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;

      if (processingStatus == 'pending') {
        // Server still processing - use PollAfter if available, fallback to default
        final pollAfter = segmentStatus['PollAfter'] as String?;
        Duration delay = const Duration(seconds: _defaultPollDelaySeconds);

        if (pollAfter != null && pollAfter.isNotEmpty) {
          try {
            final pollTime = DateTime.parse(pollAfter).toUtc();
            final now = DateTime.now().toUtc();
            final waitSeconds = pollTime.difference(now).inSeconds;
            if (waitSeconds > 0) {
              delay = Duration(seconds: waitSeconds);
            } else {
              // PollAfter is in the past, poll immediately
              delay = Duration.zero;
            }
          } catch (e) {
            debugPrint('StoryPollingService: Error parsing PollAfter, using default delay: $e');
          }
        }

        debugPrint('StoryPollingService: Segment still processing (pending), retrying in ${delay.inSeconds}s');
        _scheduleNextPoll(
          delay,
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onCharacterReload: onCharacterReload,
          onStoryComplete: onStoryComplete,
          onError: onError,
        );
      } else if (processingStatus == 'processed' && timeRemaining > 0) {
        // Segment processed but timer not expired - wait for timer then reload character
        debugPrint('StoryPollingService: Segment processed, waiting $timeRemaining seconds then reloading character');

        // Schedule character reload at segment end
        Timer(Duration(seconds: timeRemaining), () async {
          if (!_isPolling || _characterId != characterId) return;

          try {
            // Reload character to get updated state (wounds, XP, attributes)
            debugPrint('StoryPollingService: Reloading character at segment boundary');
            final character = await _apiService.getCharacterById(characterId);

            if (character != null) {
              onCharacterReload(character.toJson());
            }

            // Brief delay then check for next segment
            _scheduleNextPoll(
              const Duration(seconds: 2),
              characterId: characterId,
              onStatusUpdate: onStatusUpdate,
              onCharacterReload: onCharacterReload,
              onStoryComplete: onStoryComplete,
              onError: onError,
            );
          } catch (e) {
            debugPrint('StoryPollingService: Error reloading character: $e');
            onError?.call(e);

            // Retry with backoff
            _consecutiveErrors++;
            if (_consecutiveErrors >= _maxConsecutiveErrors) {
              debugPrint('StoryPollingService: Too many consecutive errors - stopping');
              stopPolling();
              return;
            }

            _scheduleNextPoll(
              const Duration(seconds: _errorRetryDelaySeconds),
              characterId: characterId,
              onStatusUpdate: onStatusUpdate,
              onCharacterReload: onCharacterReload,
              onStoryComplete: onStoryComplete,
              onError: onError,
            );
          }
        });
      } else {
        // Segment complete (TimeRemaining = 0) - reload character and check for next segment
        debugPrint('StoryPollingService: Segment complete, reloading character');

        try {
          final character = await _apiService.getCharacterById(characterId);
          if (character != null) {
            onCharacterReload(character.toJson());
          }
        } catch (e) {
          debugPrint('StoryPollingService: Error reloading character: $e');
          onError?.call(e);
        }

        // Brief delay then check for next segment
        _scheduleNextPoll(
          const Duration(seconds: 2),
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onCharacterReload: onCharacterReload,
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
        onCharacterReload: onCharacterReload,
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
    required void Function(Map<String, dynamic> character) onCharacterReload,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer(delay, () {
      _pollOnce(
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onCharacterReload: onCharacterReload,
        onStoryComplete: onStoryComplete,
        onError: onError,
      );
    });
  }
}
