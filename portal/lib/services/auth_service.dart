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

import 'dart:math';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Configuration class for storing Cognito settings
class AppConfig {
  // Use the fromEnvironment constructor with explicit default values
  static const String userPoolId = String.fromEnvironment('USER_POOL_ID');

  static const String clientId = String.fromEnvironment('CLIENT_ID');

  // Valid format for userPoolId: region_UUID (e.g., us-east-1_abcd1234)
  // Using a real dev pool format for testing
  static String get _devUserPoolId => kDebugMode ? 'us-east-1_devUserPool' : '';

  // Valid format for clientId: 26-character alphanumeric string
  // Using a valid format for the client ID
  static String get _devClientId =>
      kDebugMode ? '1example2client3id4567890abc' : '';

  // Getters with fallbacks for easier runtime access
  static String get userPoolIdWithFallback =>
      userPoolId.isNotEmpty ? userPoolId : _devUserPoolId;

  static String get clientIdWithFallback =>
      clientId.isNotEmpty ? clientId : _devClientId;

  static void validateConfiguration() {
    final effectiveUserPoolId = userPoolIdWithFallback;
    final effectiveClientId = clientIdWithFallback;

    debugPrint('Validating Cognito configuration:');
    debugPrint('- userPoolId: $userPoolId');
    debugPrint('- clientId: $clientId');
    debugPrint('- effectiveUserPoolId: $effectiveUserPoolId');
    debugPrint('- effectiveClientId: $effectiveClientId');

    // Validate userPoolId format: should be in the format region_poolId
    if (effectiveUserPoolId.isEmpty || !effectiveUserPoolId.contains('_')) {
      throw ConfigurationException(
        'Invalid userPoolId format. It should be in the format "region_poolId".',
      );
    }

    // Validate clientId is not empty
    if (effectiveClientId.isEmpty) {
      throw ConfigurationException('Client ID is required.');
    }

    if (kReleaseMode && (userPoolId.isEmpty || clientId.isEmpty)) {
      throw ConfigurationException(
        'Production build is missing required environment variables. '
        'USER_POOL_ID and CLIENT_ID must be set at build time.',
      );
    }

    debugPrint('Cognito configuration validated successfully');
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

      final userPoolId = AppConfig.userPoolIdWithFallback;
      final clientId = AppConfig.clientIdWithFallback;

      debugPrint(
        'Initializing Cognito with userPoolId: $userPoolId, clientId: $clientId',
      );

      userPool = CognitoUserPool(userPoolId, clientId);

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
        debugPrint('Invalid email format: $email');
        throw CognitoClientException('Invalid email format');
      }

      debugPrint(
        'Attempting sign-in for user: ${email.substring(0, min(3, email.length))}***',
      );

      // Clear any existing session first to prevent state conflicts
      if (_currentUser != null) {
        debugPrint('Clearing existing user session before sign-in');
        try {
          await _currentUser?.globalSignOut();
        } catch (e) {
          debugPrint('Error during global sign-out: $e');
          // Continue with sign-in despite error
        }
        _currentUser = null;
        _session = null;
      }

      final user = CognitoUser(email, userPool);
      final authDetails = AuthenticationDetails(
        username: email,
        password: password,
      );

      debugPrint('Authenticating user with Cognito using SRP');
      try {
        _session = await user.authenticateUser(authDetails);
      } catch (e) {
        if (e is CognitoClientException &&
            e.code == 'InvalidParameterException' &&
            e.message?.contains('USER_SRP_AUTH is not enabled') == true) {
          // Fallback to USER_PASSWORD_AUTH if SRP is not supported
          debugPrint(
            'SRP auth not supported, falling back to direct password auth',
          );

          // Need to set auth flow type on the user object before authentication
          user.setAuthenticationFlowType('USER_PASSWORD_AUTH');

          // Simple authentication details without extra parameters
          final passwordAuth = AuthenticationDetails(
            username: email,
            password: password,
          );

          _session = await user.authenticateUser(passwordAuth);
        } else {
          // Re-throw if it's not the SRP-specific error
          rethrow;
        }
      }
      _currentUser = user;

      debugPrint('Authentication successful, storing tokens');
      // Store tokens securely
      final storedSuccessfully = await _persistTokens(_session!, email);

      if (!storedSuccessfully) {
        debugPrint(
          'Warning: Token storage failed, session may not persist after app restart',
        );
      } else {
        debugPrint('Tokens stored successfully');
      }

