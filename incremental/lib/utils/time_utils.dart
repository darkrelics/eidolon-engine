/// Time utilities for consistent ISO 8601 timestamp handling.
/// 
/// Provides functions for generating and parsing ISO 8601 timestamps,
/// ensuring consistency between client and server.

class TimeUtils {
  /// Get current UTC time as ISO 8601 string.
  static String nowIso() {
    return DateTime.now().toUtc().toIso8601String();
  }

  /// Get future UTC time as ISO 8601 string.
  static String futureIso(int seconds) {
    final future = DateTime.now().toUtc().add(Duration(seconds: seconds));
    return future.toIso8601String();
  }

  /// Get past UTC time as ISO 8601 string.
  static String pastIso(int seconds) {
    final past = DateTime.now().toUtc().subtract(Duration(seconds: seconds));
    return past.toIso8601String();
  }

  /// Parse ISO 8601 string to DateTime object.
  static DateTime parseIso(String isoString) {
    return DateTime.parse(isoString);
  }

  /// Convert ISO 8601 string to Unix timestamp (seconds).
  static int toUnix(String isoString) {
    final dt = parseIso(isoString);
    return dt.millisecondsSinceEpoch ~/ 1000;
  }

  /// Convert Unix timestamp to ISO 8601 string.
  static String fromUnix(int unixTimestamp) {
    final dt = DateTime.fromMillisecondsSinceEpoch(unixTimestamp * 1000, isUtc: true);
    return dt.toIso8601String();
  }

  /// Check if ISO 8601 time is in the past.
  static bool isPast(String isoString) {
    final dt = parseIso(isoString);
    return dt.isBefore(DateTime.now().toUtc());
  }

  /// Check if ISO 8601 time is in the future.
  static bool isFuture(String isoString) {
    final dt = parseIso(isoString);
    return dt.isAfter(DateTime.now().toUtc());
  }

  /// Calculate seconds until a future ISO 8601 time.
  static int secondsUntil(String isoString) {
    final dt = parseIso(isoString);
    final now = DateTime.now().toUtc();
    final diff = dt.difference(now);
    return diff.inSeconds > 0 ? diff.inSeconds : 0;
  }

  /// Calculate seconds since a past ISO 8601 time.
  static int secondsSince(String isoString) {
    final dt = parseIso(isoString);
    final now = DateTime.now().toUtc();
    final diff = now.difference(dt);
    return diff.inSeconds > 0 ? diff.inSeconds : 0;
  }

  /// Calculate duration in seconds between two ISO 8601 times.
  static int durationBetween(String startIso, String endIso) {
    final startDt = parseIso(startIso);
    final endDt = parseIso(endIso);
    final diff = endDt.difference(startDt);
    return diff.inSeconds;
  }

  /// Format ISO 8601 string for display (e.g., "5 minutes ago").
  static String formatRelative(String isoString) {
    final dt = parseIso(isoString);
    final now = DateTime.now().toUtc();
    final diff = now.difference(dt);

    if (diff.inSeconds < 60) {
      return '${diff.inSeconds} seconds ago';
    } else if (diff.inMinutes < 60) {
      return '${diff.inMinutes} minutes ago';
    } else if (diff.inHours < 24) {
      return '${diff.inHours} hours ago';
    } else {
      return '${diff.inDays} days ago';
    }
  }

  /// Format duration in seconds to human-readable string.
  static String formatDuration(int seconds) {
    if (seconds < 60) {
      return '$seconds seconds';
    } else if (seconds < 3600) {
      final minutes = seconds ~/ 60;
      final remainingSeconds = seconds % 60;
      if (remainingSeconds == 0) {
        return '$minutes minutes';
      }
      return '$minutes:${remainingSeconds.toString().padLeft(2, '0')}';
    } else {
      final hours = seconds ~/ 3600;
      final minutes = (seconds % 3600) ~/ 60;
      return '$hours:${minutes.toString().padLeft(2, '0')}';
    }
  }
}