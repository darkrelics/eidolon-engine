// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/material.dart';

import '../services/auth_service.dart';
import 'input_sanitizer.dart';

/// State management for authentication
class AuthState extends ChangeNotifier {
  final AuthService _authService;
  final _emailController = TextEditingController();
  final _verificationCodeController = TextEditingController();
  final _passwordController = TextEditingController();

  String _message = '';
  bool _isLoading = false;
  bool _isVerificationMode = false;
  bool _isSignUpMode = true;
  bool _isAuthenticated = false;
  int _loginAttempts = 0;
  DateTime? _lastAttemptTime;

  AuthState({required AuthService authService}) : _authService = authService {
    // Check authentication status when initialized
    checkAuthStatus();
  }

  // Getters
  TextEditingController get emailController => _emailController;
  TextEditingController get verificationCodeController => _verificationCodeController;
  TextEditingController get passwordController => _passwordController;
  CognitoUser? get currentUser => _authService.currentUser;
  bool get isVerificationMode => _isVerificationMode;
  bool get isSignUpMode => _isSignUpMode;
  String get message => _message;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _isAuthenticated;
  String? get userEmail => currentUser?.username;

  /// Updates message and notifies listeners
  void _updateMessage(String message) {
    _message = InputSanitizer.sanitizeDisplayText(message);
    notifyListeners();
  }