      return user;
    } on CognitoClientException catch (e) {
      debugPrint('Cognito sign-in error: ${e.code}: ${e.message}');
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
      debugPrint('Signing out user');
      if (_currentUser != null) {
        try {
          // Try global sign-out first for better security (invalidates all sessions)
          debugPrint('Attempting global sign-out');
          try {
            await _currentUser?.globalSignOut();
            debugPrint('Global sign-out successful');
          } catch (e) {
            debugPrint(
              'Global sign-out failed: $e, falling back to regular sign-out',
            );
            // Fall back to regular sign-out
            await _currentUser?.signOut();
          }
        } catch (e) {
          // Log but don't throw for server-side signout issues
          _logError('Server sign-out error', e);
          debugPrint('Server-side sign-out failed: $e');
        }
      } else {
        debugPrint('No active user session to sign out');
      }
    } catch (e) {
      _logError('SignOut error', e);
      debugPrint('Error during sign-out process: $e');
      // Don't rethrow, we want signout to always succeed from the user's perspective
    } finally {
      // Always clear local state regardless of server communication errors
      debugPrint('Clearing local session state and tokens');
      _currentUser = null;
      _session = null;
      final cleared = await _clearTokens();
      if (!cleared) {
        _logError('Client sign-out incomplete', 'Failed to clear all tokens');
        debugPrint('Failed to clear all tokens during sign-out');
        throw AuthSignOutException(
          'Sign-out partially failed. Some data may not be cleared.',
        );
      } else {
        debugPrint('Local sign-out completed successfully');
      }
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
      debugPrint('Clearing stored authentication tokens');

      // Track which tokens were successfully cleared
      final results = await Future.wait([
        _secureStorage
            .delete(key: _accessTokenKey)
            .then((_) => true)
            .catchError((e) {
              debugPrint('Failed to clear access token: $e');
              return false;
            }),
        _secureStorage.delete(key: _idTokenKey).then((_) => true).catchError((
          e,
        ) {
          debugPrint('Failed to clear ID token: $e');
          return false;
        }),
        _secureStorage
            .delete(key: _refreshTokenKey)
            .then((_) => true)
            .catchError((e) {
              debugPrint('Failed to clear refresh token: $e');
              return false;
            }),
        _secureStorage.delete(key: _userEmailKey).then((_) => true).catchError((
          e,
        ) {
          debugPrint('Failed to clear user email: $e');
          return false;
        }),
      ]);

      // Verify all tokens were cleared successfully
      final allCleared = results.every((success) => success);
      debugPrint(
        'Initial token clearing ${allCleared ? 'succeeded' : 'had some failures'}',
      );

      // For extra precaution, verify tokens are actually gone
      final accessTokenValue = await _secureStorage.read(key: _accessTokenKey);
      final idTokenValue = await _secureStorage.read(key: _idTokenKey);
      final refreshTokenValue = await _secureStorage.read(
        key: _refreshTokenKey,
      );
      final emailValue = await _secureStorage.read(key: _userEmailKey);

      final allNull =
          accessTokenValue == null &&
          idTokenValue == null &&
          refreshTokenValue == null &&
          emailValue == null;

      if (!allNull) {
        debugPrint('Warning: Some tokens still exist after clearing attempt');

        // Make one more attempt to clear any remaining tokens
        if (accessTokenValue != null) {
          await _secureStorage.delete(key: _accessTokenKey);
        }
        if (idTokenValue != null) {
          await _secureStorage.delete(key: _idTokenKey);
        }
        if (refreshTokenValue != null) {
          await _secureStorage.delete(key: _refreshTokenKey);
        }
        if (emailValue != null) {
          await _secureStorage.delete(key: _userEmailKey);
        }
      }

      // Final verification
      final finalCheck =
          (await _secureStorage.read(key: _accessTokenKey) == null) &&
          (await _secureStorage.read(key: _idTokenKey) == null) &&
          (await _secureStorage.read(key: _refreshTokenKey) == null) &&
          (await _secureStorage.read(key: _userEmailKey) == null);

      if (finalCheck) {
        debugPrint('All tokens cleared successfully');
      } else {
        debugPrint('Failed to clear all tokens even after retry');
      }

      return finalCheck;
    } catch (e) {
      _logError('Error clearing tokens', e);
      debugPrint('Unexpected error while clearing tokens: $e');
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
        _logError(
          'Missing stored credentials',
          'Email or refresh token not found',
        );
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
        _logError(
          'Token persistence failed',
          'Unable to save refreshed tokens',
        );
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
      r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]+$',
    ).hasMatch(password);
  }

  /// Logs errors (can be replaced with proper logging framework)
  void _logError(String message, dynamic error) {
    // Log in both debug and release modes, but with different handling
    if (kDebugMode) {
      // In debug mode, print to console
      print('$message: $error');
    } else {
      debugPrint('Authentication error: ${message.split(':').first}');
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
