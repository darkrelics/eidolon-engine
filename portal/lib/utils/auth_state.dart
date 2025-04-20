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

import 'package:flutter/material.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import '../services/auth_service.dart';

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

  AuthState({required AuthService authService}) : _authService = authService {
    // Check authentication status when initialized
    checkAuthStatus();
  }

  // Getters
  TextEditingController get emailController => _emailController;
  TextEditingController get verificationCodeController =>
      _verificationCodeController;
  TextEditingController get passwordController => _passwordController;
  CognitoUser? get currentUser => _authService.currentUser;
  bool get isVerificationMode => _isVerificationMode;
  bool get isSignUpMode => _isSignUpMode;
  String get message => _message;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _isAuthenticated;

  /// Updates message and notifies listeners
  void _updateMessage(String message) {
    _message = message;
    notifyListeners();
  }

  /// Sets loading state and notifies listeners
  void _setLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
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
      final signUpResult = await _authService.signUp(
        _emailController.text.trim(),
        _passwordController.text,
      );

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

    _setLoading(true);
    try {
      await _authService.confirmRegistration(
        _emailController.text.trim(),
        code,
      );
      _updateMessage('Email verified successfully. Please sign in.');
      _isVerificationMode = false;
      _isSignUpMode = false;
      _verificationCodeController.clear();
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
    if (!_validateInputs(isSignUp: false)) return;

    _setLoading(true);
    try {
      await _authService.signIn(
        _emailController.text.trim(),
        _passwordController.text,
      );
      _updateMessage('Sign in successful');
      _isSignUpMode = false;
      _isAuthenticated = true;
      clearInputs();
    } on CognitoClientException catch (e) {
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
    return RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(email);
  }

  /// Validates password complexity
  bool _validatePassword(String password, {bool checkComplexity = false}) {
    if (password.length < 8) {
      _updateMessage('Password must be at least 8 characters long');
      return false;
    }

    if (checkComplexity) {
      // Check for uppercase, lowercase, number, and special character
      if (!RegExp(
        r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]',
      ).hasMatch(password)) {
        _updateMessage(
          'Password must contain uppercase, lowercase, number, and special character',
        );
        return false;
      }
    }

    return true;
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

  /// Clears all input fields and messages
  void clearInputs() {
    _emailController.clear();
    _passwordController.clear();
    _verificationCodeController.clear();
    _message = '';
    notifyListeners();
  }

  /// Handles deep linking for email verification or password reset
  Future<void> handleDeepLink(Uri uri) async {
    if (uri.pathSegments.contains('verify')) {
      final code = uri.queryParameters['code'];
      final email = uri.queryParameters['email'];

      if (code != null && email != null) {
        _emailController.text = email;
        _verificationCodeController.text = code;
        _isVerificationMode = true;
        _isSignUpMode = true;
        notifyListeners();
        await confirmRegistration();
      }
    }
  }

  /// Resends the verification code
  Future<void> resendVerificationCode() async {
    if (_emailController.text.isEmpty) {
      _updateMessage('Please enter your email address');
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
