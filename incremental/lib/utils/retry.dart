import 'dart:async';
import 'dart:math' as math;

/// Retry a function with exponential backoff
/// Retries up to 3 times with delays of 1s, 2s, 4s
Future<T> retryWithBackoff<T>(Future<T> Function() operation) async {
  for (int i = 0; i < 3; i++) {
    try {
      return await operation();
    } catch (e) {
      if (i == 2) rethrow; // Last attempt, propagate error
      final delay = math.pow(2, i).toInt(); // 1, 2, 4 seconds
      await Future.delayed(Duration(seconds: delay));
    }
  }
  throw Exception('Unreachable');
}
