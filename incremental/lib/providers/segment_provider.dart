import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/active_segment.dart';
import '../services/api_service.dart';

/// Provider to manage segment state and handle mechanical segment processing
class SegmentProvider extends ChangeNotifier {
  final ApiService _apiService;
  
  ActiveSegment? _currentSegment;
  Timer? _pollingTimer;
  bool _isLoading = false;
  String? _error;
  
  SegmentProvider({required ApiService apiService}) : _apiService = apiService;
  
  ActiveSegment? get currentSegment => _currentSegment;
  bool get isLoading => _isLoading;
  String? get error => _error;
  
  /// Load current story and check if mechanical segment needs processing
  Future<void> loadCurrentStory(String characterId) async {
    try {
      _isLoading = true;
      _error = null;
      notifyListeners();
      
      // Use getCharacterById to get all data including story state
      final character = await _apiService.getCharacterById(characterId);
      
      if (character == null || character.storyState == null) {
        _currentSegment = null;
        _isLoading = false;
        notifyListeners();
        return;
      }
      
      // Extract active segment data from character's story state
      Map<String, dynamic>? segmentData;
      if (character.storyState!.containsKey('ActiveSegment')) {
        segmentData = character.storyState!['ActiveSegment'] as Map<String, dynamic>?;
      } else {
        // Fallback for old format where storyState is the segment itself
        segmentData = character.storyState;
      }
      
      if (segmentData == null) {
        _currentSegment = null;
        _isLoading = false;
        notifyListeners();
        return;
      }
      
      // Add story title from Story data if not present in segment
      if (!segmentData.containsKey('StoryTitle') && 
          character.storyState!.containsKey('Story')) {
        final storyData = character.storyState!['Story'] as Map<String, dynamic>?;
        if (storyData != null && storyData.containsKey('Title')) {
          segmentData['StoryTitle'] = storyData['Title'];
        }
      }
      
      _currentSegment = ActiveSegment.fromJson(segmentData);
      
      // Note: Polling is now handled by GameScreen to avoid conflicts
      // This provider is primarily for data access
      
      _isLoading = false;
      notifyListeners();
      
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }
  
  // Removed polling logic - now handled by GameScreen
  
  /// Fetch segment history for processed mechanical segments
  Future<void> _fetchSegmentHistory(String characterId) async {
    try {
      final history = await _apiService.getSegmentHistory(
        characterId: characterId,
      );
      
      if (history.isNotEmpty && _currentSegment != null) {
        // Find the matching segment in history
        final historySegment = history.firstWhere(
          (seg) => seg['ActiveSegmentID'] == _currentSegment!.activeSegmentID,
          orElse: () => <String, dynamic>{},
        );
        
        if (historySegment.isNotEmpty) {
          // Update current segment with history data
          final updatedData = _currentSegment!.toJson();
          updatedData['ClientEvents'] = historySegment['ClientEvents'];
          updatedData['CharacterUpdates'] = historySegment['CharacterUpdates'];
          updatedData['Outcome'] = historySegment['Outcome'];
          
          _currentSegment = ActiveSegment.fromJson(updatedData);
          notifyListeners();
        }
      }
    } catch (e) {
      debugPrint('Error fetching segment history: $e');
    }
  }
  
  /// Handle segment completion
  Future<void> completeSegment(String characterId) async {
    try {
      _isLoading = true;
      _error = null;
      notifyListeners();
      
      // Advance to next segment
      await loadCurrentStory(characterId);
      
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      
      // Retry once after a delay
      await Future.delayed(const Duration(seconds: 2));
      try {
        _error = null;
        await loadCurrentStory(characterId);
      } catch (retryError) {
        _error = 'Failed to advance segment: $retryError';
        notifyListeners();
      }
    }
  }
  
  /// Manually refresh the current segment
  Future<void> refresh(String characterId) async {
    _pollingTimer?.cancel();
    await loadCurrentStory(characterId);
  }
  
  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }
}

