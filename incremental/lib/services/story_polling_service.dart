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
  StoryPollingService({required ApiService apiService})
    : _apiService = apiService;

  final ApiService _apiService;

  String? _characterId;
  Timer? _pollingTimer;
  Timer? _completionTimer;
  Timer? _recoveryTimer;
  bool _isPolling = false;
  int _consecutiveErrors = 0;
  String? _lastSeenActiveSegmentId;
  String? _lastReloadedSegmentId;
  String? _pendingCompletionSegmentId;
  static const int _maxConsecutiveErrors = 3;
  static const int _errorRetryDelaySeconds = 30;
  static const int _defaultPollDelaySeconds = 60; // Fallback if no PollAfter
  static const int _initialPollDelaySeconds =
      60; // Backend design spec: INITIAL_POLL_DELAY
  // Exponential backoff for recovery: 15s, 30s, 60s, 120s, 300s cap
  static const int _recoveryInitialDelaySeconds = 15;
  static const int _recoveryMaxDelaySeconds = 300;
  int _recoveryAttempt = 0;

  void dispose() {
    stopPolling();
  }

  void stopPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = null;
    _completionTimer?.cancel();
    _completionTimer = null;
    _recoveryTimer?.cancel();
    _recoveryTimer = null;
    _isPolling = false;
    _characterId = null;
    _consecutiveErrors = 0;
    _lastSeenActiveSegmentId = null;
    _lastReloadedSegmentId = null;
    _pendingCompletionSegmentId = null;
    _recoveryAttempt = 0;
  }

  /// Start polling for the character's active story.
  ///
  /// Parameters:
  /// - segmentStartTime: When the current segment started (for calculating initial delay).
  ///   If null, waits 60 seconds before first poll.
  ///
  /// Callbacks:
  /// - onStatusUpdate: Called with segment status data from GET /segment/status
  /// - onCharacterReload: Called with updated character from GET /character (story completion only)
  /// - onSegmentComplete: Called with segment updates for incremental cache updates
  /// - onStoryComplete: Called when ActiveSegmentID becomes null
  /// - onError: Called when API errors occur
  void startPolling({
    required String characterId,
    DateTime? segmentStartTime,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function(Map<String, dynamic> character) onCharacterReload,
    required void Function(Map<String, dynamic> segmentUpdates)
    onSegmentComplete,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    if (_isPolling && _characterId == characterId) {
      debugPrint(
        'StoryPollingService: Already polling for character $characterId',
      );
      return;
    }

    stopPolling();
    _characterId = characterId;
    _isPolling = true;
    _consecutiveErrors = 0;

    debugPrint(
      'StoryPollingService: Started polling for character $characterId',
    );

    // Calculate delay before first poll (60 seconds from segment start per backend spec)
    Duration initialDelay;
    if (segmentStartTime != null) {
      final now = DateTime.now().toUtc();
      final segmentStart = segmentStartTime.toUtc();
      final elapsedSeconds = now.difference(segmentStart).inSeconds;
      final remainingDelay = _initialPollDelaySeconds - elapsedSeconds;

      if (remainingDelay > 0) {
        initialDelay = Duration(seconds: remainingDelay);
        debugPrint(
          'StoryPollingService: Waiting $remainingDelay seconds before first poll (segment started ${elapsedSeconds}s ago)',
        );
      } else {
        // Segment started more than 60 seconds ago, poll immediately
        initialDelay = Duration.zero;
        debugPrint(
          'StoryPollingService: Polling immediately (segment started ${elapsedSeconds}s ago)',
        );
      }
    } else {
      // No start time provided, wait full 60 seconds
      initialDelay = const Duration(seconds: _initialPollDelaySeconds);
      debugPrint(
        'StoryPollingService: Waiting $_initialPollDelaySeconds seconds before first poll (no start time provided)',
      );
    }

    // Schedule first poll after initial delay
    _scheduleNextPoll(
      initialDelay,
      characterId: characterId,
      onStatusUpdate: onStatusUpdate,
      onCharacterReload: onCharacterReload,
      onSegmentComplete: onSegmentComplete,
      onStoryComplete: onStoryComplete,
      onError: onError,
    );
  }

  /// Single poll iteration - gets status and schedules next check.
  Future<void> _pollOnce({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function(Map<String, dynamic> character) onCharacterReload,
    required void Function(Map<String, dynamic> segmentUpdates)
    onSegmentComplete,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) async {
    if (!_isPolling || _characterId != characterId) {
      debugPrint('StoryPollingService: Polling stopped before execution');
      return;
    }

    try {
      // Get segment status
      final segmentStatus = await _apiService.getSegmentStatus(
        characterId: characterId,
      );

      // Cancel any stale completion timer if segment has changed
      // This handles the case where a new poll happens before the completion timer fires
      final currentActiveSegmentId =
          segmentStatus['ActiveSegmentID'] as String?;
      if (_pendingCompletionSegmentId != null &&
          _pendingCompletionSegmentId != currentActiveSegmentId) {
        debugPrint(
          'StoryPollingService: Canceling stale completion timer for segment $_pendingCompletionSegmentId',
        );
        _completionTimer?.cancel();
        _completionTimer = null;
        _pendingCompletionSegmentId = null;
      }

      // Reset error and recovery counters on successful call
      _consecutiveErrors = 0;
      _recoveryAttempt = 0;

      // Update UI with segment status
      onStatusUpdate(segmentStatus);

      // Use the already-extracted activeSegmentId
      final activeSegmentId = currentActiveSegmentId;

      if (activeSegmentId != _lastSeenActiveSegmentId) {
        // Active segment changed; reset boundary reload guard so the new segment can sync once
        _lastSeenActiveSegmentId = activeSegmentId;
        _lastReloadedSegmentId = null;
      }

      if (activeSegmentId == null) {
        debugPrint('StoryPollingService: Story complete - reloading character');

        // Reload character to get authoritative state (XP, wounds, inventory)
        try {
          final character = await _apiService.getCharacter(
            characterId: characterId,
          );
          onCharacterReload(character);
        } catch (e) {
          debugPrint(
            'StoryPollingService: Failed to reload character after completion: $e',
          );
          // Continue to onStoryComplete even if reload fails
          onError?.call(e);
        }

        stopPolling();
        onStoryComplete();
        return;
      }

      // Check ProcessingStatus to determine next action
      final processingStatus =
          (segmentStatus['ProcessingStatus'] as String?)?.toLowerCase() ?? '';
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
            debugPrint(
              'StoryPollingService: Error parsing PollAfter, using default delay: $e',
            );
          }
        }

        debugPrint(
          'StoryPollingService: Segment still processing (pending), retrying in ${delay.inSeconds}s',
        );
        _scheduleNextPoll(
          delay,
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onCharacterReload: onCharacterReload,
          onSegmentComplete: onSegmentComplete,
          onStoryComplete: onStoryComplete,
          onError: onError,
        );
      } else if (processingStatus == 'processed' && timeRemaining > 0) {
        // Segment processed but timer not expired - wait for timer then apply incremental updates
        debugPrint(
          'StoryPollingService: Segment processed, waiting $timeRemaining seconds then applying updates',
        );

        // Check if we already have a pending completion for this segment
        if (_pendingCompletionSegmentId == activeSegmentId) {
          debugPrint(
            'StoryPollingService: Completion timer already scheduled for segment $activeSegmentId - skipping duplicate',
          );
          return;
        }

        // Cancel any existing completion timer to prevent race conditions
        _completionTimer?.cancel();
        _completionTimer = null;

        // Track which segment we're waiting for
        final pendingSegmentId = activeSegmentId;
        _pendingCompletionSegmentId = pendingSegmentId;

        // Capture the current segment status to avoid closure issues
        final capturedSegmentStatus = Map<String, dynamic>.from(segmentStatus);

        // Schedule segment completion at segment end
        _completionTimer = Timer(Duration(seconds: timeRemaining), () async {
          // Clear pending completion tracking
          if (_pendingCompletionSegmentId == pendingSegmentId) {
            _pendingCompletionSegmentId = null;
          }
          _completionTimer = null;

          // Verify polling is still active for this character
          if (!_isPolling || _characterId != characterId) {
            debugPrint(
              'StoryPollingService: Completion timer fired but polling stopped',
            );
            return;
          }

          try {
            // Check for duplicate processing
            if (_lastReloadedSegmentId == pendingSegmentId) {
              debugPrint(
                'StoryPollingService: Skipping segment updates for segment $pendingSegmentId - already synchronized',
              );
            } else {
              // Apply incremental updates from segment response
              debugPrint(
                'StoryPollingService: Applying incremental character updates from segment',
              );
              onSegmentComplete(capturedSegmentStatus);
              _lastReloadedSegmentId = pendingSegmentId;
            }

            // Brief delay then check for next segment
            _scheduleNextPoll(
              const Duration(seconds: 2),
              characterId: characterId,
              onStatusUpdate: onStatusUpdate,
              onCharacterReload: onCharacterReload,
              onSegmentComplete: onSegmentComplete,
              onStoryComplete: onStoryComplete,
              onError: onError,
            );
          } catch (e) {
            debugPrint(
              'StoryPollingService: Error applying segment updates: $e',
            );
            onError?.call(e);

            // Retry with backoff
            _consecutiveErrors++;
            if (_consecutiveErrors >= _maxConsecutiveErrors) {
              debugPrint(
                'StoryPollingService: Too many consecutive errors - scheduling recovery with exponential backoff',
              );
              _scheduleRecovery(
                characterId: characterId,
                onStatusUpdate: onStatusUpdate,
                onCharacterReload: onCharacterReload,
                onSegmentComplete: onSegmentComplete,
                onStoryComplete: onStoryComplete,
                onError: onError,
              );
              return;
            }

            _scheduleNextPoll(
              const Duration(seconds: _errorRetryDelaySeconds),
              characterId: characterId,
              onStatusUpdate: onStatusUpdate,
              onCharacterReload: onCharacterReload,
              onSegmentComplete: onSegmentComplete,
              onStoryComplete: onStoryComplete,
              onError: onError,
            );
          }
        });
      } else {
        // Segment complete (TimeRemaining = 0) - apply incremental updates and check for next segment
        debugPrint(
          'StoryPollingService: Segment complete, applying incremental updates',
        );

        final segmentIdForReload = activeSegmentId;

        if (_lastReloadedSegmentId == segmentIdForReload) {
          debugPrint(
            'StoryPollingService: Skipping segment updates for segment $segmentIdForReload - already synchronized',
          );
        } else {
          try {
            // Apply incremental updates from segment response
            onSegmentComplete(segmentStatus);
            _lastReloadedSegmentId = segmentIdForReload;
          } catch (e) {
            debugPrint(
              'StoryPollingService: Error applying segment updates: $e',
            );
            onError?.call(e);
          }
        }

        // Brief delay then check for next segment
        _scheduleNextPoll(
          const Duration(seconds: 2),
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onCharacterReload: onCharacterReload,
          onSegmentComplete: onSegmentComplete,
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
        debugPrint(
          'StoryPollingService: No active segment - story complete, reloading character',
        );

        // Reload character to get authoritative state (XP, wounds, inventory)
        try {
          final character = await _apiService.getCharacter(
            characterId: characterId,
          );
          onCharacterReload(character);
        } catch (reloadErr) {
          debugPrint(
            'StoryPollingService: Failed to reload character after completion: $reloadErr',
          );
          // Continue to onStoryComplete even if reload fails
          onError?.call(reloadErr);
        }

        stopPolling();
        onStoryComplete();
        return;
      }

      // Notify error handler
      onError?.call(e);

      // Schedule recovery after too many consecutive errors
      if (_consecutiveErrors >= _maxConsecutiveErrors) {
        debugPrint(
          'StoryPollingService: Too many consecutive errors ($_consecutiveErrors) - scheduling recovery with exponential backoff',
        );
        _scheduleRecovery(
          characterId: characterId,
          onStatusUpdate: onStatusUpdate,
          onCharacterReload: onCharacterReload,
          onSegmentComplete: onSegmentComplete,
          onStoryComplete: onStoryComplete,
          onError: onError,
        );
        return;
      }

      // Retry after 30 seconds on error
      debugPrint(
        'StoryPollingService: Retrying in $_errorRetryDelaySeconds seconds (error count: $_consecutiveErrors)',
      );
      _scheduleNextPoll(
        const Duration(seconds: _errorRetryDelaySeconds),
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onCharacterReload: onCharacterReload,
        onSegmentComplete: onSegmentComplete,
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
    required void Function(Map<String, dynamic> segmentUpdates)
    onSegmentComplete,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer(delay, () {
      _pollOnce(
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onCharacterReload: onCharacterReload,
        onSegmentComplete: onSegmentComplete,
        onStoryComplete: onStoryComplete,
        onError: onError,
      );
    });
  }

  /// Schedule recovery attempt after too many consecutive errors.
  ///
  /// Uses exponential backoff (15s, 30s, 60s, 120s) capped at 5 minutes so
  /// transient network hiccups don't impose a minutes-long UI stall while
  /// sustained outages still avoid hammering the API.
  void _scheduleRecovery({
    required String characterId,
    required void Function(Map<String, dynamic> status) onStatusUpdate,
    required void Function(Map<String, dynamic> character) onCharacterReload,
    required void Function(Map<String, dynamic> segmentUpdates)
    onSegmentComplete,
    required void Function() onStoryComplete,
    void Function(Object error)? onError,
  }) {
    // Cancel any existing timers but keep polling state
    _pollingTimer?.cancel();
    _pollingTimer = null;
    _completionTimer?.cancel();
    _completionTimer = null;
    _recoveryTimer?.cancel();

    // Cap the shift amount before shifting. On web builds `<<` is a signed
    // 32-bit operation, so an unbounded shift wraps to a negative value and
    // clamp() collapses the backoff back to the 15s floor -- the opposite of a
    // cap. 15 << 5 = 480 already exceeds the 300s ceiling, so clamping the shift
    // at 5 preserves the intended maximum on every platform.
    final shift = _recoveryAttempt.clamp(0, 5);
    final backoffSeconds = (_recoveryInitialDelaySeconds << shift).clamp(
      _recoveryInitialDelaySeconds,
      _recoveryMaxDelaySeconds,
    );
    _recoveryAttempt++;
    debugPrint(
      'StoryPollingService: Recovery attempt #$_recoveryAttempt in ${backoffSeconds}s',
    );

    _recoveryTimer = Timer(Duration(seconds: backoffSeconds), () {
      _recoveryTimer = null;

      // Check if polling was explicitly stopped
      if (!_isPolling || _characterId != characterId) {
        debugPrint('StoryPollingService: Recovery cancelled - polling stopped');
        return;
      }

      debugPrint(
        'StoryPollingService: Attempting recovery after extended timeout',
      );

      // Reset error counter for fresh start
      _consecutiveErrors = 0;

      // Resume polling immediately
      _pollOnce(
        characterId: characterId,
        onStatusUpdate: onStatusUpdate,
        onCharacterReload: onCharacterReload,
        onSegmentComplete: onSegmentComplete,
        onStoryComplete: onStoryComplete,
        onError: onError,
      );
    });
  }
}
