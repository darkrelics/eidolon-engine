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
      
      // Get current story
      final storyData = await _apiService.getCurrentStory(
        characterId: characterId,
      );
      
      if (storyData == null) {
        _currentSegment = null;
        _isLoading = false;
        notifyListeners();
        return;
      }
      
      // Extract active segment data
      final segmentData = storyData['ActiveSegment'] as Map<String, dynamic>?;
      if (segmentData == null) {
        _currentSegment = null;
        _isLoading = false;
        notifyListeners();
        return;
      }
      
      _currentSegment = ActiveSegment.fromJson(segmentData);
      
      // For mechanical segments, check if already processed
      if (_currentSegment!.segmentType == 'mechanical' && 
          _currentSegment!.processingStatus != 'processed') {
        // Start polling for processing completion
        _startPollingForProcessing(characterId);
      } else if (_currentSegment!.segmentType == 'mechanical' &&
                 _currentSegment!.processingStatus == 'processed' &&
                 _currentSegment!.clientEvents == null) {
        // If processed but no events, fetch from history
        await _fetchSegmentHistory(characterId);
      }
      
      _isLoading = false;
      notifyListeners();
      
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }
  
  /// Start polling for mechanical segment processing completion
  void _startPollingForProcessing(String characterId) {
    _pollingTimer?.cancel();
    
    // Poll every 2 seconds for processed status
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      try {
        // Check segment status
        final statusData = await _apiService.getSegmentStatus(
          characterId: characterId,
        );
        
        final processingStatus = statusData['processingStatus'] as String?;
        
        if (processingStatus == 'processed') {
          timer.cancel();
          
          // Fetch the updated segment with results
          await loadCurrentStory(characterId);
        }
      } catch (e) {
        debugPrint('Polling error: $e');
      }
    });
  }
  
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
      notifyListeners();
      
      // Advance to next segment
      await loadCurrentStory(characterId);
      
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }
  
  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }
}

