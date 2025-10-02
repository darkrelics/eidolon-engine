import 'dart:async';
import 'package:flutter/foundation.dart';

/// Rate limiter to prevent excessive API calls
class RateLimiter {
  static const Duration humanDrivenInterval = Duration(seconds: 15);
  static const Duration automatedInterval = Duration(seconds: 60);
  static const Duration cleanupInterval = Duration(minutes: 5);
  static const Duration maxAge = Duration(hours: 1);

  final Map<String, DateTime> _lastCallTimes = {};
  final Map<String, Timer?> _pendingTimers = {};
  final Map<String, void Function(String message, Duration remaining)?>
  _pendingCancelCallbacks = {};
  Timer? _cleanupTimer;

  RateLimiter() {
    _startPeriodicCleanup();
  }

  /// Start periodic cleanup to prevent memory leaks
  void _startPeriodicCleanup() {
    _cleanupTimer = Timer.periodic(
      cleanupInterval,
      (_) => _cleanupOldEntries(),
    );
  }

  /// Remove old entries from _lastCallTimes to prevent memory leaks
  void _cleanupOldEntries() {
    final cutoff = DateTime.now().subtract(maxAge);
    _lastCallTimes.removeWhere((key, time) => time.isBefore(cutoff));

    debugPrint(
      'RateLimiter: Cleaned up old entries, ${_lastCallTimes.length} keys remaining',
    );
  }

  /// Check if enough time has passed for a human-driven action
  bool canCallHumanDriven(String key) {
    final lastCall = _lastCallTimes[key];
    if (lastCall == null) return true;

    final elapsed = DateTime.now().difference(lastCall);
    return elapsed >= humanDrivenInterval;
  }

  /// Check if enough time has passed for an automated action
  bool canCallAutomated(String key) {
    final lastCall = _lastCallTimes[key];
    if (lastCall == null) return true;

    final elapsed = DateTime.now().difference(lastCall);
    return elapsed >= automatedInterval;
  }

  /// Execute a human-driven action with rate limiting
  Future<T> executeHumanDriven<T>(
    String key,
    Future<T> Function() action, {
    bool throwOnRateLimit = false,
  }) async {
    final lastCall = _lastCallTimes[key];
    final now = DateTime.now();

    if (lastCall != null) {
      final elapsed = now.difference(lastCall);
      final remaining = humanDrivenInterval - elapsed;

      if (remaining > Duration.zero) {
        debugPrint(
          'RateLimiter: Action $key rate limited, ${remaining.inSeconds}s remaining',
        );

        if (throwOnRateLimit) {
          throw RateLimitException(
            'Please wait ${remaining.inSeconds} seconds before trying again',
            remaining: remaining,
          );
        }

        // Queue the action to run when the rate limit expires
        return _queueAction(key, action, remaining);
      }
    }

    _lastCallTimes[key] = now;
    return await action();
  }

  /// Execute an automated action with rate limiting
  Future<T> executeAutomated<T>(String key, Future<T> Function() action) async {
    final lastCall = _lastCallTimes[key];
    final now = DateTime.now();

    if (lastCall != null) {
      final elapsed = now.difference(lastCall);
      final remaining = automatedInterval - elapsed;

      if (remaining > Duration.zero) {
        debugPrint(
          'RateLimiter: Automated action $key delayed by ${remaining.inSeconds}s',
        );
        // Always queue automated actions instead of throwing
        return _queueAction(key, action, remaining);
      }
    }

    _lastCallTimes[key] = now;
    return await action();
  }

  /// Queue an action to run after the rate limit expires
  Future<T> _queueAction<T>(
    String key,
    Future<T> Function() action,
    Duration delay,
  ) async {
    // Cancel any existing queued action for this key
    _pendingTimers[key]?.cancel();
    _pendingTimers.remove(key);

    final previousCancel = _pendingCancelCallbacks.remove(key);
    previousCancel?.call('Cancelled by new request', Duration.zero);

    final completer = Completer<T>();
    _pendingCancelCallbacks[key] = (message, remaining) {
      if (!completer.isCompleted) {
        completer.completeError(
          RateLimitException(message, remaining: remaining),
        );
      }
    };

    _pendingTimers[key] = Timer(delay, () async {
      try {
        _lastCallTimes[key] = DateTime.now();
        final result = await action();
        if (!completer.isCompleted) {
          completer.complete(result);
        }
      } catch (e) {
        if (!completer.isCompleted) {
          completer.completeError(e);
        }
      } finally {
        _pendingTimers.remove(key);
        _pendingCancelCallbacks.remove(key);
      }
    });

    return completer.future;
  }

  /// Record that an API call was made (for external tracking)
  void recordCall(String key) {
    _lastCallTimes[key] = DateTime.now();
  }

  /// Get remaining time until next allowed call
  Duration getRemainingTime(String key, {bool isAutomated = false}) {
    final lastCall = _lastCallTimes[key];
    if (lastCall == null) return Duration.zero;

    final interval = isAutomated ? automatedInterval : humanDrivenInterval;
    final elapsed = DateTime.now().difference(lastCall);
    final remaining = interval - elapsed;

    return remaining > Duration.zero ? remaining : Duration.zero;
  }

  /// Clear rate limit for a specific key
  void clearLimit(String key) {
    _lastCallTimes.remove(key);
    _pendingTimers[key]?.cancel();
    _pendingTimers.remove(key);
    final cancel = _pendingCancelCallbacks.remove(key);
    cancel?.call('Cleared', Duration.zero);
  }

  /// Clear all rate limits
  void clearAll() {
    _lastCallTimes.clear();
    for (final timer in _pendingTimers.values) {
      timer?.cancel();
    }
    _pendingTimers.clear();
    for (final cancel in _pendingCancelCallbacks.values) {
      cancel?.call('Cleared', Duration.zero);
    }
    _pendingCancelCallbacks.clear();
  }

  /// Dispose of resources
  void dispose() {
    _cleanupTimer?.cancel();
    _cleanupTimer = null;
    clearAll();
  }
}

/// Exception thrown when rate limit is exceeded
class RateLimitException implements Exception {
  final String message;
  final Duration remaining;

  RateLimitException(this.message, {required this.remaining});

  @override
  String toString() => message;
}

/// Singleton instance for global rate limiting
class GlobalRateLimiter {
  static final GlobalRateLimiter _instance = GlobalRateLimiter._internal();
  factory GlobalRateLimiter() => _instance;
  GlobalRateLimiter._internal();

  final RateLimiter _limiter = RateLimiter();

  /// Rate limit keys for different API endpoints
  /// Each endpoint gets its own rate limit bucket
  static const String getCharacter = 'api_get_character';
  static const String startStory = 'api_start_story';
  static const String submitDecision = 'api_submit_decision';
  static const String submitOutcome = 'api_submit_outcome';
  static const String abandonStory = 'api_abandon_story';
  static const String getSegmentStatus = 'api_get_segment_status';
  static const String getAvailableStories = 'api_get_available_stories';

  RateLimiter get limiter => _limiter;

  void dispose() {
    _limiter.dispose();
  }
}
