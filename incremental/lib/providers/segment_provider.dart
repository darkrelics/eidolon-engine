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
    
    int retryCount = 0;
    const maxRetries = 5;
    const maxPollingDuration = Duration(minutes: 5);
    final startTime = DateTime.now();
    
    // Poll every 2 seconds for processed status
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      try {
        // Check if we've exceeded max polling duration
        if (DateTime.now().difference(startTime) > maxPollingDuration) {
          timer.cancel();
          _error = 'Processing timeout - please refresh';
          notifyListeners();
          return;
        }
        
        // Check segment status
        final statusData = await _apiService.getSegmentStatus(
          characterId: characterId,
        );
        
        final isComplete = statusData['IsComplete'] as bool? ?? false;
        
        if (isComplete) {
          timer.cancel();
          retryCount = 0; // Reset retry count on success
          
          // Fetch the updated segment with full results
          await loadCurrentStory(characterId);
        }
      } catch (e) {
        debugPrint('Polling error: $e');
        retryCount++;
        
        // If we've had too many consecutive errors, stop polling
        if (retryCount >= maxRetries) {
          timer.cancel();
          _error = 'Connection error - please check your network and refresh';
          notifyListeners();
        }
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

