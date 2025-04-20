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

import 'package:flutter/services.dart';

/// Utility class for sanitizing user input to prevent XSS and other attacks
class InputSanitizer {
  // Private constructor to prevent instantiation
  InputSanitizer._();

  // Characters that could potentially be used for XSS attacks
  static const String _xssCharacters = '<>/"\'`&';

  // Characters that could potentially be used in path traversal attacks
  static const String _pathTraversalChars = '../|\\:*?"<>|';

  /// Creates a TextInputFormatter that blocks XSS characters
  static TextInputFormatter noXSSChars() {
    return FilteringTextInputFormatter.deny(RegExp('[$_xssCharacters]'));
  }

  /// Creates a TextInputFormatter that blocks path traversal characters
  static TextInputFormatter noPathTraversalChars() {
    return FilteringTextInputFormatter.deny(RegExp('[$_pathTraversalChars]'));
  }

  /// Sanitizes text for display in SnackBars and other UI elements
  static String sanitizeDisplayText(String text) {
    // HTML encode special characters
    return text
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;')
        .replaceAll('/', '&#47;');
  }

  /// Sanitizes file paths to prevent directory traversal
  static String sanitizeFilePath(String path) {
    // Remove any parent directory traversal
    String sanitized = path.replaceAll('../', '').replaceAll('..\\', '');

    // Remove any absolute paths
    sanitized = sanitized.replaceAll(RegExp(r'^[/\\]'), '');

    // Remove any path traversal characters
    sanitized = sanitized.replaceAll(RegExp('[$_pathTraversalChars]'), '');

    return sanitized;
  }

  /// Validates and sanitizes asset paths
  static String? validateAssetPath(String path) {
    // Check if path is empty
    if (path.isEmpty) return null;

    // Check for path traversal attempts
    if (path.contains('..') || path.contains('~')) {
      return null;
    }

    // Ensure path starts with assets/
    if (!path.startsWith('assets/')) {
      return 'assets/$path';
    }

    // Sanitize the path
    return sanitizeFilePath(path);
  }

  /// Sanitizes URLs to prevent javascript: and other malicious protocols
  static String? sanitizeUrl(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null) return null;

    // Allow only http and https protocols
    if (!uri.scheme.toLowerCase().startsWith('http')) {
      return null;
    }

    return url;
  }

  /// Validates email addresses without allowing malicious content
  static bool validateEmail(String email) {
    // Basic structure check
    if (!RegExp(r'^[\w\-\.]+@([\w\-]+\.)+[\w\-]{2,4}$').hasMatch(email)) {
      return false;
    }

    // No XSS characters allowed
    if (RegExp('[$_xssCharacters]').hasMatch(email)) {
      return false;
    }

    return true;
  }

  /// Removes all potentially dangerous characters from a string
  static String stripDangerousChars(String input) {
    return input.replaceAll(RegExp('[$_xssCharacters]'), '');
  }

  /// Checks if a string contains potentially dangerous characters
  static bool containsDangerousChars(String input) {
    return RegExp('[$_xssCharacters]').hasMatch(input);
  }

  /// Sanitizes user-generated content for safe display
  static String sanitizeUserContent(String content) {
    // First, sanitize for HTML display
    String sanitized = sanitizeDisplayText(content);

    // Then strip any remaining potentially dangerous patterns
    sanitized = sanitized.replaceAll(
      RegExp(r'javascript:', caseSensitive: false),
      '',
    );
    sanitized = sanitized.replaceAll(
      RegExp(r'data:', caseSensitive: false),
      '',
    );
    sanitized = sanitized.replaceAll(
      RegExp(r'vbscript:', caseSensitive: false),
      '',
    );

    return sanitized;
  }

  /// Escapes special characters for regular expressions
  static String escapeRegExp(String string) {
    return string.replaceAllMapped(
      RegExp(r'[.*+?^${}()|[\]\\]'),
      (Match match) => '\\${match.group(0)}',
    );
  }
}
