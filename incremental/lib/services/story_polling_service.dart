import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_service.dart';

/// Simplified polling events
enum PollingEventType { characterUpdated, storyCompleted, error }

/// A polling event with its type and data
class PollingEvent {
  final PollingEventType type;
  final dynamic data;

  PollingEvent(this.type, [this.data]);
}

/// Server-authoritative polling service with simplified interface
///
/// This service provides a clean stream-based interface for story polling,
/// eliminating the complex callback setup while maintaining server-authoritative behavior.
class StoryPollingService {
  final ApiService _apiService;
  final StreamController<PollingEvent> _eventController =
      StreamController<PollingEvent>.broadcast();
  Timer? _pollTimer;
  bool _isPolling = false;
  String? _currentCharacterId;
  Timer? _delayTimer;
  Completer<void>? _delayCompleter;

  StoryPollingService({required ApiService apiService})
    : _apiService = apiService;

  /// Stream of polling events
  Stream<PollingEvent> get events => _eventController.stream;

  /// Whether polling is currently active
  bool get isPolling => _isPolling;

  /// Start polling for a character
  Future<void> startPolling(String characterId) async {
    if (_isPolling && _currentCharacterId == characterId) {
      debugPrint('StoryPollingService: Already polling for this character');
      return;
    }

    stopPolling(); // Stop any existing polling

    _currentCharacterId = characterId;
    _isPolling = true;

    debugPrint(
      'StoryPollingService: Starting polling for character: $characterId',
    );

    try {
      await _runPollingLoop(characterId);
    } finally {
      _isPolling = false;
      _currentCharacterId = null;
    }
  }

  /// Stop polling and cleanup
  void stopPolling() {
    if (!_isPolling) return;

    debugPrint('StoryPollingService: Stopping polling');
    _isPolling = false;
    _pollTimer?.cancel();
    _pollTimer = null;
    _currentCharacterId = null;
    _cancelActiveDelay();
  }

  /// Core polling loop following server cadence exactly
  Future<void> _runPollingLoop(String characterId) async {
    int consecutiveErrors = 0;
    const maxConsecutiveErrors = 3;

    // ALWAYS wait 60 seconds initially for server processing
    if (_isPolling) {
      await Future.delayed(const Duration(seconds: 60));
    }

    while (_isPolling) {
      try {
        // Step 2: Check character state for story completion
        final character = await _apiService.getCharacterById(characterId);

        // Check if polling was stopped during the await
        if (!_isPolling) break;

        if (character == null) {
          debugPrint('StoryPollingService: Character not found');
          _eventController.add(
            PollingEvent(PollingEventType.error, 'Character not found'),
          );
          break;
        }

        // Update UI with latest character data
        _eventController.add(
          PollingEvent(PollingEventType.characterUpdated, character),
        );

        // If no active segment, story is complete
        if (character.activeSegmentID == null) {
          debugPrint(
            'StoryPollingService: Story completed - no active segment',
          );
          _eventController.add(PollingEvent(PollingEventType.storyCompleted));
          break;
        }

        // Step 3: Get server timing for current segment
        final segmentStatus = await _apiService.getSegmentStatus(
          characterId: characterId,
        );

        // Check if polling was stopped during the await
        if (!_isPolling) break;

        // Step 4: Wait server-specified time exactly
        final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;

        debugPrint(
          'StoryPollingService: Server says wait $timeRemaining seconds',
        );

        if (timeRemaining > 0 && _isPolling) {
          // Wait the server-specified time before next poll
          await _waitFor(Duration(seconds: timeRemaining));
        } else if (_isPolling) {
          // If timeRemaining is 0 or negative, wait a small delay before next poll
          await _waitFor(const Duration(seconds: 5));
        }

        // Reset consecutive errors on successful poll cycle
        consecutiveErrors = 0;
      } catch (e) {
        consecutiveErrors++;
        debugPrint(
          'StoryPollingService: Polling error ($consecutiveErrors/$maxConsecutiveErrors): $e',
        );

        // Handle specific error cases as documented
        final errorStr = e.toString().toLowerCase();

        if (errorStr.contains('404') ||
            errorStr.contains('no active segment')) {
          // Story completed
          debugPrint('StoryPollingService: Story completed (404 response)');
          _eventController.add(PollingEvent(PollingEventType.storyCompleted));
          break;
        }

        if (consecutiveErrors >= maxConsecutiveErrors) {
          debugPrint(
            'StoryPollingService: Too many consecutive errors, stopping',
          );
          _eventController.add(
            PollingEvent(
              PollingEventType.error,
              'Connection failed after $maxConsecutiveErrors attempts',
            ),
          );
          break;
        }

        // Wait 30 seconds before retry as documented
        if (_isPolling) {
          await _waitFor(const Duration(seconds: 30));
        }
      }
    }

    debugPrint('StoryPollingService: Polling loop ended');
  }

  /// Dispose of resources
  void dispose() {
    stopPolling();
    _eventController.close();
  }

  Future<void> _waitFor(Duration duration) {
    if (duration.isNegative || duration == Duration.zero) {
      return Future.value();
    }

    _cancelActiveDelay();

    final completer = Completer<void>();
    _delayCompleter = completer;
    _delayTimer = Timer(duration, () {
      if (!completer.isCompleted) {
        completer.complete();
      }
      _clearDelayTimer();
      if (identical(_delayCompleter, completer)) {
        _delayCompleter = null;
      }
    });

    return completer.future;
  }

  void _cancelActiveDelay() {
    if (_delayTimer != null || _delayCompleter != null) {
      _clearDelayTimer();
      final completer = _delayCompleter;
      _delayCompleter = null;
      if (completer != null && !completer.isCompleted) {
        completer.complete();
      }
    }
  }

  void _clearDelayTimer() {
    _delayTimer?.cancel();
    _delayTimer = null;
  }
}
