import 'package:eidolon_incremental/models/character.dart';

/// Manages segment history data and caching for the game screen.
///
/// This is a plain data manager class (not a ChangeNotifier). It owns all
/// segment history state, deduplication logic, and caching. The controller
/// is responsible for calling notifyListeners() after mutating state via
/// this manager.
class SegmentHistoryManager {
  List<Map<String, dynamic>> _segments = const [];
  int _segmentCounter = 0;

  // Caching
  List<Map<String, dynamic>>? _cachedCompletedSegments;
  String? _completedSegmentsCacheKey;
  List<Map<String, dynamic>>? _cachedStoryHistory;
  String? _storyHistoryCacheKey;

  /// The raw list of segment history entries.
  List<Map<String, dynamic>> get segments => _segments;

  /// Direct setter for the segment list (used when replacing wholesale).
  set segments(List<Map<String, dynamic>> value) {
    _segments = value;
    invalidateCache();
  }

  /// Current segment counter value (read-only).
  int get segmentCounter => _segmentCounter;

  /// Resets all state back to initial values.
  void reset() {
    _segments = <Map<String, dynamic>>[];
    _segmentCounter = 0;
    invalidateCache();
  }

  /// Invalidates all cached computed results.
  void invalidateCache() {
    _cachedCompletedSegments = null;
    _completedSegmentsCacheKey = null;
    _cachedStoryHistory = null;
    _storyHistoryCacheKey = null;
  }

  /// Returns a stable identity key for a segment, used for deduplication.
  String segmentIdentity(Map<String, dynamic> segment) {
    // Primary key: ActiveSegmentID (unique execution identifier)
    final activeSegmentId = segment['ActiveSegmentID'];
    if (activeSegmentId != null) {
      final idString = activeSegmentId.toString().trim();
      if (idString.isNotEmpty) {
        return 'active:$idString';
      }
    }

    // Fallback: SegmentID (story definition identifier)
    final segmentId = segment['SegmentID'];
    if (segmentId != null) {
      final idString = segmentId.toString().trim();
      if (idString.isNotEmpty) {
        return 'segment:$idString';
      }
    }

    // Last resort: Composite key from available fields
    final storyInstanceId = segment['StoryInstanceID']?.toString().trim();
    final storyId = segment['StoryID']?.toString().trim();
    final segmentActivity = segment['SegmentActivity']?.toString().trim();
    final segmentTitle = segment['SegmentTitle']?.toString().trim();
    final prompt = segment['Prompt']?.toString().trim();

    final parts = <String>[
      if (storyInstanceId != null && storyInstanceId.isNotEmpty) storyInstanceId,
      if (storyId != null && storyId.isNotEmpty) storyId,
      if (segmentActivity != null && segmentActivity.isNotEmpty) segmentActivity,
      if (segmentTitle != null && segmentTitle.isNotEmpty) segmentTitle,
      if (prompt != null && prompt.isNotEmpty) prompt,
    ];

    if (parts.isEmpty) {
      return 'fallback:${segment.hashCode}';
    }

    return 'composite:${parts.join('|')}';
  }

  /// Sorts segments in chronological order by their `_index` field.
  void sortSegmentsChronologically(List<Map<String, dynamic>> segments, {bool newestFirst = false}) {
    segments.sort((a, b) {
      final aIndex = a['_index'] as int?;
      final bIndex = b['_index'] as int?;

      if (aIndex != null && bIndex != null) {
        return newestFirst ? bIndex.compareTo(aIndex) : aIndex.compareTo(bIndex);
      }

      if (aIndex == null && bIndex == null) return 0;
      if (aIndex == null) return 1;
      if (bIndex == null) return -1;

      return 0;
    });
  }

  /// Returns true if a segment is considered complete.
  bool isSegmentComplete(Map<String, dynamic> segment) {
    final completedAt = segment['CompletedAt'];
    if (completedAt is String && completedAt.isNotEmpty) return true;
    if (completedAt is num && completedAt > 0) return true;
    if (segment['Status']?.toString().toLowerCase() == 'completed') return true;

    final processingStatus = segment['ProcessingStatus']?.toString().toLowerCase();
    if (processingStatus == 'processed') {
      final endTimeStr = segment['EndTime']?.toString();
      if (endTimeStr != null && endTimeStr.isNotEmpty) {
        try {
          final endTime = DateTime.parse(endTimeStr).toUtc();
          final now = DateTime.now().toUtc();
          return now.isAfter(endTime) || now.isAtSameMomentAs(endTime);
        } catch (e) {
          // ignore
        }
      }
      final timeRemaining = segment['TimeRemaining'];
      if (timeRemaining is num) {
        return timeRemaining <= 0;
      }
      return false;
    }

    if (segment['StoryComplete'] == true) return true;

    return false;
  }

