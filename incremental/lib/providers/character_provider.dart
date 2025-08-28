import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../models/character.dart';
import '../models/active_segment.dart';
import '../models/segment_outcome.dart';
import 'base_provider.dart';

/// Provider for character state management
/// All progression happens server-side, this only manages display state
class CharacterProvider extends BaseProvider {
  Character? _character;
  ActiveSegment? _activeSegment;

  Character? get character => _character;
  ActiveSegment? get activeSegment => _activeSegment;
  bool get hasCharacter => _character != null;

  final SharedPreferences _prefs;
  static const String _characterKey = 'current_character';
  static const String _activeSegmentKey = 'active_segment';

  CharacterProvider({required SharedPreferences prefs}) : _prefs = prefs {
    // Load data asynchronously after construction to avoid blocking
    // This prevents the constructor from hanging if storage is slow
    _loadFromStorage();
  }

  /// Load character from local storage with improved error recovery.
  /// 
  /// This method attempts to recover from corrupted data by:
  /// 1. Clearing corrupted character data and continuing
  /// 2. Clearing corrupted segment data and continuing
  /// 3. Always notifying listeners even if loading fails
  /// 
  /// This ensures the app remains functional even if local storage is corrupted.
  Future<void> _loadFromStorage() async {
    bool dataCleared = false;
    
    try {
      // Attempt to load character data
      final characterJson = _prefs.getString(_characterKey);
      if (characterJson != null) {
        try {
          _character = Character.fromJson(jsonDecode(characterJson));
        } catch (characterError) {
          // Character data is corrupted - clear it and continue
          debugPrint('Corrupted character data detected, clearing: $characterError');
          await _prefs.remove(_characterKey);
          _character = null;
          dataCleared = true;
        }
      }

      // Attempt to load segment data independently
      final segmentJson = _prefs.getString(_activeSegmentKey);
      if (segmentJson != null) {
        try {
          _activeSegment = ActiveSegment.fromJson(jsonDecode(segmentJson));

          // Clear expired segments
          if (_activeSegment!.isExpired) {
            _activeSegment = null;
            await _prefs.remove(_activeSegmentKey);
          }
        } catch (segmentError) {
          // Segment data is corrupted - clear it and continue
          debugPrint('Corrupted segment data detected, clearing: $segmentError');
          await _prefs.remove(_activeSegmentKey);
          _activeSegment = null;
          dataCleared = true;
        }
      }

      // Always notify listeners, even if some data failed to load
      notifyListeners();
      
      // Log if we had to clear corrupted data
      if (dataCleared) {
        debugPrint('Some corrupted data was cleared. App will continue normally.');
      }
    } catch (e) {
      // Catastrophic error - log it but ensure app continues
      debugPrint('Critical error loading from storage: $e');
      // Clear all data to ensure clean state
      _character = null;
      _activeSegment = null;
      // Still notify listeners so UI can update
      notifyListeners();
    }
  }

  /// Update character from server response with proper error handling.
  /// 
  /// This method follows the "persist first, then update state" pattern to prevent
  /// data loss if persistence fails. The state is only updated after successful
  /// persistence to storage, preventing race conditions where the UI shows data
  /// that isn't actually saved.
  Future<void> updateCharacter(Character newCharacter) async {
    await executeAsyncVoid(() async {
      try {
        // CRITICAL: Persist to storage FIRST before updating in-memory state
        // This ensures data is safely stored before UI reflects the change
        await _prefs.setString(_characterKey, jsonEncode(newCharacter.toJson()));
        
        // Only update in-memory state after successful persistence
        _character = newCharacter;
        
        debugPrint('Character successfully updated and persisted');
      } catch (e) {
        // If persistence fails, don't update state - keep old data
        debugPrint('Failed to persist character update: $e');
        // Re-throw to let executeAsyncVoid handle the error properly
        throw Exception('Failed to save character data');
      }
    }, showLoading: false);
  }

