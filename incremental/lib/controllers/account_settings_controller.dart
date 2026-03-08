import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:flutter/foundation.dart';

class AccountSettingsController extends ChangeNotifier {
  final AuthProvider _authProvider;
  bool _isLoading = false;

  bool get isLoading => _isLoading;

  AccountSettingsController({required AuthProvider authProvider}) : _authProvider = authProvider;

  Future<void> signOut({required VoidCallback onSuccess, required Function(String) onError}) async {
    _setLoading(true);
    try {
      await _authProvider.signOut();
      onSuccess();
    } catch (e) {
      onError(ErrorHandler.getUserFriendlyMessage(e, context: 'signing out'));
    } finally {
      _setLoading(false);
    }
  }

  Future<void> deleteAccount({required VoidCallback onSuccess, required Function(String) onError}) async {
    _setLoading(true);
    try {
      await _authProvider.deleteAccount();
      onSuccess();
    } catch (e) {
      onError(ErrorHandler.getUserFriendlyMessage(e, context: 'deleting account'));
    } finally {
      _setLoading(false);
    }
  }

  void _setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }
}
