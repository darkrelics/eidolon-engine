import 'package:flutter/material.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'auth_service.dart';

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

  void _updateMessage(String message) {
    _message = message;
    notifyListeners();
  }

  void _setLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
  }

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

  Future<void> signUp() async {
    if (!_validateInputs()) return;

    _setLoading(true);
    try {
      final signUpResult = await _authService.signUp(
        _emailController.text,
        _passwordController.text,
      );

      if (signUpResult.userConfirmed ?? false) {
        _updateMessage('User registered successfully. You can now log in.');
        _isSignUpMode = false;
      } else {
        _updateMessage('Please check your email for your verification code.');
        _isVerificationMode = true;
      }
    } on CognitoClientException catch (e) {
      _updateMessage('Registration failed: ${e.message}');
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  Future<void> confirmRegistration() async {
    if (_verificationCodeController.text.isEmpty) {
      _updateMessage('Please enter the verification code');
      return;
    }

    _setLoading(true);
    try {
      await _authService.confirmRegistration(
        _emailController.text,
        _verificationCodeController.text,
      );
      _updateMessage('Email confirmed successfully. You can now log in.');
      _isVerificationMode = false;
    } on CognitoClientException catch (e) {
      _updateMessage('Verification failed: ${e.message}');
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  Future<void> signIn() async {
    if (!_validateInputs()) return;

    _setLoading(true);
    try {
      await _authService.signIn(
        _emailController.text,
        _passwordController.text,
      );
      _updateMessage('Login Successful!');
      _isSignUpMode = false;
      _isAuthenticated = true;
      notifyListeners();
    } on CognitoClientException catch (e) {
      _updateMessage('Login failed: ${e.message}');
      _isAuthenticated = false;
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
      _isAuthenticated = false;
    } finally {
      _setLoading(false);
    }
  }

  Future<void> signOut() async {
    _setLoading(true);
    try {
      await _authService.signOut();
      _isAuthenticated = false;
      _updateMessage('Successfully signed out');
    } catch (e) {
      _updateMessage('Error signing out: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  bool _validateInputs() {
    if (_emailController.text.isEmpty || _passwordController.text.isEmpty) {
      _updateMessage('Please fill in all fields');
      return false;
    }
    return true;
  }

  void toggleAuthMode() {
    _message = '';
    _isSignUpMode = !_isSignUpMode;
    notifyListeners();
  }

  void clearInputs() {
    _emailController.clear();
    _passwordController.clear();
    _verificationCodeController.clear();
    _message = '';
    notifyListeners();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _verificationCodeController.dispose();
    _passwordController.dispose();
    super.dispose();
  }
}