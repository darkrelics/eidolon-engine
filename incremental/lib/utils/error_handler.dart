// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
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

    if (error is CognitoClientException) {
      final message = error.message;
      if (message != null && message.trim().isNotEmpty) {
        return message;
      }
    }

    // Check if the error already has a user-friendly message
    final errorString = error.toString();
    final normalizedError = errorString.toLowerCase();

    // If it's already a user-friendly message (doesn't contain technical jargon), return it
    if (_isUserFriendlyMessage(errorString)) {
      return errorString;
    }

    // Map specific error types to user-friendly messages
    if (normalizedError.contains('usernameexists') ||
        normalizedError.contains('username exists') ||
        normalizedError.contains('user already exists') ||
        normalizedError.contains('email already exists') ||
        normalizedError.contains('already registered')) {
      return 'The Player Account already exists.';
    }

    if (normalizedError.contains('network')) {
      return 'Network error. Please check your connection and try again.';
    }

    if (normalizedError.contains('timeout')) {
      return 'Request timed out. Please try again.';
    }

    if (normalizedError.contains('permission') ||
        normalizedError.contains('forbidden')) {
      return 'You don\'t have permission to perform this action.';
    }

    if (normalizedError.contains('not found')) {
      return 'The requested resource was not found.';
    }

    // Character-specific errors
    if (normalizedError.contains('player account not found')) {
      return 'We could not find your player data. Please sign out and back in.';
    }

    if (normalizedError.contains('character name is already taken') ||
        normalizedError.contains('character name is not available')) {
      return 'That character name is not available. Please choose another.';
    }

    if (normalizedError.contains('character limit reached')) {
      return 'You have reached the maximum number of characters.';
    }

    if (normalizedError.contains('access denied')) {
      return 'You do not have permission to perform this action.';
    }

    // Story-specific errors
    if (normalizedError.contains('story not available')) {
      return 'This story is not available. It may be on cooldown or require certain prerequisites.';
    }

    if (normalizedError.contains('already in a story')) {
      return 'Your character is already in an active story. Complete or abandon it first.';
    }

    if (normalizedError.contains('segment not found')) {
      return 'Unable to find the current segment. Please refresh.';
    }

    if (normalizedError.contains('decision already')) {
      return 'You have already made a decision for this segment.';
    }

    if (normalizedError.contains('not authenticated')) {
      return 'Your session has expired. Please log in again.';
    }

    if (normalizedError.contains('character is dead')) {
      return 'Your character has died. You must resurrect before continuing.';
    }

    if (normalizedError.contains('overloaded')) {
      return 'The server is busy. Please wait a moment and try again.';
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
