// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the “License”);
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an “AS IS” BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Configuration class for storing Cognito settings
class AppConfig {
  // Use the fromEnvironment constructor with explicit default values
  static const String userPoolId = String.fromEnvironment(
    'USER_POOL_ID',
    defaultValue: '',
  );

  static const String clientId = String.fromEnvironment(
    'CLIENT_ID',
    defaultValue: '',
  );

  // Development fallbacks - DO NOT use in production
  static String get _devUserPoolId => kDebugMode ? 'dev-user-pool-id' : '';
  static String get _devClientId => kDebugMode ? 'dev-client-id' : '';

  // Getters with fallbacks for easier runtime access
  static String get userPoolIdWithFallback => 
      userPoolId.isNotEmpty ? userPoolId : _devUserPoolId;
  
  static String get clientIdWithFallback => 
      clientId.isNotEmpty ? clientId : _devClientId;

  static void validateConfiguration() {
    final effectiveUserPoolId = userPoolIdWithFallback;
    final effectiveClientId = clientIdWithFallback;

    if (effectiveUserPoolId.isEmpty || effectiveClientId.isEmpty) {
      throw ConfigurationException(
        'Missing required Cognito configuration. Please set USER_POOL_ID and CLIENT_ID environment variables.',
      );
    }

    if (kReleaseMode && (userPoolId.isEmpty || clientId.isEmpty)) {
      throw ConfigurationException(
        'Production build is missing required environment variables. '
        'USER_POOL_ID and CLIENT_ID must be set at build time.',
      );
    }
  }
}

/// Custom exception for configuration errors
class ConfigurationException implements Exception {
  final String message;

  ConfigurationException(this.message);

  @override
  String toString() => message;
}

/// Custom exception for sign-out errors
class AuthSignOutException implements Exception {
  final String message;

  AuthSignOutException(this.message);

  @override
  String toString() => message;
}

/// Maps Cognito exceptions to user-friendly messages
class AuthExceptionMapper {
  static String mapToUserFriendlyMessage(dynamic error) {
    if (error is CognitoClientException) {
      switch (error.code) {
        case 'UserNotFoundException':
        case 'NotAuthorizedException':
          return 'Invalid email or password';
        case 'UserNotConfirmedException':
          return 'Please verify your email before signing in';
        case 'InvalidParameterException':
          return 'Please check your input and try again';
        case 'UsernameExistsException':
          return 'An account with this email already exists';
        case 'LimitExceededException':
          return 'Too many attempts. Please try again later';
        case 'InvalidPasswordException':
          return 'Password must meet complexity requirements';
        case 'CodeMismatchException':
          return 'Invalid verification code. Please try again';
        case 'ExpiredCodeException':
          return 'Verification code has expired. Please request a new one';
        default:
          return 'An error occurred. Please try again';
      }
    }
    return 'An unexpected error occurred. Please try again';
  }
}

/// Service for handling authentication with AWS Cognito
class AuthService {
  late final CognitoUserPool userPool;
  CognitoUser? _currentUser;
  CognitoUserSession? _session;
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  // Token storage keys
  static const String _accessTokenKey = 'access_token';
  static const String _idTokenKey = 'id_token';
  static const String _refreshTokenKey = 'refresh_token';
  static const String _userEmailKey = 'user_email';

  AuthService() {
    _initializeCognito();
  }

  /// Initializes Cognito configuration
  void _initializeCognito() {
    try {
      AppConfig.validateConfiguration();

      userPool = CognitoUserPool(
        AppConfig.userPoolIdWithFallback, 
        AppConfig.clientIdWithFallback,
      );

      // Attempt to restore previous session
      _restoreSession();
    } catch (e) {
      _logError('Error initializing Cognito', e);
      rethrow;
    }
  }

