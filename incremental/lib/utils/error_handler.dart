// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson

import 'package:flutter/foundation.dart';

/// Central error handler for the application
class ErrorHandler {
  /// Maps errors to user-friendly messages and logs the actual error
  static String getUserFriendlyMessage(dynamic error, {String context = ''}) {
    // Log the actual error to console for debugging
    if (kDebugMode) {
      debugPrint('ErrorHandler: Context: $context');
      debugPrint('ErrorHandler: Error type: ${error.runtimeType}');
      debugPrint('ErrorHandler: Error details: $error');
      if (error is Error) {
        debugPrint('ErrorHandler: Stack trace: ${error.stackTrace}');
      }
    }

    // Check if the error already has a user-friendly message
    final errorString = error.toString();

    // If it's already a user-friendly message (doesn't contain technical jargon), return it
    if (_isUserFriendlyMessage(errorString)) {
      return errorString;
    }

    // Map specific error types to user-friendly messages
    if (errorString.toLowerCase().contains('network')) {
      return 'Network error. Please check your connection and try again.';
    }

    if (errorString.toLowerCase().contains('timeout')) {
      return 'Request timed out. Please try again.';
    }

    if (errorString.toLowerCase().contains('permission') || errorString.toLowerCase().contains('forbidden')) {
      return 'You don\'t have permission to perform this action.';
    }

    if (errorString.toLowerCase().contains('not found')) {
      return 'The requested resource was not found.';
    }

    // Return a generic user-friendly message for unknown errors
    return 'An error occurred. Please try again later.';
  }

  /// Checks if a message is already user-friendly
  static bool _isUserFriendlyMessage(String message) {
    // Messages that come from AuthExceptionMapper are already user-friendly
    final userFriendlyPhrases = [
      'Invalid email or password',
      'Please verify your email',
      'The Player Account already exists',
      'Too many attempts',
      'Password must',
      'Invalid verification code',
      'Verification code has expired',
      'Please check your input',
      'already exists',
      'Please try again',
    ];

    for (final phrase in userFriendlyPhrases) {
      if (message.contains(phrase)) {
        return true;
      }
    }

    // Check if message contains technical jargon
    final technicalTerms = [
      'Exception',
      'Error:',
      'Stack trace',
      'null',
      'undefined',
      'instance of',
      'type \'',
      'HTTP',
      '404',
      '500',
      '401',
      '403',
    ];

    for (final term in technicalTerms) {
      if (message.contains(term)) {
        return false;
      }
    }

    // If it's a short, readable message without technical terms, consider it user-friendly
    return message.length < 100 && !message.contains(':');
  }
}