  /// Adds a new segment or updates an existing one in the history.
  ///
  /// This encapsulates the repeated pattern of:
  /// 1. Making a copy of the segment data
  /// 2. Adding StoryTitle from lastStoryDetails if missing
  /// 3. Checking if the segment already exists by identity key
  /// 4. Adding with a new _index or updating while preserving the existing _index
  ///
  /// Returns true if the segment was newly added, false if it was updated.
  bool addOrUpdateSegment(Map<String, dynamic> segment, Map<String, dynamic>? lastStoryDetails) {
    final copy = Map<String, dynamic>.from(segment);
    if (!copy.containsKey('StoryTitle') && lastStoryDetails != null) {
      copy['StoryTitle'] = lastStoryDetails['Title'];
    }

    final segmentKey = segmentIdentity(copy);
    final exists = _segments.any((s) => segmentIdentity(s) == segmentKey);

    if (!exists) {
      copy['_index'] = _segmentCounter++;
      _segments = [..._segments, copy];
      invalidateCache();
      return true;
    }

    _segments = _segments.map((s) {
      if (segmentIdentity(s) == segmentKey) {
        if (s.containsKey('_index')) {
          copy['_index'] = s['_index'];
        }
        return copy;
      }
      return s;
    }).toList();
    invalidateCache();
    return false;
  }

  /// Returns completed segments, excluding the currently active segment.
  List<Map<String, dynamic>> getCompletedSegments(String? activeSegmentId) {
    final cacheKey = '${activeSegmentId ?? 'none'}_${_segments.length}_$_segmentCounter';

    if (_completedSegmentsCacheKey == cacheKey && _cachedCompletedSegments != null) {
      return _cachedCompletedSegments!;
    }

    final completed = _segments.where((segment) {
      final segmentActiveId = segment['ActiveSegmentID']?.toString() ?? segment['SegmentID']?.toString();
      final isComplete = segmentActiveId != activeSegmentId && isSegmentComplete(segment);
      return isComplete;
    }).toList();

    sortSegmentsChronologically(completed, newestFirst: true);

    _completedSegmentsCacheKey = cacheKey;
    _cachedCompletedSegments = completed;

    return completed;
  }

  /// Builds a deduplicated story history archive from both the character's
  /// storyState CompletedSegments and the local segment history.
  List<Map<String, dynamic>> buildStoryHistoryArchive(
    String? activeSegmentId,
    Map<String, dynamic>? storyState,
    List<Map<String, dynamic>> segmentHistory,
  ) {
    final stateSegmentsLength = (storyState?['CompletedSegments'] as List?)?.length ?? 0;
    final cacheKey = '${activeSegmentId ?? 'none'}_${segmentHistory.length}_${_segmentCounter}_$stateSegmentsLength';

    if (_storyHistoryCacheKey == cacheKey && _cachedStoryHistory != null) {
      return _cachedStoryHistory!;
    }

    final Map<String, Map<String, dynamic>> deduped = {};

    void addSegments(Iterable<Map<String, dynamic>> segments) {
      for (final segment in segments) {
        final copy = Map<String, dynamic>.from(segment);
        final segmentActiveId = copy['ActiveSegmentID']?.toString() ?? copy['SegmentID']?.toString();
        final key = segmentIdentity(copy);

        final isActiveSegment = activeSegmentId != null && segmentActiveId == activeSegmentId;
        if (!isActiveSegment) {
          deduped[key] = copy;
        }
      }
    }

    final completedSegmentsDynamic = storyState?['CompletedSegments'] as List<dynamic>?;
    if (completedSegmentsDynamic != null) {
      final completedSegments = completedSegmentsDynamic
          .whereType<Map<String, dynamic>>()
          .where(isSegmentComplete)
          .map((segment) => Map<String, dynamic>.from(segment));
      addSegments(completedSegments);
    }

    if (segmentHistory.isNotEmpty) {
      final historyCopies = segmentHistory.where(isSegmentComplete).map((segment) => Map<String, dynamic>.from(segment));
      addSegments(historyCopies);
    }

    final segments = deduped.values.toList();
    sortSegmentsChronologically(segments);

    _storyHistoryCacheKey = cacheKey;
    _cachedStoryHistory = segments;

    return segments;
  }

  /// Synchronizes story completion state on the character when no active segment
  /// exists. Returns an updated character if changes were made, or null if no
  /// changes were needed.
  Character? synchronizeStoryCompletionState(Character? character, Map<String, dynamic>? lastStoryDetails) {
    if (character == null || _segments.isEmpty) return null;
    if (character.activeSegmentID != null) return null;

    final currentStoryState = character.storyState ?? <String, dynamic>{};
    final updatedStoryState = Map<String, dynamic>.from(currentStoryState);

    final synchronizedSegments = _segments.map((segment) => Map<String, dynamic>.from(segment)).toList();
    sortSegmentsChronologically(synchronizedSegments);
    updatedStoryState['CompletedSegments'] = synchronizedSegments;

    if (!updatedStoryState.containsKey('Story') && lastStoryDetails != null) {
      updatedStoryState['Story'] = Map<String, dynamic>.from(lastStoryDetails);
    }

    return character.copyWith(storyState: updatedStoryState);
  }

  /// Assigns _index to segments that don't have one and increments the counter.
  /// Returns the processed list of segments.
  List<Map<String, dynamic>> assignIndices(List<Map<String, dynamic>> segments) {
    return segments.map((segment) {
      final copy = Map<String, dynamic>.from(segment);
      if (!copy.containsKey('_index')) {
        copy['_index'] = _segmentCounter++;
      }
      return copy;
    }).toList();
  }
}
