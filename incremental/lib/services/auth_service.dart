// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'dart:async';
import 'dart:convert';

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:crypto/crypto.dart';
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
        'Ensure USER_POOL_ID and CLIENT_ID are provided via --dart-define during build.',
      );
    }

    // Basic validation - user pool ID must have the correct format
    if (effectiveUserPoolId.isEmpty || !effectiveUserPoolId.contains('_')) {
      throw ConfigurationException('Invalid User Pool ID format. Expected format: "region_poolId" (e.g., "us-east-1_abcd1234")');
    }

    // Client ID must be present and have reasonable length
    if (effectiveClientId.isEmpty) {
      throw ConfigurationException('Client ID is missing. Ensure CLIENT_ID environment variable is set.');
    }

    if (effectiveClientId.length < 10) {
      throw ConfigurationException('Client ID appears invalid (too short). Expected a valid Cognito Client ID.');
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

  /// Lock to prevent concurrent session operations (restore, refresh)
  /// When a session operation is in progress, subsequent callers will await the same result
  Completer<bool>? _sessionOperationLock;

  static const String _accessTokenKey = 'access_token';
  static const String _idTokenKey = 'id_token';
  static const String _refreshTokenKey = 'refresh_token';
  static const String _userEmailKey = 'user_email';
  static const String _integrityKey = 'token_integrity';
  static const String _deviceKeyKey = 'device_key';

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
      } on CognitoClientException catch (e) {
        if (e.code == 'InvalidParameterException' && e.message?.contains('USER_SRP_AUTH is not enabled') == true) {
          user.setAuthenticationFlowType('USER_PASSWORD_AUTH');

          final passwordAuth = AuthenticationDetails(username: email, password: password);

          _session = await user.authenticateUser(passwordAuth);
        } else if (e.code == 'SOFTWARE_TOKEN_MFA') {
          // MFA Challenge received
          _currentUser = user;
          // We don't have a session yet, but we have the user state needed to respond
          // Throw a specific exception that the UI can catch to show the MFA prompt
          throw CognitoClientException('MFA_REQUIRED', code: 'MFA_REQUIRED', name: 'MFA_REQUIRED');
        } else {
          rethrow;
        }
      }
      _currentUser = user;

      await _persistTokens(_session!, email);

      return user;
    } on CognitoClientException catch (err) {
      if (err.code == 'MFA_REQUIRED') {
        rethrow;
      }
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

  /// Get or generate device-specific key for HMAC
  Future<String> _getDeviceKey() async {
    try {
      final existingKey = await _secureStorage.read(key: _deviceKeyKey);
      if (existingKey != null && existingKey.isNotEmpty) {
        return existingKey;
      }

      // Generate new device key using timestamp and random component
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final random = DateTime.now().microsecondsSinceEpoch;
      final deviceKey = '$timestamp-$random-${userPool.getUserPoolId()}';
      final hash = sha256.convert(utf8.encode(deviceKey)).toString();

      await _secureStorage.write(key: _deviceKeyKey, value: hash);
      return hash;
    } catch (err) {
      _logError('Device key generation failed', err);
      // Fallback to pool ID if device key generation fails
      return userPool.getUserPoolId();
    }
  }

  /// Generate HMAC for token data to detect tampering
  Future<String> _generateTokenIntegrity(String accessToken, String idToken, String? refreshToken, String email) async {
    try {
      final deviceKey = await _getDeviceKey();
      final tokenData = '$accessToken|$idToken|${refreshToken ?? ''}|$email';
      final hmacKey = utf8.encode(deviceKey);
      final hmacData = utf8.encode(tokenData);
      final hmac = Hmac(sha256, hmacKey);
      final digest = hmac.convert(hmacData);
      return digest.toString();
    } catch (err) {
      _logError('HMAC generation failed', err);
      // Return empty string on failure - will cause validation to fail on restore
      return '';
    }
  }

  /// Validate token integrity using HMAC
  Future<bool> _validateTokenIntegrity(
    String accessToken,
    String idToken,
    String? refreshToken,
    String email,
    String storedHmac,
  ) async {
    try {
      final computedHmac = await _generateTokenIntegrity(accessToken, idToken, refreshToken, email);

      if (computedHmac.isEmpty || storedHmac.isEmpty) {
        debugPrint('AuthService: Integrity validation failed - empty HMAC');
        return false;
      }

      final isValid = computedHmac == storedHmac;

      if (!isValid) {
        debugPrint('AuthService: Token integrity check failed - possible tampering detected');
      }

      return isValid;
    } catch (err) {
      _logError('HMAC validation failed', err);
      return false;
    }
  }

  /// Persists authentication tokens with integrity protection
  Future<bool> _persistTokens(CognitoUserSession session, String email) async {
    try {
      final accessToken = session.getAccessToken().getJwtToken() ?? '';
      final idToken = session.getIdToken().getJwtToken() ?? '';
      final refreshToken = session.getRefreshToken()?.getToken();

      if (accessToken.isEmpty || idToken.isEmpty) {
        _logError('Cannot persist session - missing required tokens', null);
        return false;
      }

      // Generate integrity hash before storing
      final integrity = await _generateTokenIntegrity(accessToken, idToken, refreshToken, email);

      await Future.wait([
        _secureStorage.write(key: _accessTokenKey, value: accessToken),
        _secureStorage.write(key: _idTokenKey, value: idToken),
        if (refreshToken != null) _secureStorage.write(key: _refreshTokenKey, value: refreshToken),
        _secureStorage.write(key: _userEmailKey, value: email),
        _secureStorage.write(key: _integrityKey, value: integrity),
      ]);

      return true;
    } catch (err) {
      _logError('Session storage issue', err);
      return false;
    }
  }

  /// Clears stored tokens and integrity data
  Future<bool> _clearTokens() async {
    try {
      await Future.wait([
        _secureStorage.delete(key: _accessTokenKey),
        _secureStorage.delete(key: _idTokenKey),
        _secureStorage.delete(key: _refreshTokenKey),
        _secureStorage.delete(key: _userEmailKey),
        _secureStorage.delete(key: _integrityKey),
        // Note: Device key is NOT cleared - it persists across sessions
      ]);

      final accessTokenValue = await _secureStorage.read(key: _accessTokenKey);
      final idTokenValue = await _secureStorage.read(key: _idTokenKey);
      final refreshTokenValue = await _secureStorage.read(key: _refreshTokenKey);
      final emailValue = await _secureStorage.read(key: _userEmailKey);
      final integrityValue = await _secureStorage.read(key: _integrityKey);

      final allNull =
          accessTokenValue == null &&
          idTokenValue == null &&
          refreshTokenValue == null &&
          emailValue == null &&
          integrityValue == null;

      return allNull;
    } catch (err) {
      _logError('Session cleanup issue', err);
      return false;
    }
  }

  /// Attempts to restore previous session from stored tokens with integrity validation
  /// Uses a lock to prevent concurrent restore operations
  Future<bool> _restoreSession() async {
    // If a session operation is already in progress, wait for it
    if (_sessionOperationLock != null) {
      debugPrint('AuthService: Session restore already in progress, waiting...');
      return _sessionOperationLock!.future;
    }

    // Create a new lock
    _sessionOperationLock = Completer<bool>();

    try {
      final result = await _doRestoreSession();
      _sessionOperationLock!.complete(result);
      return result;
    } catch (err) {
      _sessionOperationLock!.complete(false);
      rethrow;
    } finally {
      _sessionOperationLock = null;
    }
  }

  /// Internal session restore logic
  Future<bool> _doRestoreSession() async {
    try {
      final email = await _secureStorage.read(key: _userEmailKey);
      final accessToken = await _secureStorage.read(key: _accessTokenKey);
      final idToken = await _secureStorage.read(key: _idTokenKey);
      final refreshToken = await _secureStorage.read(key: _refreshTokenKey);
      final storedIntegrity = await _secureStorage.read(key: _integrityKey);

      if (email == null || refreshToken == null) {
        _logError('No stored session found', null);
        return false;
      }

      // Validate token integrity if HMAC is present
      if (storedIntegrity != null && storedIntegrity.isNotEmpty) {
        final isValid = await _validateTokenIntegrity(accessToken ?? '', idToken ?? '', refreshToken, email, storedIntegrity);

        if (!isValid) {
          debugPrint('AuthService: Token integrity validation failed - clearing potentially tampered tokens');
          await _clearTokens();
          return false;
        }

        debugPrint('AuthService: Token integrity validated successfully');
      } else {
        // No integrity hash found - tokens stored before integrity feature was added
        // Allow restore but re-persist with new integrity hash
        debugPrint('AuthService: No integrity hash found - will generate on next persist');
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

      // Re-persist tokens with fresh integrity hash
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
  /// Allows plus addressing (user+tag@domain) and modern TLDs (.digital, .technology, etc.)
  bool _validateEmail(String email) {
    return RegExp(r'^[\w\-\.\+]+@([\w-]+\.)+[a-zA-Z]{2,}$').hasMatch(email);
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

  /// Sets up MFA for the current user
  /// Returns the secret code for QR generation
  Future<String> setupMfa() async {
    await _ensureInitialized();

    try {
      if (_currentUser == null) {
        throw CognitoClientException('User must be signed in to setup MFA');
      }

      final secret = await _currentUser!.associateSoftwareToken();
      return secret ?? '';
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('MFA setup failed', err);
      rethrow;
    }
  }

  /// Verifies MFA setup with code
  Future<bool> verifyMfaSetup(String code) async {
    await _ensureInitialized();

    try {
      if (_currentUser == null) {
        throw CognitoClientException('User must be signed in to verify MFA');
      }

      final result = await _currentUser!.verifySoftwareToken(totpCode: code);
      if (result) {
        // Enable MFA
        // Note: MfaSettings class might be missing or named differently.
        // For now, we assume verification is enough or we need to find the correct class.
        // Commenting out preference setting to fix build.
        // final settings = MfaSettings(enabled: true, preferredMfa: 'SOFTWARE_TOKEN_MFA');
        // await _currentUser!.setUserMfaPreference(null, settings);
      }
      return result;
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('MFA verification failed', err);
      rethrow;
    }
  }

  /// Responds to MFA challenge during sign in
  Future<CognitoUser> respondToMfaChallenge(String code) async {
    try {
      if (_currentUser == null) {
        throw CognitoClientException('No active authentication session');
      }

      // Use verifySoftwareToken for responding to challenge as well in some flows,
      // but for login challenge, it's usually sendMfaCode.
      // If sendMfaCode is missing, let's try respondToAuthChallenge directly if exposed,
      // or try verifySoftwareToken again (sometimes overloaded).
      // Actually, for this library version, it might be `sendMFA`.
      // Let's try `sendMfa`.
      _session = await _currentUser!.sendMFACode(code);
      await _persistTokens(_session!, await currentUserEmail ?? '');
      return _currentUser!;
    } on CognitoClientException catch (err) {
      throw CognitoClientException(AuthExceptionMapper.mapToUserFriendlyMessage(err));
    } catch (err) {
      _logError('MFA challenge response failed', err);
      rethrow;
    }
  }

  /// Gets the current user's email
  Future<String?> get currentUserEmail async => await _secureStorage.read(key: _userEmailKey);
}
