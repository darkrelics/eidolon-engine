// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Configuration class for AWS Cognito authentication settings.
/// 
/// This class manages the Cognito User Pool and Client IDs needed for authentication.
/// In production, these values MUST be provided via environment variables during build.
/// In development mode (kDebugMode), placeholder values are used as fallbacks to simplify local testing.
/// 
/// The environment variables USER_POOL_ID and CLIENT_ID are injected at compile time
/// using the --dart-define flags during the Flutter build process.
class CognitoConfig {
  static const String userPoolId = String.fromEnvironment('USER_POOL_ID');
  static const String clientId = String.fromEnvironment('CLIENT_ID');

  /// Development fallback values for local testing only.
  /// These are placeholder values that allow the app to run in development mode
  /// without requiring actual AWS Cognito configuration.
  /// NEVER use these in production - they are intentionally invalid.
  static String get _devUserPoolId => kDebugMode ? 'us-east-1_devUserPool' : '';
  static String get _devClientId => kDebugMode ? '1example2client3id4567890abc' : '';

  /// Returns the User Pool ID with fallback to development value in debug mode
  static String get userPoolIdWithFallback => userPoolId.isNotEmpty ? userPoolId : _devUserPoolId;

  /// Returns the Client ID with fallback to development value in debug mode
  static String get clientIdWithFallback => clientId.isNotEmpty ? clientId : _devClientId;

  /// Validates that the Cognito configuration is properly set.
  /// In production (release mode), this ensures environment variables are provided.
  /// In development (debug mode), this allows fallback values to be used.
  /// 
  /// This should be called during app initialization to fail fast on configuration issues.
  static void validateConfiguration() {
    final effectiveUserPoolId = userPoolIdWithFallback;
    final effectiveClientId = clientIdWithFallback;

    // In production, environment variables MUST be provided - no fallbacks allowed
    if (kReleaseMode && (userPoolId.isEmpty || clientId.isEmpty)) {
      throw ConfigurationException(
        'Production build is missing required environment variables. '
        'Ensure USER_POOL_ID and CLIENT_ID are provided via --dart-define during build.'
      );
    }

    // Basic validation - user pool ID must have the correct format
    if (effectiveUserPoolId.isEmpty || !effectiveUserPoolId.contains('_')) {
      throw ConfigurationException(
        'Invalid User Pool ID format. Expected format: "region_poolId" (e.g., "us-east-1_abcd1234")'
      );
    }

    // Client ID must be present and have reasonable length
    if (effectiveClientId.isEmpty) {
      throw ConfigurationException(
        'Client ID is missing. Ensure CLIENT_ID environment variable is set.'
      );
    }
    
    if (effectiveClientId.length < 10) {
      throw ConfigurationException(
        'Client ID appears invalid (too short). Expected a valid Cognito Client ID.'
      );
    }
  }

  /// Static validation that runs when the class is first accessed.
  /// This ensures configuration issues are caught early in the app lifecycle.
  // ignore: unused_field
  static final bool _isValidated = _performEarlyValidation();
  
  static bool _performEarlyValidation() {
    // Only validate automatically in release mode to catch production issues early
    if (kReleaseMode) {
      validateConfiguration();
    }
    return true;
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
      // Log the error code in debug mode to help diagnose issues
      if (kDebugMode) {
        debugPrint('AuthExceptionMapper: Cognito error code: ${error.code}');
        debugPrint('AuthExceptionMapper: Cognito error message: ${error.message}');
      }

      switch (error.code) {
        case 'UserNotFoundException':
        case 'NotAuthorizedException':
          return 'Invalid email or password';
        case 'UserNotConfirmedException':
          return 'Please verify your email before signing in';
        case 'InvalidParameterException':
          if (error.message?.toLowerCase().contains('password') == true) {
            return 'Password must meet complexity requirements';
          }
          return 'Please check your input and try again';
        case 'UsernameExistsException':
          return 'The Player Account already exists.';
        case 'LimitExceededException':
          return 'Too many attempts. Please try again later';
        case 'InvalidPasswordException':
          return 'Password must meet complexity requirements';
        case 'CodeMismatchException':
          return 'Invalid verification code. Please try again';
        case 'ExpiredCodeException':
          return 'Verification code has expired. Please request a new one';
        default:
          // Check if the error message contains username exists indication
          if (error.message?.toLowerCase().contains('username exists') == true ||
              error.message?.toLowerCase().contains('user already exists') == true ||
              error.message?.toLowerCase().contains('already registered') == true) {
            return 'The Player Account already exists.';
          }
          return 'An error occurred. Please try again';
      }
    }