  /// Signs up a new user
  Future<CognitoUserPoolData> signUp(String email, String password) async {
    try {
      if (!_validateEmail(email)) {
        throw CognitoClientException('Invalid email format');
      }

      if (!_validatePassword(password)) {
        throw CognitoClientException(
          'Password must be at least 8 characters with uppercase, lowercase, number and special character',
        );
      }

      final signUpResult = await userPool.signUp(
        email,
        password,
        userAttributes: [AttributeArg(name: 'email', value: email)],
      );

      return signUpResult;
    } on CognitoClientException catch (e) {
      throw CognitoClientException(
        AuthExceptionMapper.mapToUserFriendlyMessage(e),
      );
    } catch (e) {
      _logError('Unexpected error during signup', e);
      rethrow;
    }
  }

  /// Confirms user registration with verification code
  Future<bool> confirmRegistration(String email, String code) async {
    try {
      if (code.isEmpty) {
        throw CognitoClientException('Verification code cannot be empty');
      }

      final user = CognitoUser(email, userPool);
      return await user.confirmRegistration(code);
    } on CognitoClientException catch (e) {
      throw CognitoClientException(
        AuthExceptionMapper.mapToUserFriendlyMessage(e),
      );
    } catch (e) {
      _logError('Unexpected error during confirmation', e);
      rethrow;
    }
  }

  /// Signs in a user
  Future<CognitoUser> signIn(String email, String password) async {
    try {
      if (!_validateEmail(email)) {
        throw CognitoClientException('Invalid email format');
      }

      final user = CognitoUser(email, userPool);
      final authDetails = AuthenticationDetails(
        username: email,
        password: password,
      );

      _session = await user.authenticateUser(authDetails);
      _currentUser = user;

      // Store tokens securely
      await _persistTokens(_session!, email);

      return user;
    } on CognitoClientException catch (e) {
      throw CognitoClientException(
        AuthExceptionMapper.mapToUserFriendlyMessage(e),
      );
    } catch (e) {
      _logError('Unexpected error during signin', e);
      rethrow;
    }
  }

  /// Signs out the current user
  Future<void> signOut() async {
    try {
      if (_currentUser != null) {
        try {
          await _currentUser?.signOut();
        } catch (e) {
          // Log but don't throw for server-side signout issues
          _logError('Server sign-out error', e);
        } finally {
          // Always clear local state regardless of server communication errors
          _currentUser = null;
          _session = null;
          final cleared = await _clearTokens();
          if (!cleared) {
            _logError('Client sign-out incomplete', 'Failed to clear all tokens');
          }
        }
      }
    } catch (e) {
      _logError('SignOut error', e);
      // Don't rethrow, we want signout to always succeed from the user's perspective
      // Instead, return failure status for internal error handling
      throw AuthSignOutException('Sign-out failed. Please try again.');
    }
  }

  /// Checks if user is authenticated
  Future<bool> isAuthenticated() async {
    try {
      // Check for existing tokens and refresh if necessary
      if (_currentUser == null || _session == null) {
        final restored = await _restoreSession();
        if (!restored) return false;
      }

      // Check if session is still valid
      if (_session == null) return false;

      // If session has expired, try to refresh
      if (!_session!.isValid()) {
        return await _refreshSession();
      }

      return true;
    } catch (e) {
      _logError('Authentication check error', e);
      return false;
    }
  }

  /// Resends the confirmation code
  Future<void> resendConfirmationCode(String email) async {
    try {
      final user = CognitoUser(email, userPool);
      await user.resendConfirmationCode();
    } on CognitoClientException catch (e) {
      throw CognitoClientException(
        AuthExceptionMapper.mapToUserFriendlyMessage(e),
      );
    } catch (e) {
      _logError('Resend confirmation code error', e);
      rethrow;
    }
  }

  /// Persists authentication tokens securely
  Future<bool> _persistTokens(CognitoUserSession session, String email) async {
    try {
      await _secureStorage.write(
        key: _accessTokenKey,
        value: session.getAccessToken().getJwtToken(),
      );
      await _secureStorage.write(
        key: _idTokenKey,
        value: session.getIdToken().getJwtToken(),
      );
      await _secureStorage.write(
        key: _refreshTokenKey,
        value: session.getRefreshToken()?.getToken(),
      );
      await _secureStorage.write(key: _userEmailKey, value: email);
      return true;
    } catch (e) {
      _logError('Error persisting tokens', e);
      // Continue without throwing - persistence failure shouldn't block auth
      // But we'll return false to indicate failure
      return false;
    }
  }

