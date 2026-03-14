import 'package:eidolon_incremental/models/active_segment.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/repositories/character_repository.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
  final CharacterRepository _repository;

  static const String _activeCharacterIdKey = 'active_character_id';

  CharacterProvider({required SharedPreferences prefs, required CharacterRepository repository})
    : _prefs = prefs,
      _repository = repository {
    // Load data asynchronously after construction to avoid blocking
    _loadFromStorage();
  }

  /// Load character from repository using saved ID.
  Future<void> _loadFromStorage() async {
    try {
      final characterId = _prefs.getString(_activeCharacterIdKey);

      if (characterId != null) {
        debugPrint('CharacterProvider: Loading active character ID: $characterId');
        try {
          final character = await _repository.getCharacter(characterId);
          if (character != null) {
            _character = character;
            debugPrint('CharacterProvider: Loaded character ${character.name}');
          } else {
            debugPrint('CharacterProvider: Character not found, clearing ID');
            await _prefs.remove(_activeCharacterIdKey);
          }
        } catch (e) {
          debugPrint('CharacterProvider: Error loading character: $e');
          // Don't clear ID on error, might be temporary network/db issue
        }
      } else {
        debugPrint('CharacterProvider: No active character ID found');
      }

      notifyListeners();
    } catch (e) {
      debugPrint('CharacterProvider: Critical error loading from storage: $e');
      notifyListeners();
    }
  }

  /// Update character state and persist ID.
  Future<void> updateCharacter(Character newCharacter) async {
    await executeAsyncVoid(() async {
      try {
        // Update in-memory state
        _character = newCharacter;

        // Persist ID so we know who to load next time
        await _prefs.setString(_activeCharacterIdKey, newCharacter.id);

        // Note: We don't need to persist the full object here because
        // CharacterRepository handles caching when we fetched/updated the character.
        // If this update came from somewhere else, we might want to ensure it's cached,
        // but typically updates come from the Repo or API anyway.

        debugPrint('CharacterProvider: Updated character and saved ID');
        notifyListeners();
      } catch (e) {
        debugPrint('CharacterProvider: Failed to update character: $e');
        throw Exception('Failed to update character');
      }
    }, showLoading: false);
  }

  /// Set active segment (in-memory only).
  /// Segment persistence is handled by the server/repository state.
  void setActiveSegment(ActiveSegment segment) {
    _activeSegment = segment;
    notifyListeners();
  }

  /// Clear active segment.
  void clearActiveSegment() {
    _activeSegment = null;
    notifyListeners();
  }

  /// Create new character (called after server creates it)
  Future<void> createCharacter(Character newCharacter) async {
    await updateCharacter(newCharacter);
  }

  /// Clear all character data.
  Future<void> clearCharacter() async {
    await executeAsyncVoid(() async {
      try {
        await _prefs.remove(_activeCharacterIdKey);
      } catch (e) {
        debugPrint('CharacterProvider: Failed to clear character ID: $e');
      }

      _character = null;
      _activeSegment = null;

      debugPrint('CharacterProvider: Character cleared');
      notifyListeners();
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