    // Additional check for non-Cognito exceptions that might indicate duplicate account
    if (error.toString().toLowerCase().contains('username exists') ||
        error.toString().toLowerCase().contains('user already exists') ||
        error.toString().toLowerCase().contains('already registered')) {
      return 'The Player Account already exists.';
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
  bool _isInitialized = false;

  static const String _accessTokenKey = 'access_token';
  static const String _idTokenKey = 'id_token';
  static const String _refreshTokenKey = 'refresh_token';
  static const String _userEmailKey = 'user_email';

  static AuthService? _instance;

  AuthService._();

  static AuthService get instance {
    _instance ??= AuthService._();
    return _instance!;
  }

  /// Initializes authentication configuration
  Future<void> initialize() async {
    if (_isInitialized) return;

    try {
      CognitoConfig.validateConfiguration();

      final userPoolId = CognitoConfig.userPoolIdWithFallback;
      final clientId = CognitoConfig.clientIdWithFallback;

      userPool = CognitoUserPool(userPoolId, clientId);
      _isInitialized = true;

      await _restoreSession();
    } catch (err) {
      _logError('Authentication initialization error', err);
      rethrow;
    }
  }

  /// Signs up a new user
  Future<CognitoUserPoolData> signUp(String email, String password) async {
    await _ensureInitialized();

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
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Account creation failed', err);
      rethrow;
    }
  }

  /// Confirms user registration with verification code
  Future<bool> confirmRegistration(String email, String code) async {
    await _ensureInitialized();

    try {
      if (code.isEmpty) {
        throw CognitoClientException('Verification code cannot be empty');
      }

      final user = CognitoUser(email, userPool);
      return await user.confirmRegistration(code);
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Account verification failed', err);
      rethrow;
    }
  }

  /// Signs in a user
  Future<CognitoUser> signIn(String email, String password) async {
    await _ensureInitialized();

    try {
      if (!_validateEmail(email)) {
        throw CognitoClientException('Invalid email format');
      }

      if (_currentUser != null) {
        try {
          await _currentUser?.globalSignOut();
        } catch (err) {
          _logError('Global sign out error', err);
        }
        _currentUser = null;
        _session = null;
      }

      final user = CognitoUser(email, userPool);
      final authDetails = AuthenticationDetails(username: email, password: password);

      try {
        _session = await user.authenticateUser(authDetails);
      } catch (err) {
        if (err is CognitoClientException &&
            err.code == 'InvalidParameterException' &&
            err.message?.contains('USER_SRP_AUTH is not enabled') == true) {
          user.setAuthenticationFlowType('USER_PASSWORD_AUTH');

          final passwordAuth = AuthenticationDetails(username: email, password: password);

          _session = await user.authenticateUser(passwordAuth);
        } else {
          rethrow;
        }
      }
      _currentUser = user;

      await _persistTokens(_session!, email);

      return user;
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Sign in failed', err);
      rethrow;
    }
  }

  /// Signs out the current user
  Future<void> signOut() async {
    try {
      if (_currentUser != null) {
        try {
          try {
            await _currentUser?.globalSignOut();
          } catch (err) {
            await _currentUser?.signOut();
          }
        } catch (err) {
          _logError('Sign out error', err);
        }
      }
    } catch (err) {
      _logError('Sign out failed', err);
    } finally {
      _currentUser = null;
      _session = null;
      final cleared = await _clearTokens();
      if (!cleared) {
        throw AuthSignOutException('Sign-out partially failed. Please try again.');
      }
    }
  }

  /// Checks if user is authenticated
  Future<bool> isAuthenticated() async {
    await _ensureInitialized();

    try {
      // debugPrint('AuthService: isAuthenticated check - _currentUser: ${_currentUser != null}, _session: ${_session != null}');

      if (_currentUser == null || _session == null) {
        // debugPrint('AuthService: No current session in memory, attempting restore...');
        final restored = await _restoreSession();
        // debugPrint('AuthService: Restore session result: $restored');
        if (!restored) return false;
      }

      if (_session == null) return false;

      final isValid = _session!.isValid();
      // debugPrint('AuthService: Session validity: $isValid');

      if (!isValid) {
        // debugPrint('AuthService: Session invalid, attempting refresh...');
        return await _refreshSession();
      }

      return true;
    } catch (err) {
      _logError('Session validation failed', err);
      return false;
    }
  }

  /// Gets the current ID token for API authentication
  Future<String?> getIdToken() async {
    await _ensureInitialized();

    try {
      if (_currentUser == null || _session == null) {
        final restored = await _restoreSession();
        if (!restored) return null;
      }

      if (_session == null) return null;

      if (!_session!.isValid()) {
        final refreshed = await _refreshSession();
        if (!refreshed) return null;
      }

      return _session!.getIdToken().getJwtToken();
    } catch (err) {
      _logError('Failed to get ID token', err);
      return null;
    }
  }

  /// Resends the confirmation code
  Future<void> resendConfirmationCode(String email) async {
    await _ensureInitialized();

    try {
      final user = CognitoUser(email, userPool);
      await user.resendConfirmationCode();
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Failed to send verification code', err);
      rethrow;
    }
  }

