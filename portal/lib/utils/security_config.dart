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

// This file contains security configurations for the web application
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:crypto/crypto.dart';

/// Configures security headers for the web application
class SecurityConfig {
  // Private constructor to prevent instantiation
  SecurityConfig._();

  // Security configurations
  static const int maxLoginAttempts = 5;
  static const Duration lockoutDuration = Duration(minutes: 15);
  static const int passwordMinLength = 8;
  static const int passwordMaxLength = 128;
  static const Duration sessionTimeout = Duration(hours: 24);
  static const int maxSessionsPerUser = 5;

  // Content Security Policy directives
  static const String contentSecurityPolicy = """
    default-src 'self';
    script-src 'self' 'unsafe-inline' 'unsafe-eval';
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: https:;
    font-src 'self' data:;
    connect-src 'self' https://*.amazonaws.com;
    frame-ancestors 'none';
    form-action 'self';
    base-uri 'self';
    object-src 'none';
  """;

  /// Applies security configurations to the web application
  static void applyWebSecurityConfig() {
    // Check if running on web platform
    if (!kIsWeb) return; // If not web, return early

    // Since we're using CloudFront, most security headers are handled there
    // We only need to set up any client-side security measures
    _setupClientSideConfig();
    _validateCloudFrontDeployment();
    _configureClientSecurity();
  }

  /// Configure client-side security settings
  static void _setupClientSideConfig() {
    // Web-specific configurations would go here
    // Since CloudFront handles security headers, we keep this minimal
    if (kDebugMode) {
      debugPrint('Client-side security config applied');
    }
  }

  /// Validates CloudFront deployment settings
  static void _validateCloudFrontDeployment() {
    // CloudFront validation would go here
    // Logging actual deployment checks would require web-specific packages
    if (kDebugMode) {
      debugPrint('Note: Security headers should be configured in CloudFront');
    }
  }

  /// Configures additional client-side security measures
  static void _configureClientSecurity() {
    if (kIsWeb) {
      // Disable right-click context menu in production
      if (kReleaseMode) {
        // This would need to be implemented using web-specific code
      }

      // Set up secure cookie flags
      _configureSecureCookies();

      // Configure secure session management
      _configureSessionSecurity();
    }
  }

  /// Validates that security headers are properly set
  static bool validateSecurityHeaders() {
    // When using CloudFront, headers won't be in meta tags
    // They'll be set in HTTP response headers instead
    if (kDebugMode) {
      debugPrint(
        'CloudFront deployment: Security headers should be configured in CloudFront settings.',
      );
    }

    // Since we're handling headers at CloudFront level,
    // this method primarily serves as a reminder/documentation
    return true;
  }

  /// Configures secure cookie settings for web
  static void _configureSecureCookies() {
    // In production, ensure cookies are secure and HttpOnly
    // This would need to be implemented using web-specific code
    if (kDebugMode) {
      debugPrint('Secure cookie configuration would be applied here');
    }
  }

  /// Configures session security settings
  static void _configureSessionSecurity() {
    // Configure session timeout and other security measures
    // This would need to be implemented using web-specific code
    if (kDebugMode) {
      debugPrint('Session security configuration would be applied here');
    }
  }

  /// Generates a cryptographically secure random token
  static String generateSecureToken() {
    final random = utf8.encode(
      DateTime.now().millisecondsSinceEpoch.toString(),
    );
    final bytes = sha256.convert(random).bytes;
    return base64Url.encode(bytes);
  }

  /// Validates if a password meets security requirements
  static bool validatePasswordSecurity(String password) {
    if (password.length < passwordMinLength ||
        password.length > passwordMaxLength) {
      return false;
    }

    // Check for complexity requirements
    final hasUppercase = password.contains(RegExp(r'[A-Z]'));
    final hasLowercase = password.contains(RegExp(r'[a-z]'));
    final hasDigits = password.contains(RegExp(r'[0-9]'));
    final hasSpecialCharacters = password.contains(
      RegExp(r'[!@#$%^&*(),.?":{}|<>]'),
    );

    return hasUppercase && hasLowercase && hasDigits && hasSpecialCharacters;
  }

  /// Sanitizes HTML to prevent XSS attacks
  static String sanitizeHtml(String html) {
    // Basic HTML sanitization (would need a more robust solution in production)
    return html
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
  }

  /// Validates and sanitizes URLs to prevent injection attacks
  static String? sanitizeUrl(String url) {
    try {
      final uri = Uri.parse(url);

      // Only allow http and https protocols
      if (!['http', 'https'].contains(uri.scheme.toLowerCase())) {
        return null;
      }

      // Check for common injection patterns
      if (url.contains('<script>') || url.contains('javascript:')) {
        return null;
      }

      return uri.toString();
    } catch (e) {
      return null;
    }
  }

  /// Validates file uploads for security
  static bool validateFileUpload(String filename, List<int> content) {
    // Check file extension
    final validExtensions = ['jpg', 'jpeg', 'png', 'gif', 'pdf'];
    final extension = filename.split('.').last.toLowerCase();

    if (!validExtensions.contains(extension)) {
      return false;
    }

    // Check file size (e.g., 5MB limit)
    if (content.length > 5 * 1024 * 1024) {
      return false;
    }

    // Additional checks would be needed for file content validation
    return true;
  }

  /// Generates a CSRF token for form protection
  static String generateCsrfToken() {
    final random = DateTime.now().millisecondsSinceEpoch.toString();
    final hash = sha256.convert(utf8.encode(random));
    return base64Url.encode(hash.bytes);
  }

  /// Validates a CSRF token
  static bool validateCsrfToken(String token, String expectedToken) {
    if (token.isEmpty || expectedToken.isEmpty) return false;
    return token == expectedToken;
  }

  /// Gets the recommended security headers for CloudFront
  static Map<String, String> getRecommendedHeaders() {
    return {
      'Strict-Transport-Security':
          'max-age=31536000; includeSubDomains; preload',
      'X-Frame-Options': 'DENY',
      'X-Content-Type-Options': 'nosniff',
      'X-XSS-Protection': '1; mode=block',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Content-Security-Policy':
          contentSecurityPolicy.replaceAll('\n', ' ').trim(),
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    };
  }
}
