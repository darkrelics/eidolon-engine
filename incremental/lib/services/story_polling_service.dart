import 'dart:async';

import '../models/character.dart';
import 'api_service.dart';

/// Coordinates the network cadence for story segments:
/// - Start: UI is updated immediately from /story/start
/// - First status: GET /segment/status at T+60s from segment start
/// - While unprocessed: repeat status calls every 30s
/// - Expiry: at EndTime, GET /character to load next segment or completion
class StoryPollingService {
  StoryPollingService({required ApiService apiService}) : _apiService = apiService;

  // Tunables (seconds)
  static const int firstStatusDelaySeconds = 60;
  static const int repeatStatusDelaySeconds = 30;

  final ApiService _apiService;

  String? _characterId;
  // Track only character ID; segment ID not needed for cadence

  Timer? _firstStatusTimer;
  Timer? _repeatStatusTimer;
  Timer? _expiryTimer;

  bool _processed = false;
  Map<String, dynamic>? _lastStatus;
  int _consecutiveErrors = 0;

  void dispose() {
    cancel();
  }

  void cancel() {
    _firstStatusTimer?.cancel();
    _firstStatusTimer = null;
    _repeatStatusTimer?.cancel();
    _repeatStatusTimer = null;
    _expiryTimer?.cancel();
    _expiryTimer = null;
  }

  /// Starts orchestration for the character's current active segment.
  ///
  /// Callbacks should be lightweight UI updates; network is handled here.
  void start({
    required Character character,
    required void Function(Character newCharacter) onCharacterReloaded,
    void Function(Map<String, dynamic> status)? onStatusUpdated,
    void Function(Map<String, dynamic>? finalStatus)? onStoryComplete,
    void Function(Object error)? onError,
  }) {
    cancel();

    _characterId = character.id;
    _consecutiveErrors = 0;
    final storyState = character.storyState ?? const <String, dynamic>{};
    final activeSegment = storyState['ActiveSegment'] as Map<String, dynamic>?;
    if (activeSegment == null) {
      return; // Nothing to orchestrate
    }

    _processed = _isProcessed(activeSegment);

    final segmentStart = _parseDate(activeSegment['StartTime']) ?? DateTime.now().toUtc();
    final end = _resolveEndTime(activeSegment, segmentStart);

    // First status at T+60s from segment start
    final firstStatusAt = segmentStart.add(const Duration(seconds: firstStatusDelaySeconds));
    final delayToFirst = firstStatusAt.difference(DateTime.now().toUtc());
    final firstDelay = delayToFirst.isNegative ? Duration.zero : delayToFirst;

    _firstStatusTimer = Timer(firstDelay, () async {
      await _performStatusCheck(onStatusUpdated: onStatusUpdated, onError: onError);
      // If not yet processed, schedule repeating status every 30s
      if (!_processed) {
        _repeatStatusTimer = Timer.periodic(
          const Duration(seconds: repeatStatusDelaySeconds),
          (_) async {
            await _performStatusCheck(onStatusUpdated: onStatusUpdated, onError: onError);
            if (_processed) {
              _repeatStatusTimer?.cancel();
              _repeatStatusTimer = null;
            }
          },
        );
      }
    });

    // Expiry timer triggers character reload exactly at EndTime
    if (end != null) {
      final untilExpiry = end.difference(DateTime.now().toUtc());
      final expiryDelay = untilExpiry.isNegative ? Duration.zero : untilExpiry;
      _expiryTimer = Timer(expiryDelay, () async {
        try {
          final id = _characterId;
          if (id == null) return;
          final updated = await _apiService.getCharacterById(id);
          if (updated == null) return;

          onCharacterReloaded(updated);

          // Determine if story ended
          if (updated.activeSegmentID == null) {
            // Completed
            onStoryComplete?.call(_lastStatus);
          } else {
            // New segment -> restart orchestration
            start(
              character: updated,
              onCharacterReloaded: onCharacterReloaded,
              onStatusUpdated: onStatusUpdated,
              onStoryComplete: onStoryComplete,
              onError: onError,
            );
          }
        } catch (e) {
          onError?.call(e);
        }
      });
    }
  }

  Future<void> _performStatusCheck({
    void Function(Map<String, dynamic>)? onStatusUpdated,
    void Function(Object)? onError,
  }) async {
    final id = _characterId;
    if (id == null) return;
    try {
      final status = await _apiService.getSegmentStatus(characterId: id);
      onStatusUpdated?.call(status);
      _lastStatus = status;

      // Mark processed if server indicates completion
      if (_isProcessed(status)) {
        _processed = true;
      }
      // Successful call resets error counter
      _consecutiveErrors = 0;
    } catch (e) {
      // Treat 404/no active segment as completion edge case; allow expiry GET to handle transition
      final msg = e.toString().toLowerCase();
      if (msg.contains('no active segment')) {
        _processed = true; // Avoid further status polls
        _repeatStatusTimer?.cancel();
        _repeatStatusTimer = null;
        return;
      }
      _consecutiveErrors += 1;
      onError?.call(e);
      if (_consecutiveErrors >= 3) {
        // Stop all timers after too many consecutive failures
        cancel();
      }
    }
  }

  static bool _isProcessed(Map<String, dynamic> segmentOrStatus) {
    final storyComplete = segmentOrStatus['StoryComplete'] == true || segmentOrStatus['IsComplete'] == true;
    if (storyComplete) return true;
    final proc = segmentOrStatus['ProcessingStatus']?.toString().toLowerCase();
    if (proc == 'processed') return true;
    final status = segmentOrStatus['Status']?.toString().toLowerCase();
    return status == 'completed' || status == 'complete';
  }

  static DateTime? _parseDate(Object? value) {
    if (value == null) return null;
    if (value is DateTime) return value.toUtc();
    if (value is String && value.isNotEmpty) {
      try {
        return DateTime.parse(value).toUtc();
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  static DateTime? _resolveEndTime(Map<String, dynamic> segment, DateTime start) {
    final end = _parseDate(segment['EndTime']);
    if (end != null) return end;

    final rawDuration = segment['Duration'] ?? segment['SegmentDuration'] ?? segment['ExpectedDuration'];
    int duration = 60;
    if (rawDuration is num) {
      duration = rawDuration.toInt();
    } else if (rawDuration is String) {
      duration = int.tryParse(rawDuration) ?? 60;
    }
    if (duration <= 0) duration = 60;
    return start.add(Duration(seconds: duration));
  }
}
