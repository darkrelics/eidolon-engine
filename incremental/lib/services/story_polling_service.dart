import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/character.dart';
import 'api_service.dart';

/// Server-authoritative polling service following documented pattern
/// 
/// This service implements the exact 4-step polling loop defined in the API documentation:
/// 1. Initial Wait: 60 seconds after story start
/// 2. Check Character State: GET /character 
/// 3. Get Server Timing: GET /segment/status
/// 4. Wait Server Time: Exact seconds from server response
class StoryPollingService {
  final ApiService _apiService;
  bool _isPolling = false;
  Timer? _pollTimer;
  
  // Callbacks for UI updates
  Function(Character?)? onCharacterUpdated;
  Function(String)? onPollingError;
  Function()? onStoryCompleted;
  
  StoryPollingService({required ApiService apiService}) 
      : _apiService = apiService;
  
  /// Start server-authoritative polling
  Future<void> startPolling(String characterId) async {
    if (_isPolling) return;
    _isPolling = true;
    
    debugPrint('StoryPollingService: Starting polling for character: $characterId');
    
    try {
      await _runPollingLoop(characterId);
    } finally {
      _isPolling = false;
    }
  }
  
  /// Stop polling and cleanup timers
  void stopPolling() {
    if (!_isPolling) return;
    
    debugPrint('StoryPollingService: Stopping polling');
    _isPolling = false;
    _pollTimer?.cancel();
    _pollTimer = null;
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
        
        if (character == null) {
          debugPrint('StoryPollingService: Character not found');
          onPollingError?.call('Character not found');
          break;
        }
        
        // Update UI with latest character data
        onCharacterUpdated?.call(character);
        
        // If no active segment, story is complete
        if (character.activeSegmentID == null) {
          debugPrint('StoryPollingService: Story completed - no active segment');
          onStoryCompleted?.call();
          break;
        }
        
        // Step 3: Get server timing for current segment
        final segmentStatus = await _apiService.getSegmentStatus(
          characterId: characterId
        );
        
        // Step 4: Wait server-specified time exactly
        final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;
        
        debugPrint('StoryPollingService: Server says wait $timeRemaining seconds');
        
        if (timeRemaining > 0 && _isPolling) {
          // Use Timer for precise timing control
          _pollTimer?.cancel();
          _pollTimer = Timer(Duration(seconds: timeRemaining), () {
            if (_isPolling) {
              // Continue polling loop after server-specified time
              _runPollingLoop(characterId);
            }
          });
          return; // Exit this iteration, timer will continue the loop
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
          onStoryCompleted?.call();
          break;
        }
        
        if (consecutiveErrors >= maxConsecutiveErrors) {
          debugPrint('StoryPollingService: Too many consecutive errors, stopping');
          onPollingError?.call('Connection failed after $maxConsecutiveErrors attempts');
          break;
        }
        
        // Wait 30 seconds before retry as documented
        if (_isPolling) {
          await Future.delayed(const Duration(seconds: 30));
        }
      }
    }
    
    debugPrint('StoryPollingService: Polling loop ended');
  }
  
  /// Check if currently polling
  bool get isPolling => _isPolling;
  
  /// Dispose of resources
  void dispose() {
    stopPolling();
  }
}