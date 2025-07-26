// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:flutter/foundation.dart';

/// Global error handler for the application
class GlobalErrorHandler {
  // Prevent instantiation
  GlobalErrorHandler._();

  /// Initialize global error handlers for the application
  static void initialize() {
    // Set up error reporting
    FlutterError.onError = (FlutterErrorDetails details) {
      if (kDebugMode) {
        FlutterError.presentError(details);
      } else {
        // In production, log to a service
        _logError('Flutter error', details.exception, details.stack);
      }
    };

    // Set up error zone
    PlatformDispatcher.instance.onError = (error, stack) {
      _logError('Platform error', error, stack);
      return true; // Prevents the error from propagating
    };
  }

  /// Log an error safely
  static void _logError(String context, Object error, StackTrace? stackTrace) {
    try {
      debugPrint('$context: $error');
      if (stackTrace != null) {
        debugPrint(stackTrace.toString());
      }

      // In production, this would send to a logging service
      if (!kDebugMode) {
        // Send to error reporting service
      }
    } catch (e) {
      // Even logging failed - last resort
      debugPrint('Error logging failed: $e');
    }
  }
}
