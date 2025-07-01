import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../models/character.dart';
import '../models/segment_outcome.dart';

/// Provider for character state management
/// All progression happens server-side, this only manages display state
class CharacterProvider extends ChangeNotifier {
  Character? _character;
  ActiveSegment? _activeSegment;
  bool _isLoading = false;
  String? _error;

  Character? get character => _character;
  ActiveSegment? get activeSegment => _activeSegment;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get hasCharacter => _character != null;

  final SharedPreferences _prefs;
  static const String _characterKey = 'current_character';
  static const String _activeSegmentKey = 'active_segment';

  CharacterProvider({required SharedPreferences prefs}) : _prefs = prefs {
    _loadFromStorage();
  }

  /// Load character from local storage
  Future<void> _loadFromStorage() async {
    try {
      final characterJson = _prefs.getString(_characterKey);
      if (characterJson != null) {
        _character = Character.fromJson(jsonDecode(characterJson));
      }

      final segmentJson = _prefs.getString(_activeSegmentKey);
      if (segmentJson != null) {
        _activeSegment = ActiveSegment.fromJson(jsonDecode(segmentJson));
        
        // Clear expired segments
        if (_activeSegment!.isExpired) {
          _activeSegment = null;
          await _prefs.remove(_activeSegmentKey);
        }
      }
      
      notifyListeners();
    } catch (e) {
      debugPrint('Failed to load character from storage: $e');
    }
  }

  /// Update character from server response
  Future<void> updateCharacter(Character newCharacter) async {
    _character = newCharacter;
    _error = null;
    
    // Save to storage
    await _prefs.setString(_characterKey, jsonEncode(newCharacter.toJson()));
    
    notifyListeners();
  }

  /// Set active segment when starting
  Future<void> setActiveSegment(ActiveSegment segment) async {
    _activeSegment = segment;
    _error = null;
    
    // Save to storage
    await _prefs.setString(_activeSegmentKey, jsonEncode(segment));
    
    notifyListeners();
  }

  /// Clear active segment when completed
  Future<void> clearActiveSegment() async {
    _activeSegment = null;
    await _prefs.remove(_activeSegmentKey);
    notifyListeners();
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

  /// Clear all character data
  Future<void> clearCharacter() async {
    _character = null;
    _activeSegment = null;
    _error = null;
    
    await _prefs.remove(_characterKey);
    await _prefs.remove(_activeSegmentKey);
    
    notifyListeners();
  }

  /// Set loading state
  void setLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
  }

  /// Set error state
  void setError(String? error) {
    _error = error;
    _isLoading = false;
    notifyListeners();
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