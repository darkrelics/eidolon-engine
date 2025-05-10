// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
