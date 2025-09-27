// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../services/auth_service.dart';

enum AuthStatus { uninitialized, authenticated, unauthenticated, loading }

class AuthProvider extends ChangeNotifier {
  AuthStatus _status = AuthStatus.uninitialized;
  String? _userEmail;
  final AuthService _authService = AuthService.instance;
  final String _instanceId = const Uuid().v7();

  AuthStatus get status => _status;
  String? get userEmail => _userEmail;
  bool get isAuthenticated => _status == AuthStatus.authenticated;

  AuthProvider() {
    // debugPrint('AuthProvider: Creating new instance $_instanceId');
    _initializeAuth();
  }

  Future<void> _initializeAuth() async {
    try {
      // debugPrint('AuthProvider $_instanceId: Initializing auth service...');
      await _authService.initialize();

      // debugPrint('AuthProvider $_instanceId: Checking authentication status...');
      final isAuth = await _authService.isAuthenticated();
      // debugPrint('AuthProvider $_instanceId: isAuthenticated = $isAuth');

      if (isAuth) {
        _userEmail = await _authService.currentUserEmail;
        // debugPrint('AuthProvider $_instanceId: User authenticated as $_userEmail');
        _status = AuthStatus.authenticated;
      } else {
        // debugPrint('AuthProvider $_instanceId: User not authenticated');
        _status = AuthStatus.unauthenticated;
      }
      notifyListeners();
    } catch (err) {
      debugPrint(
        'AuthProvider $_instanceId: Error during initialization: $err',
      );
      _status = AuthStatus.unauthenticated;
      notifyListeners();
    }
  }

  Future<void> signUp(String email, String password) async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      await _authService.signUp(email, password);
      _status = AuthStatus.unauthenticated;
      notifyListeners();
    } catch (err) {
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      rethrow;
    }
  }

  Future<bool> confirmRegistration(String email, String code) async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      final result = await _authService.confirmRegistration(email, code);
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      return result;
    } catch (err) {
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> signIn(String email, String password) async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      // debugPrint('AuthProvider: Starting signIn for $email');
      await _authService.signIn(email, password);
      _userEmail = email;
      _status = AuthStatus.authenticated;
      // debugPrint('AuthProvider: SignIn successful, status set to authenticated');
      notifyListeners();

      // Verify auth status immediately after login
      // final isAuth = await _authService.isAuthenticated();
      // debugPrint('AuthProvider: Post-login auth check: $isAuth');
    } catch (err) {
      // debugPrint('AuthProvider: SignIn failed: $err');
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> signOut() async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      await _authService.signOut();
    } finally {
      _userEmail = null;
      _status = AuthStatus.unauthenticated;
      notifyListeners();
    }
  }

  Future<void> resendConfirmationCode(String email) async {
    await _authService.resendConfirmationCode(email);
  }

  Future<void> forgotPassword(String email) async {
    await _authService.forgotPassword(email);
  }

  Future<void> confirmPassword(
    String email,
    String code,
    String newPassword,
  ) async {
    await _authService.confirmPassword(email, code, newPassword);
  }

  Future<void> deleteAccount() async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      await _authService.deleteUser();
      _userEmail = null;
      _status = AuthStatus.unauthenticated;
      notifyListeners();
    } catch (err) {
      _status = AuthStatus.authenticated;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> checkAuthStatus() async {
    try {
      debugPrint('AuthProvider: Checking auth status...');
      final isAuth = await _authService.isAuthenticated();
      debugPrint('AuthProvider: Auth check result: $isAuth');

      if (isAuth) {
        _userEmail = await _authService.currentUserEmail;
        debugPrint('AuthProvider: User is authenticated as $_userEmail');
        _status = AuthStatus.authenticated;
      } else {
        debugPrint('AuthProvider: User is not authenticated');
        _userEmail = null;
        _status = AuthStatus.unauthenticated;
      }
      notifyListeners();
    } catch (err) {
      debugPrint('AuthProvider: Error checking auth status: $err');
      _userEmail = null;
      _status = AuthStatus.unauthenticated;
      notifyListeners();
    }
  }
}
