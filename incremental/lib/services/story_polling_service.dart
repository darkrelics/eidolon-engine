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
  static const Duration _minSuccessfulPollInterval = Duration(seconds: 60);
  static const Duration _minFailedPollInterval = Duration(seconds: 10);

  final ApiService _apiService;
  final StreamController<PollingEvent> _eventController = StreamController<PollingEvent>.broadcast();
  Timer? _pollTimer;
  bool _isPolling = false;
  String? _currentCharacterId;
  Timer? _delayTimer;
  Completer<void>? _delayCompleter;

  StoryPollingService({required ApiService apiService}) : _apiService = apiService;

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

    debugPrint('StoryPollingService: Starting polling for character: $characterId');

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
    String? lastSegmentId;
    String? lastProcessingStatus;
    bool lastStoryComplete = false;

    while (_isPolling) {
      try {
        final segmentStatus = await _apiService.getSegmentStatus(characterId: characterId);

        if (!_isPolling) break;

        final currentSegmentId = segmentStatus['SegmentID']?.toString();
        final rawProcessingStatus = segmentStatus['ProcessingStatus']?.toString().toLowerCase();
        final fallbackStatus = segmentStatus['Status']?.toString().toLowerCase();
        final processingStatus = (rawProcessingStatus?.isNotEmpty ?? false) ? rawProcessingStatus : fallbackStatus;
        final storyCompleteFlag = segmentStatus['StoryComplete'] == true || segmentStatus['IsComplete'] == true;

        final segmentChanged = lastSegmentId != null && currentSegmentId != null && currentSegmentId != lastSegmentId;

        const completeStatuses = {'processed', 'complete', 'completed'};
        final processingStateChanged =
            processingStatus != null && processingStatus != lastProcessingStatus && completeStatuses.contains(processingStatus);

        final storyJustCompleted = storyCompleteFlag && !lastStoryComplete;

        if (currentSegmentId != null && lastSegmentId == null) {
          lastSegmentId = currentSegmentId;
        }

        final shouldReloadCharacter = segmentChanged || processingStateChanged || storyJustCompleted;

        if (shouldReloadCharacter) {
          final character = await _apiService.getCharacterById(characterId);

          if (!_isPolling) break;

          if (character == null) {
            debugPrint('StoryPollingService: Character not found');
            _eventController.add(PollingEvent(PollingEventType.error, 'Character not found'));
            break;
          }

          _eventController.add(PollingEvent(PollingEventType.characterUpdated, character));

          final activeSegmentId = character.activeSegmentID;
          if (activeSegmentId == null) {
            debugPrint('StoryPollingService: Story completed - no active segment');
            _eventController.add(PollingEvent(PollingEventType.storyCompleted));
            lastStoryComplete = true;
            break;
          }

          if (currentSegmentId != null) {
            lastSegmentId = currentSegmentId;
          } else {
            lastSegmentId = activeSegmentId;
          }
          lastProcessingStatus = processingStatus ?? lastProcessingStatus;
          lastStoryComplete = storyCompleteFlag;
          consecutiveErrors = 0;
        } else {
          lastProcessingStatus = processingStatus ?? lastProcessingStatus;
          lastStoryComplete = storyCompleteFlag;
        }

        if (currentSegmentId != null) {
          lastSegmentId = currentSegmentId;
        }
        final recommendedWait = _determineWaitDuration(segmentStatus);
        final waitDuration = _applySuccessInterval(recommendedWait);
        final rawRemaining = segmentStatus['TimeRemaining'];
        final enforcedSuffix = waitDuration > recommendedWait ? ', enforcing ${_minSuccessfulPollInterval.inSeconds}s minimum' : '';

        debugPrint(
          'StoryPollingService: Waiting ${waitDuration.inSeconds}s '
          '(server TimeRemaining: $rawRemaining$enforcedSuffix)',
        );

        if (_isPolling) {
          await _waitFor(waitDuration);
        }

        // Reset consecutive errors on successful poll cycle
        consecutiveErrors = 0;
      } catch (e) {
        consecutiveErrors++;
        debugPrint('StoryPollingService: Polling error ($consecutiveErrors/$maxConsecutiveErrors): $e');

        // Handle specific error cases as documented
        final errorStr = e.toString().toLowerCase();

        if (errorStr.contains('404') || errorStr.contains('no active segment')) {
          // Story completed
          debugPrint('StoryPollingService: Story completed (404 response)');
          _eventController.add(PollingEvent(PollingEventType.storyCompleted));
          break;
        }

        if (consecutiveErrors >= maxConsecutiveErrors) {
          debugPrint('StoryPollingService: Too many consecutive errors, stopping');
          _eventController.add(PollingEvent(PollingEventType.error, 'Connection failed after $maxConsecutiveErrors attempts'));
          break;
        }

        // Wait before retrying to respect minimum failure backoff
        if (_isPolling) {
          await _waitFor(_minFailedPollInterval);
        }
      }
    }

    debugPrint('StoryPollingService: Polling loop ended');
  }

  Duration _applySuccessInterval(Duration recommendedWait) {
    final minWait = _minSuccessfulPollInterval;

    // Always respect the minimum cadence so we never poll faster than the
    // system resolution.
    if (recommendedWait < minWait) {
      return minWait;
    }

    return recommendedWait;
  }

  /// Dispose of resources
  void dispose() {
    stopPolling();
    _eventController.close();
  }

  Duration _determineWaitDuration(Map<String, dynamic> segmentStatus) {
    const minWait = Duration(seconds: 1);
    const networkPadding = Duration(seconds: 1);

    // Check if this is a decision segment - if so, pause polling until user acts
    final segmentType = segmentStatus['SegmentType']?.toString().toLowerCase();
    if (segmentType == 'decision') {
      debugPrint('StoryPollingService: Decision segment detected, pausing polling');
      return const Duration(hours: 1); // Effectively pause polling for decision segments
    }

    Duration? timeRemaining;
    final rawRemaining = segmentStatus['TimeRemaining'];
    if (rawRemaining is num) {
      final seconds = rawRemaining.floor();
      timeRemaining = Duration(seconds: seconds < 0 ? 0 : seconds);
    }

    Duration? endTimeRemaining;
    final endTimeString = segmentStatus['EndTime'] as String?;
    if (endTimeString != null) {
      final endTime = DateTime.tryParse(endTimeString);
      if (endTime != null) {
        endTimeRemaining = endTime.difference(DateTime.now().toUtc());
      }
    }

    Duration? calculated;
    if (timeRemaining != null && endTimeRemaining != null) {
      calculated = timeRemaining < endTimeRemaining ? timeRemaining : endTimeRemaining;
    } else {
      calculated = timeRemaining ?? endTimeRemaining;
    }

    var waitDuration = calculated ?? const Duration(seconds: 5);

    if (waitDuration.isNegative) {
      waitDuration = minWait;
    } else if (waitDuration > networkPadding) {
      waitDuration -= networkPadding;
    }

    if (waitDuration < minWait) {
      waitDuration = minWait;
    }

    return waitDuration;
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
