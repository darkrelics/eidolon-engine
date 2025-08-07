import 'dart:async';
import 'package:flutter/foundation.dart';

/// Manages polling strategies for different game states
class PollingService {
  static const Duration _defaultPollingInterval = Duration(seconds: 60);
  static const Duration _mechanicalPollingInterval = Duration(minutes: 1);
  static const Duration _errorRetryInterval = Duration(seconds: 30);
  static const int _maxRetries = 3;

  final Map<String, Timer?> _activeTimers = {};
  final Map<String, int> _retryCounters = {};
  final Map<String, StreamController<void>> _pollStreams = {};

  /// Start polling for a specific key with a custom interval
  Stream<void> startPolling(
    String key, {
    Duration interval = _defaultPollingInterval,
    bool immediate = true,
  }) {
    // Cancel existing timer if any
    stopPolling(key);

    // Create stream controller if not exists
    _pollStreams[key] ??= StreamController<void>.broadcast();

    // Reset retry counter
    _retryCounters[key] = 0;

    // Execute immediately if requested
    if (immediate) {
      _pollStreams[key]!.add(null);
    }

    // Start periodic timer
    _activeTimers[key] = Timer.periodic(interval, (_) {
      _pollStreams[key]!.add(null);
    });

    return _pollStreams[key]!.stream;
  }

  /// Start mechanical segment polling with specific rules
  Stream<void> startMechanicalPolling(String characterId) {
    return startPolling(
      'mechanical_$characterId',
      interval: _mechanicalPollingInterval,
      immediate: true,
    );
  }

  /// Start story refresh polling
  Stream<void> startStoryPolling(String characterId) {
    return startPolling(
      'story_$characterId',
      interval: _defaultPollingInterval,
      immediate: false,
    );
  }

  /// Stop polling for a specific key
  void stopPolling(String key) {
    _activeTimers[key]?.cancel();
    _activeTimers[key] = null;
  }

  /// Stop all polling
  void stopAllPolling() {
    for (final timer in _activeTimers.values) {
      timer?.cancel();
    }
    _activeTimers.clear();
  }

  /// Handle polling error with retry logic
  Future<bool> handlePollingError(String key, VoidCallback onRetry) async {
    _retryCounters[key] = (_retryCounters[key] ?? 0) + 1;

    if (_retryCounters[key]! <= _maxRetries) {
      // Wait before retrying
      await Future.delayed(_errorRetryInterval);
      onRetry();
      return true; // Retry attempted
    }

    // Max retries reached, stop polling
    stopPolling(key);
    return false; // No retry
  }

  /// Reset retry counter on successful poll
  void resetRetryCounter(String key) {
    _retryCounters[key] = 0;
  }

  /// Check if polling is active for a key
  bool isPollingActive(String key) {
    return _activeTimers[key] != null && _activeTimers[key]!.isActive;
  }

  /// Dispose of all resources
  void dispose() {
    stopAllPolling();
    for (final controller in _pollStreams.values) {
      controller.close();
    }
    _pollStreams.clear();
    _retryCounters.clear();
  }
}

/// Singleton instance for global access
class PollingManager {
  static final PollingManager _instance = PollingManager._internal();
  factory PollingManager() => _instance;
  PollingManager._internal();

  final PollingService _service = PollingService();

  /// Start mechanical segment polling
  Stream<void> startMechanicalPolling(String characterId) {
    debugPrint('Starting mechanical polling for character: $characterId');
    return _service.startMechanicalPolling(characterId);
  }

  /// Start story refresh polling  
  Stream<void> startStoryPolling(String characterId) {
    debugPrint('Starting story polling for character: $characterId');
    return _service.startStoryPolling(characterId);
  }

  /// Stop specific polling
  void stopPolling(String key) {
    debugPrint('Stopping polling for: $key');
    _service.stopPolling(key);
  }

  /// Stop all polling
  void stopAllPolling() {
    debugPrint('Stopping all polling');
    _service.stopAllPolling();
  }

  /// Handle error with retry
  Future<bool> handleError(String key, VoidCallback onRetry) {
    return _service.handlePollingError(key, onRetry);
  }

  /// Reset retry counter
  void resetRetries(String key) {
    _service.resetRetryCounter(key);
  }

  /// Check polling status
  bool isActive(String key) {
    return _service.isPollingActive(key);
  }

  /// Clean up resources
  void dispose() {
    _service.dispose();
  }
}