  /// Clears stored tokens
  Future<bool> _clearTokens() async {
    try {
      await _secureStorage.delete(key: _accessTokenKey);
      await _secureStorage.delete(key: _idTokenKey);
      await _secureStorage.delete(key: _refreshTokenKey);
      await _secureStorage.delete(key: _userEmailKey);
      return true;
    } catch (e) {
      _logError('Error clearing tokens', e);
      // Continue without throwing - clearing failure shouldn't block signout
      // But return a status for monitoring purposes
      return false;
    }
  }

  /// Attempts to restore previous session from stored tokens
  Future<bool> _restoreSession() async {
    try {
      final email = await _secureStorage.read(key: _userEmailKey);
      final refreshToken = await _secureStorage.read(key: _refreshTokenKey);

      if (email == null || refreshToken == null) {
        _logError('Missing stored credentials', 'Email or refresh token not found');
        return false;
      }

      _currentUser = CognitoUser(email, userPool);
      final cognitoRefreshToken = CognitoRefreshToken(refreshToken);

      try {
        _session = await _currentUser!.refreshSession(cognitoRefreshToken);
      } on CognitoClientException catch (e) {
        // Handle specific Cognito errors
        _logError('Cognito refresh session error', '${e.code}: ${e.message}');
        // Clear invalid tokens to prevent future restore attempts with bad tokens
        await _clearTokens();
        return false;
      }

      // Update stored tokens with new ones
      final tokensPersisted = await _persistTokens(_session!, email);
      if (!tokensPersisted) {
        _logError('Token persistence failed', 'Unable to save refreshed tokens');
        // Continue anyway as the session is valid in memory
      }

      return true;
    } catch (e) {
      _logError('Error restoring session', e);
      // Clear any incomplete data that might have been stored
      await _clearTokens();
      return false;
    }
  }

  /// Refreshes the current session
  Future<bool> _refreshSession() async {
    try {
      if (_currentUser == null || _session == null) return false;

      final refreshToken = _session!.getRefreshToken();
      if (refreshToken == null) return false;

      _session = await _currentUser!.refreshSession(refreshToken);

      // Update stored tokens
      final email = await _secureStorage.read(key: _userEmailKey);
      if (email != null) {
        await _persistTokens(_session!, email);
      }

      return true;
    } catch (e) {
      _logError('Error refreshing session', e);
      return false;
    }
  }

  /// Validates email format
  bool _validateEmail(String email) {
    return RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email);
  }

  /// Validates password complexity
  bool _validatePassword(String password) {
    if (password.length < 8) return false;

    // Check for at least one uppercase, one lowercase, one number and one special character
    return RegExp(
      r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]',
    ).hasMatch(password);
  }

  /// Logs errors (can be replaced with proper logging framework)
  void _logError(String message, dynamic error) {
    // Log in both debug and release modes, but with different handling
    if (kDebugMode) {
      // In debug mode, print to console
      print('$message: $error');
    } else {
      // In production mode, we should use a proper logging service
      // This would ideally send errors to a monitoring service
      // For now, we'll just guard with a mode check, but this should be replaced
      // with actual error reporting in production
      
      // Potential implementation:
      // FirebaseCrashlytics.instance.recordError(error, StackTrace.current, reason: message);
      // or
      // Sentry.captureException(error, stackTrace: StackTrace.current, hint: message);
      
      // As a minimal fallback, we'll still log to console in release mode,
      // but with less detail to avoid leaking sensitive info
      print('Authentication error: ${message.split(':').first}');
    }
    
    // Always log security relevant errors to a secure audit log in production
    final bool isSecurityRelevant = 
        message.contains('token') || 
        message.contains('auth') || 
        message.contains('session');
        
    if (isSecurityRelevant && !kDebugMode) {
      // Implement secure audit logging here
      // This should go to a separate, tamper-proof security log
    }
  }

  /// Gets the current user
  CognitoUser? get currentUser => _currentUser;

  /// Gets the current session
  CognitoUserSession? get session => _session;
}
