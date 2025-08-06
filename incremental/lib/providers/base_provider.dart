import 'package:flutter/foundation.dart';

/// Base provider class that handles common functionality for all providers
abstract class BaseProvider extends ChangeNotifier {
  bool _isLoading = false;
  String? _error;
  bool _disposed = false;

  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get hasError => _error != null;

  /// Execute an async operation with automatic loading and error handling
  Future<T?> executeAsync<T>(
    Future<T> Function() action, {
    bool showLoading = true,
    Function(T)? onSuccess,
    Function(dynamic)? onError,
  }) async {
    if (_disposed) return null;

    if (showLoading) {
      _setLoading(true);
    }
    _setError(null);

    try {
      final result = await action();
      if (!_disposed) {
        onSuccess?.call(result);
      }
      return result;
    } catch (e) {
      if (!_disposed) {
        _setError(e.toString());
        onError?.call(e);
      }
      debugPrint('Error in $runtimeType: $e');
      return null;
    } finally {
      if (!_disposed && showLoading) {
        _setLoading(false);
      }
    }
  }

  /// Execute an async operation without returning a value
  Future<void> executeAsyncVoid(
    Future<void> Function() action, {
    bool showLoading = true,
    Function()? onSuccess,
    Function(dynamic)? onError,
  }) async {
    await executeAsync<void>(
      action,
      showLoading: showLoading,
      onSuccess: (_) => onSuccess?.call(),
      onError: onError,
    );
  }

  /// Set loading state
  void _setLoading(bool value) {
    if (_disposed) return;
    if (_isLoading != value) {
      _isLoading = value;
      notifyListeners();
    }
  }

  /// Set error state
  void _setError(String? value) {
    if (_disposed) return;
    if (_error != value) {
      _error = value;
      notifyListeners();
    }
  }

  /// Clear error state
  void clearError() {
    _setError(null);
  }

  /// Safe notify listeners that checks disposed state
  @override
  void notifyListeners() {
    if (!_disposed) {
      super.notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}