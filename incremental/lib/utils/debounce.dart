import 'dart:async';
import 'package:flutter/foundation.dart';

/// Debouncer utility for preventing rapid repeated actions
///
/// Ensures a function only executes after a specified delay has passed
/// since the last call. Useful for preventing accidental double-clicks
/// or rapid repeated submissions.
///
/// Example usage:
/// ```dart
/// final debouncer = Debouncer(delay: Duration(milliseconds: 300));
///
/// // In a button onPressed handler:
/// debouncer.run(() {
///   submitForm();
/// });
/// ```
class Debouncer {
  final Duration delay;
  Timer? _timer;
  VoidCallback? _action;

  Debouncer({required this.delay});

  /// Execute action after delay, canceling any pending action
  void run(VoidCallback action) {
    _action = action;
    _timer?.cancel();
    _timer = Timer(delay, () {
      _action?.call();
      _action = null;
    });
  }

  /// Execute action immediately and prevent further calls for delay duration
  /// This is useful for "first call wins" scenarios like button clicks
  void runImmediate(VoidCallback action) {
    if (_timer?.isActive ?? false) {
      debugPrint('Debouncer: Action blocked - still in cooldown');
      return;
    }

    action();

    // Start cooldown timer
    _timer = Timer(delay, () {
      _timer = null;
    });
  }

  /// Check if debouncer is currently in cooldown
  bool get isActive => _timer?.isActive ?? false;

  /// Cancel any pending action
  void cancel() {
    _timer?.cancel();
    _timer = null;
    _action = null;
  }

  /// Dispose of resources
  void dispose() {
    cancel();
  }
}

/// Throttler utility for rate-limiting actions
///
/// Ensures a function can only execute once per time interval,
/// regardless of how many times it's called.
///
/// Example usage:
/// ```dart
/// final throttler = Throttler(duration: Duration(seconds: 1));
///
/// // In a scroll listener:
/// throttler.run(() {
///   updateScrollPosition();
/// });
/// ```
class Throttler {
  final Duration duration;
  Timer? _timer;
  bool _isThrottled = false;

  Throttler({required this.duration});

  /// Execute action immediately if not throttled, otherwise ignore
  void run(VoidCallback action) {
    if (_isThrottled) {
      debugPrint('Throttler: Action blocked - throttled');
      return;
    }

    _isThrottled = true;
    action();

    _timer = Timer(duration, () {
      _isThrottled = false;
      _timer = null;
    });
  }

  /// Check if currently throttled
  bool get isThrottled => _isThrottled;

  /// Cancel throttle
  void cancel() {
    _timer?.cancel();
    _timer = null;
    _isThrottled = false;
  }

  /// Dispose of resources
  void dispose() {
    cancel();
  }
}