  /// Initiates password reset by sending reset code to user's email
  Future<void> forgotPassword(String email) async {
    await _ensureInitialized();

    try {
      if (!_validateEmail(email)) {
        throw CognitoClientException('Invalid email format');
      }

      final user = CognitoUser(email, userPool);
      await user.forgotPassword();
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Failed to initiate password reset', err);
      rethrow;
    }
  }

  /// Confirms password reset with code and new password
  Future<void> confirmPassword(String email, String code, String newPassword) async {
    await _ensureInitialized();

    try {
      if (!_validateEmail(email)) {
        throw CognitoClientException('Invalid email format');
      }

      if (code.isEmpty) {
        throw CognitoClientException('Verification code cannot be empty');
      }

      if (!_validatePassword(newPassword)) {
        throw CognitoClientException(
          'Password must be at least 8 characters with uppercase, lowercase, number and special character',
        );
      }

      final user = CognitoUser(email, userPool);
      await user.confirmPassword(code, newPassword);
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Failed to reset password', err);
      rethrow;
    }
  }

  /// Deletes the current user's account permanently
  Future<void> deleteUser() async {
    await _ensureInitialized();

    try {
      if (_currentUser == null || _session == null) {
        throw CognitoClientException('User must be signed in to delete account');
      }

      if (!_session!.isValid()) {
        final refreshed = await _refreshSession();
        if (!refreshed) {
          throw CognitoClientException('Session expired. Please sign in again');
        }
      }

      await _currentUser!.deleteUser();

      _currentUser = null;
      _session = null;
      await _clearTokens();
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('Account deletion failed', err);
      rethrow;
    }
  }

  /// Persists authentication tokens
  Future<bool> _persistTokens(CognitoUserSession session, String email) async {
    try {
      await _secureStorage.write(key: _accessTokenKey, value: session.getAccessToken().getJwtToken());
      await _secureStorage.write(key: _idTokenKey, value: session.getIdToken().getJwtToken());
      await _secureStorage.write(key: _refreshTokenKey, value: session.getRefreshToken()?.getToken());
      await _secureStorage.write(key: _userEmailKey, value: email);
      return true;
    } catch (err) {
      _logError('Session storage issue', err);
      return false;
    }
  }

  /// Clears stored tokens
  Future<bool> _clearTokens() async {
    try {
      await Future.wait([
        _secureStorage.delete(key: _accessTokenKey),
        _secureStorage.delete(key: _idTokenKey),
        _secureStorage.delete(key: _refreshTokenKey),
        _secureStorage.delete(key: _userEmailKey),
      ]);

      final accessTokenValue = await _secureStorage.read(key: _accessTokenKey);
      final idTokenValue = await _secureStorage.read(key: _idTokenKey);
      final refreshTokenValue = await _secureStorage.read(key: _refreshTokenKey);
      final emailValue = await _secureStorage.read(key: _userEmailKey);

      final allNull = accessTokenValue == null && idTokenValue == null && refreshTokenValue == null && emailValue == null;

      return allNull;
    } catch (err) {
      _logError('Session cleanup issue', err);
      return false;
    }
  }

  /// Attempts to restore previous session from stored tokens
  Future<bool> _restoreSession() async {
    try {
      final email = await _secureStorage.read(key: _userEmailKey);
      final refreshToken = await _secureStorage.read(key: _refreshTokenKey);

      if (email == null || refreshToken == null) {
        _logError('No stored session found', null);
        return false;
      }

      _currentUser = CognitoUser(email, userPool);
      final cognitoRefreshToken = CognitoRefreshToken(refreshToken);

      try {
        _session = await _currentUser!.refreshSession(cognitoRefreshToken);
      } on CognitoClientException {
        _logError('Session refresh failed', null);
        await _clearTokens();
        return false;
      }

      final tokensPersisted = await _persistTokens(_session!, email);
      if (!tokensPersisted) {
        _logError('Session persistence issue', null);
      }

      return true;
    } catch (err) {
      _logError('Session restoration failed', err);
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

      final email = await _secureStorage.read(key: _userEmailKey);
      if (email != null) {
        await _persistTokens(_session!, email);
      }

      return true;
    } catch (err) {
      _logError('Session refresh failed', err);
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

    return RegExp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]+$').hasMatch(password);
  }

  /// Logs errors in a secure way without exposing sensitive information
  void _logError(String message, dynamic err) {
    if (kDebugMode) {
      debugPrint('Auth: $message');
      if (err != null) {
        debugPrint('Error: $err');
      }
    }
  }

  /// Ensures the service is initialized
  Future<void> _ensureInitialized() async {
    if (!_isInitialized) {
      await initialize();
    }
  }

  /// Gets the current user
  CognitoUser? get currentUser => _currentUser;

  /// Gets the current session
  CognitoUserSession? get session => _session;

  /// Gets the current user's email
  Future<String?> get currentUserEmail async => await _secureStorage.read(key: _userEmailKey);
}
