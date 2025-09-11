import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart';

/// Service for caching completed story data locally
/// 
/// This prevents loss of story segment data when transitioning between
/// story states, allowing users to view completed story narratives.
class StoryCacheService {
  static StoryCacheService? _instance;
  static const String _keyPrefix = 'completed_story_';
  static const String _storyListKey = 'completed_story_list';
  
  StoryCacheService._internal();
  
  factory StoryCacheService() {
    _instance ??= StoryCacheService._internal();
    return _instance!;
  }

  /// Cache a completed story's data
  /// 
  /// Stores the complete story state including segments, story metadata,
  /// and completion timestamp for later retrieval.
  Future<void> cacheCompletedStory({
    required String characterId,
    required String storyId,
    required Map<String, dynamic> storyState,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Create the cached story data structure
      final cachedStory = {
        'characterId': characterId,
        'storyId': storyId,
        'storyState': storyState,
        'completedAt': DateTime.now().toIso8601String(),
        'version': '1.0', // For future compatibility
      };
      
      // Store the individual story
      final key = '$_keyPrefix${characterId}_$storyId';
      await prefs.setString(key, jsonEncode(cachedStory));
      
      // Update the list of cached stories for this character
      await _updateCachedStoryList(characterId, storyId);
      
      debugPrint('StoryCacheService: Cached story $storyId for character $characterId');
    } catch (e) {
      debugPrint('StoryCacheService: Failed to cache story: $e');
    }
  }

  /// Retrieve a cached completed story
  Future<Map<String, dynamic>?> getCachedStory({
    required String characterId,
    required String storyId,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = '$_keyPrefix${characterId}_$storyId';
      final cachedData = prefs.getString(key);
      
      if (cachedData != null) {
        final decoded = jsonDecode(cachedData) as Map<String, dynamic>;
        debugPrint('StoryCacheService: Retrieved cached story $storyId for character $characterId');
        return decoded;
      }
      
      debugPrint('StoryCacheService: No cached story found for $storyId');
      return null;
    } catch (e) {
      debugPrint('StoryCacheService: Failed to retrieve cached story: $e');
      return null;
    }
  }

  /// Get all cached completed stories for a character
  Future<List<CompletedStoryInfo>> getCachedStoriesForCharacter(String characterId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final listKey = '${_storyListKey}_$characterId';
      final storyIds = prefs.getStringList(listKey) ?? [];
      
      final List<CompletedStoryInfo> completedStories = [];
      
      for (final storyId in storyIds) {
        final cachedStory = await getCachedStory(
          characterId: characterId,
          storyId: storyId,
        );
        
        if (cachedStory != null) {
          final storyState = cachedStory['storyState'] as Map<String, dynamic>;
          final story = storyState['Story'] as Map<String, dynamic>?;
          final segments = storyState['CompletedSegments'] as List<dynamic>?;
          
          if (story != null && segments != null) {
            completedStories.add(CompletedStoryInfo(
              storyId: storyId,
              storyTitle: story['Title'] as String? ?? storyId,
              storyDescription: story['Description'] as String? ?? '',
              storyType: story['Type'] as String? ?? 'story',
              completedAt: DateTime.parse(cachedStory['completedAt'] as String),
              segmentCount: segments.length,
              lastOutcome: _extractLastOutcome(segments),
            ));
          }
        }
      }
      
      // Sort by completion date (newest first)
      completedStories.sort((a, b) => b.completedAt.compareTo(a.completedAt));
      
      debugPrint('StoryCacheService: Found ${completedStories.length} cached stories for character $characterId');
      return completedStories;
    } catch (e) {
      debugPrint('StoryCacheService: Failed to get cached stories: $e');
      return [];
    }
  }

  /// Update the list of cached stories for a character
  Future<void> _updateCachedStoryList(String characterId, String storyId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final listKey = '${_storyListKey}_$characterId';
      final storyIds = prefs.getStringList(listKey) ?? [];
      
      // Add story ID if not already present
      if (!storyIds.contains(storyId)) {
        storyIds.add(storyId);
        await prefs.setStringList(listKey, storyIds);
      }
    } catch (e) {
      debugPrint('StoryCacheService: Failed to update story list: $e');
    }
  }

  /// Extract the last outcome from completed segments
  String _extractLastOutcome(List<dynamic> segments) {
    if (segments.isEmpty) return 'unknown';
    
    final lastSegment = segments.last as Map<String, dynamic>;
    final outcome = lastSegment['Outcome'];
    
    if (outcome is String) {
      return outcome.toLowerCase();
    } else if (outcome is Map<String, dynamic>) {
      return (outcome['Type'] as String? ?? 'unknown').toLowerCase();
    }
    
    return 'unknown';
  }

  /// Clear all cached stories for a character (for cleanup/reset)
  Future<void> clearCachedStoriesForCharacter(String characterId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final listKey = '${_storyListKey}_$characterId';
      final storyIds = prefs.getStringList(listKey) ?? [];
      
      // Remove all individual story caches
      for (final storyId in storyIds) {
        final key = '$_keyPrefix${characterId}_$storyId';
        await prefs.remove(key);
      }
      
      // Clear the story list
      await prefs.remove(listKey);
      
      debugPrint('StoryCacheService: Cleared all cached stories for character $characterId');
    } catch (e) {
      debugPrint('StoryCacheService: Failed to clear cached stories: $e');
    }
  }

  /// Check if a story is cached
  Future<bool> isStoryCached({
    required String characterId,
    required String storyId,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final key = '$_keyPrefix${characterId}_$storyId';
      return prefs.containsKey(key);
    } catch (e) {
      debugPrint('StoryCacheService: Failed to check if story is cached: $e');
      return false;
    }
  }
}

/// Information about a completed story
class CompletedStoryInfo {
  final String storyId;
  final String storyTitle;
  final String storyDescription;
  final String storyType;
  final DateTime completedAt;
  final int segmentCount;
  final String lastOutcome;

  CompletedStoryInfo({
    required this.storyId,
    required this.storyTitle,
    required this.storyDescription,
    required this.storyType,
    required this.completedAt,
    required this.segmentCount,
    required this.lastOutcome,
  });

  /// Check if this story was completed successfully
  bool get wasSuccessful => 
      lastOutcome == 'success' || 
      lastOutcome == 'exceptional' || 
      lastOutcome == 'normal';

  /// Check if this story failed
  bool get wasFailed => 
      lastOutcome == 'failure' || 
      lastOutcome == 'death';

  /// Get a color representing the outcome
  String get outcomeColor {
    switch (lastOutcome) {
      case 'success':
      case 'exceptional':
        return 'purple';
      case 'normal':
        return 'green';
      case 'failure':
        return 'red';
      case 'death':
        return 'black';
      default:
        return 'grey';
    }
  }

  /// Format the completion time for display
  String formatCompletedAt() {
    final now = DateTime.now();
    final difference = now.difference(completedAt);
    
    if (difference.inDays == 0) {
      if (difference.inHours == 0) {
        return '${difference.inMinutes}m ago';
      }
      return '${difference.inHours}h ago';
    } else if (difference.inDays == 1) {
      return 'Yesterday';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}d ago';
    } else if (difference.inDays < 30) {
      return '${difference.inDays ~/ 7}w ago';
    } else {
      return '${completedAt.day}/${completedAt.month}/${completedAt.year}';
    }
  }
}