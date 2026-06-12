// Eidolon Engine
//
// Copyright 2024-2025 Jason E. Robinson

import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:flutter/material.dart';

enum AuthStatus { uninitialized, authenticated, unauthenticated, loading }

class AuthProvider extends ChangeNotifier {
  AuthStatus _status = AuthStatus.uninitialized;
  String? _userEmail;
  final AuthService _authService = AuthService.instance;

  AuthStatus get status => _status;
  String? get userEmail => _userEmail;
  bool get isAuthenticated => _status == AuthStatus.authenticated;

  AuthProvider() {
    _initializeAuth();
  }

  Future<void> _initializeAuth() async {
    try {
      await _authService.initialize();

      final isAuth = await _authService.isAuthenticated();

      if (isAuth) {
        _userEmail = await _authService.currentUserEmail;
        _status = AuthStatus.authenticated;
      } else {
        _status = AuthStatus.unauthenticated;
      }
      notifyListeners();
    } catch (err) {
      debugPrint('AuthProvider: Error during initialization: $err');
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
      await _authService.signIn(email, password);
      _userEmail = email;
      _status = AuthStatus.authenticated;
      notifyListeners();
    } catch (err) {
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

  Future<String> setupMfa() async {
    return await _authService.setupMfa();
  }

  Future<bool> verifyMfaSetup(String code) async {
    return await _authService.verifyMfaSetup(code);
  }

  Future<void> respondToMfaChallenge(String code) async {
    _status = AuthStatus.loading;
    notifyListeners();

    try {
      await _authService.respondToMfaChallenge(code);
      _userEmail = await _authService.currentUserEmail;
      _status = AuthStatus.authenticated;
      notifyListeners();
    } catch (err) {
      _status = AuthStatus.unauthenticated;
      notifyListeners();
      rethrow;
    }
  }

  Future<void> checkAuthStatus() async {
    try {
      final isAuth = await _authService.isAuthenticated();

      if (isAuth) {
        _userEmail = await _authService.currentUserEmail;
        _status = AuthStatus.authenticated;
      } else {
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