  /// Set active segment when starting with proper error handling.
  /// 
  /// Uses the same "persist first" pattern to ensure data integrity.
  /// If storage fails, the segment won't be set in memory, preventing
  /// the UI from showing an unsaved segment.
  Future<void> setActiveSegment(ActiveSegment segment) async {
    await executeAsyncVoid(() async {
      try {
        // CRITICAL: Persist to storage FIRST
        await _prefs.setString(_activeSegmentKey, jsonEncode(segment));
        
        // Only update in-memory state after successful persistence
        _activeSegment = segment;
        
        debugPrint('Active segment successfully set and persisted');
      } catch (e) {
        // If persistence fails, don't update state
        debugPrint('Failed to persist active segment: $e');
        throw Exception('Failed to save segment data');
      }
    }, showLoading: false);
  }

  /// Clear active segment when completed with proper error handling.
  /// 
  /// Clears storage first, then memory. If storage clearing fails,
  /// we still clear memory to prevent showing stale data, but log
  /// the error for debugging.
  Future<void> clearActiveSegment() async {
    await executeAsyncVoid(() async {
      try {
        // Try to remove from storage first
        await _prefs.remove(_activeSegmentKey);
      } catch (e) {
        // Log but don't fail - we still want to clear from memory
        debugPrint('Warning: Failed to remove segment from storage: $e');
      }
      
      // Always clear from memory to prevent showing stale data
      _activeSegment = null;
      
      debugPrint('Active segment cleared');
    }, showLoading: false);
  }

  /// Apply outcome from server
  Future<void> applySegmentOutcome(SegmentOutcome outcome) async {
    // Update character with server-calculated values
    await updateCharacter(outcome.updatedCharacter);

    // Clear the active segment
    await clearActiveSegment();
  }

  /// Create new character (called after server creates it)
  Future<void> createCharacter(Character newCharacter) async {
    await updateCharacter(newCharacter);
  }

  /// Clear all character data with proper error handling.
  /// 
  /// This method clears both storage and memory. Storage operations are
  /// attempted first, but memory is always cleared regardless of storage
  /// success to ensure the UI doesn't show stale data.
  Future<void> clearCharacter() async {
    await executeAsyncVoid(() async {
      // Track any storage errors for logging
      bool storageError = false;
      
      try {
        // Attempt to clear from storage first
        await Future.wait([
          _prefs.remove(_characterKey),
          _prefs.remove(_activeSegmentKey),
        ]);
      } catch (e) {
        // Log storage errors but continue - we still want to clear memory
        debugPrint('Warning: Failed to clear some data from storage: $e');
        storageError = true;
      }
      
      // ALWAYS clear from memory to ensure UI shows correct state
      // This prevents the app from showing stale data even if storage fails
      _character = null;
      _activeSegment = null;
      
      if (storageError) {
        debugPrint('Character data cleared from memory (storage had errors)');
      } else {
        debugPrint('Character data successfully cleared from storage and memory');
      }
    }, showLoading: false);
  }

  /// Get display-friendly skill score
  String getSkillDisplay(String skill) {
    if (_character == null) return '0.0';
    final value = _character!.skills[skill] ?? 0.0;
    return value.toStringAsFixed(1);
  }

  /// Get display-friendly attribute score
  String getAttributeDisplay(String attribute) {
    if (_character == null) return '0.0';
    final value = _character!.attributes[attribute] ?? 0.0;
    return value.toStringAsFixed(1);
  }

  /// Get effective score for display
  int getEffectiveScore(String skill, String attribute) {
    if (_character == null) return 0;
    return _character!.getEffectiveScore(skill, attribute);
  }

  /// Check if character meets resource requirements
  bool meetsRequirements(Map<String, int> requirements) {
    if (_character == null) return false;

    for (final entry in requirements.entries) {
      final current = _character!.resources[entry.key] ?? 0;
      if (current < entry.value) return false;
    }

    return true;
  }
}