  /// Sets loading state and notifies listeners
  void _setLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
  }

  /// Checks if account is locked due to too many attempts
  bool _isAccountLocked() {
    if (_loginAttempts >= 5 && _lastAttemptTime != null) {
      final difference = DateTime.now().difference(_lastAttemptTime!);
      if (difference.inMinutes < 15) {
        return true;
      }
      // Reset after 15 minutes
      _loginAttempts = 0;
      _lastAttemptTime = null;
    }
    return false;
  }

  /// Increments login attempts
  void _incrementLoginAttempts() {
    _loginAttempts++;
    _lastAttemptTime = DateTime.now();
  }

  /// Resets login attempts
  void _resetLoginAttempts() {
    _loginAttempts = 0;
    _lastAttemptTime = null;
  }

  /// Checks current authentication status
  Future<bool> checkAuthStatus() async {
    try {
      _isAuthenticated = await _authService.isAuthenticated();
      notifyListeners();
      return _isAuthenticated;
    } catch (e) {
      _isAuthenticated = false;
      notifyListeners();
      return false;
    }
  }

  /// Signs up a new user
  Future<void> signUp() async {
    if (!_validateInputs(isSignUp: true)) return;

    _setLoading(true);
    try {
      final signUpResult = await _authService.signUp(_emailController.text.trim(), _passwordController.text);

      if (signUpResult.userConfirmed ?? false) {
        _updateMessage('Registration successful. Please sign in.');
        _isSignUpMode = false;
        // Don't clear password to allow immediate sign in
        _verificationCodeController.clear();
      } else {
        _updateMessage('Please check your email for a verification code.');
        _isVerificationMode = true;
      }
    } on CognitoClientException catch (e) {
      // Authentication-specific errors already formatted by AuthService
      _updateMessage(e.message ?? 'Registration failed');
    } catch (e) {
      _updateMessage('An unexpected error occurred. Please try again.');
    } finally {
      _setLoading(false);
    }
  }

  /// Confirms user registration with verification code
  Future<void> confirmRegistration() async {
    final code = _verificationCodeController.text.trim();
    if (code.isEmpty) {
      _updateMessage('Please enter the verification code');
      return;
    }

    // Sanitize verification code
    if (!_validateSecureInput(code)) {
      _updateMessage('Invalid verification code format');
      return;
    }

    final email = _emailController.text.trim();
    final password = _passwordController.text;

    _setLoading(true);
    try {
      final result = await _authService.confirmRegistration(email, code);

      // Store credentials temporarily for sign-in attempt
      final tempEmail = email;
      final tempPassword = password;

      // Clear verification mode and related UI state
      _isVerificationMode = false;
      _isSignUpMode = false;
      _verificationCodeController.clear();

      if (result) {
        // Important: Clear credentials first to ensure we don't have stale state
        await _authService.signOut();

        try {
          // Attempt automatic sign-in after verification
          await _authService.signIn(tempEmail, tempPassword);
          _isAuthenticated = true;
          _updateMessage('Account verified and logged in successfully.');
          clearInputs(); // Clear sensitive data after successful login
        } catch (signInError) {
          _updateMessage('Email verified successfully. Please sign in manually.');
          // Don't clear email to make manual sign-in easier
          _emailController.text = tempEmail;
          _passwordController.text = '';
        }
      } else {
        _updateMessage('Verification process completed. Please sign in.');
      }
    } on CognitoClientException catch (e) {
      // Authentication-specific errors already formatted by AuthService
      _updateMessage(e.message ?? 'Verification failed');
    } catch (e) {
      _updateMessage('An unexpected error occurred. Please try again.');
    } finally {
      _setLoading(false);
    }
  }

  /// Signs in a user
  Future<void> signIn() async {
    if (_isAccountLocked()) {
      _updateMessage('Account temporarily locked. Please try again later.');
      return;
    }

    if (!_validateInputs(isSignUp: false)) return;

    _setLoading(true);
    try {
      await _authService.signIn(_emailController.text.trim(), _passwordController.text);
      _updateMessage('Sign in successful');
      _isSignUpMode = false;
      _isAuthenticated = true;
      _resetLoginAttempts();
      clearInputs();
    } on CognitoClientException catch (e) {
      _incrementLoginAttempts();
      // Authentication-specific errors already formatted by AuthService
      _updateMessage(e.message ?? 'Sign in failed');
      _isAuthenticated = false;
    } catch (e) {
      _updateMessage('An unexpected error occurred. Please try again.');
      _isAuthenticated = false;
    } finally {
      _setLoading(false);
    }
  }

  /// Signs out the current user
  Future<void> signOut() async {
    _setLoading(true);
    try {
      await _authService.signOut();
      _isAuthenticated = false;
      _updateMessage('Successfully signed out');
      clearInputs();
    } catch (e) {
      _updateMessage('Error signing out. Please try again.');
    } finally {
      _setLoading(false);
    }
  }

  /// Validates email format
  bool _validateEmail(String email) {
    return InputSanitizer.validateEmail(email);
  }

  /// Validates password complexity
  bool _validatePassword(String password, {bool checkComplexity = false}) {
    if (password.length < 8) {
      _updateMessage('Password must be at least 8 characters long');
      return false;
    }

    if (InputSanitizer.containsDangerousChars(password)) {
      _updateMessage('Password contains invalid characters');
      return false;
    }

    if (checkComplexity) {
      // Check for uppercase, lowercase, number, and special character
      // End anchor $ added to ensure the entire string is validated
      if (!RegExp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]+$').hasMatch(password)) {
        _updateMessage('Password must contain uppercase, lowercase, number, and special character');
        return false;
      }
    }

    return true;
  }

  /// Validates secure input without XSS characters
  bool _validateSecureInput(String input) {
    return !InputSanitizer.containsDangerousChars(input);
  }

  /// Validates input fields before submission
  bool _validateInputs({required bool isSignUp}) {
    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (email.isEmpty || password.isEmpty) {
      _updateMessage('Please fill in all fields');
      return false;
    }

    if (!_validateEmail(email)) {
      _updateMessage('Please enter a valid email address');
      return false;
    }

    // Only check password complexity during sign up
    if (isSignUp && !_validatePassword(password, checkComplexity: true)) {
      return false;
    }

    // Basic password length check for sign in
    if (!isSignUp && password.length < 8) {
      _updateMessage('Invalid email or password');
      return false;
    }

    return true;
  }

  /// Toggles between sign up and sign in modes
  void toggleAuthMode() {
    _message = '';
    _isSignUpMode = !_isSignUpMode;
    _isVerificationMode = false;
    notifyListeners();
  }

  /// Clears all input fields and messages securely
  void clearInputs() {
    _emailController.clear();
    _passwordController.clear();
    _verificationCodeController.clear();
    _message = '';
    // Force a garbage collection hint for sensitive data
    // This is a hint to Dart runtime, not a guarantee
    String.fromCharCodes([]);
    notifyListeners();
  }

  /// Handles deep linking for email verification or password reset
  Future<void> handleDeepLink(Uri uri) async {
    if (uri.pathSegments.contains('verify')) {
      final code = uri.queryParameters['code'];
      final email = uri.queryParameters['email'];

      if (code != null && email != null) {
        // Sanitize inputs from deep link
        if (_validateEmail(email) && _validateSecureInput(code)) {
          _emailController.text = email;
          _verificationCodeController.text = code;
          _isVerificationMode = true;
          _isSignUpMode = true;
          notifyListeners();
          await confirmRegistration();
        } else {
          _updateMessage('Invalid verification link');
        }
      }
    }
  }

  /// Resends the verification code
  Future<void> resendVerificationCode() async {
    if (_emailController.text.isEmpty) {
      _updateMessage('Please enter your email address');
      return;
    }

    if (!_validateEmail(_emailController.text.trim())) {
      _updateMessage('Please enter a valid email address');
      return;
    }

    _setLoading(true);
    try {
      await _authService.resendConfirmationCode(_emailController.text.trim());
      _updateMessage('Verification code resent. Please check your email.');
    } on CognitoClientException catch (e) {
      _updateMessage(e.message ?? 'Failed to resend verification code');
    } catch (e) {
      _updateMessage('An unexpected error occurred. Please try again.');
    } finally {
      _setLoading(false);
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _verificationCodeController.dispose();
    // Clear sensitive data
    _message = '';
    _isAuthenticated = false;
    super.dispose();
  }
}
