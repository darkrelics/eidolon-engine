import 'package:flutter/foundation.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/indexeddb_service.dart';

/// Repository for managing character data with intelligent caching.
///
/// Implements a cache-first strategy to minimize server calls while maintaining
/// data consistency. The server remains authoritative for all calculations,
/// state transitions, and game mechanics. This repository manages the flow
/// between local IndexedDB cache and server API.
///
/// Caching Strategy:
/// - Fetch from server at character selection (all player's characters)
/// - Fetch from server after story completion (refresh character state)
/// - Apply incremental updates from segment responses to local cache
/// - Fall back to server if cache unavailable or corrupted
class CharacterRepository {
  final ApiService _apiService;
  final IndexedDBService _indexedDB;

  CharacterRepository({
    required ApiService apiService,
    IndexedDBService? indexedDBService,
  })  : _apiService = apiService,
        _indexedDB = indexedDBService ?? IndexedDBService();

  /// Load all characters for a player from server and cache them.
  ///
  /// This is called when entering the character selection screen.
  /// Fetches fresh data from server and caches all characters in IndexedDB.
  ///
  /// Returns list of character info for selection screen.
  Future<List<CharacterInfo>> loadPlayerCharacters() async {
    debugPrint('CharacterRepository: Loading player characters from server');

    try {
      // Fetch from server
      final characterInfoList = await _apiService.listCharacters();

      debugPrint('CharacterRepository: Loaded ${characterInfoList.length} characters');

      // For each character in the list, fetch full details and cache
      // This ensures the cache is populated when user selects a character
      for (final info in characterInfoList) {
        try {
          final character = await _apiService.getCharacterById(info.id);
          if (character != null) {
            await _cacheCharacter(character);
          }
        } catch (e) {
          // Don't fail entire load if one character fails
          debugPrint('CharacterRepository: Failed to cache character ${info.id}: $e');
        }
      }

      return characterInfoList;
    } catch (e) {
      debugPrint('CharacterRepository: Error loading characters: $e');
      rethrow;
    }
  }

  /// Get character by ID using cache-first strategy.
  ///
  /// Checks IndexedDB first. If found and not stale, returns cached data.
  /// Otherwise, fetches from server and updates cache.
  ///
  /// Returns null if character doesn't exist.
  Future<Character?> getCharacter(String characterId) async {
    debugPrint('CharacterRepository: Getting character $characterId');

    // Try cache first if IndexedDB is available
    if (_indexedDB.isSupported) {
      try {
        final cachedData = await _indexedDB.getCharacter(characterId);
        if (cachedData != null) {
          debugPrint('CharacterRepository: Character $characterId found in cache');
          return Character.fromJson(cachedData);
        }
      } catch (e) {
        debugPrint('CharacterRepository: Cache read failed, falling back to server: $e');
      }
    }

    // Cache miss or unavailable - fetch from server
    debugPrint('CharacterRepository: Fetching character $characterId from server');
    try {
      final character = await _apiService.getCharacterById(characterId);
      if (character != null) {
        await _cacheCharacter(character);
      }
      return character;
    } catch (e) {
      debugPrint('CharacterRepository: Error fetching character: $e');
      rethrow;
    }
  }

  /// Refresh character from server and update cache.
  ///
  /// Forces a server fetch regardless of cache state.
  /// Used after story completion to ensure cache is synchronized.
  Future<Character?> refreshCharacterFromServer(String characterId) async {
    debugPrint('CharacterRepository: Refreshing character $characterId from server');

    try {
      final character = await _apiService.getCharacterById(characterId);
      if (character != null) {
        await _cacheCharacter(character);
        debugPrint('CharacterRepository: Character $characterId refreshed and cached');
      }
      return character;
    } catch (e) {
      debugPrint('CharacterRepository: Error refreshing character: $e');
      rethrow;
    }
  }

  /// Apply incremental updates from segment response to cached character.
  ///
  /// This is the core of the caching strategy. Instead of fetching the entire
  /// character record, we apply only the changes from the segment response
  /// to the locally cached character.
  ///
  /// Updates include:
  /// - Health and Essence changes
  /// - Skill XP gains
  /// - Attribute XP gains
  /// - Wounds added or healed
  /// - Inventory changes
  /// - Resource modifications
  ///
  /// Returns the updated character.
  Future<Character?> updateCharacterFromSegment(
    String characterId,
    Map<String, dynamic> segmentUpdates,
  ) async {
    debugPrint('CharacterRepository: Applying segment updates to character $characterId');

    try {
      // Get current cached character
      final cachedData = _indexedDB.isSupported ? await _indexedDB.getCharacter(characterId) : null;

      if (cachedData == null) {
        debugPrint('CharacterRepository: No cached character found, fetching from server');
        return await getCharacter(characterId);
      }

      // Parse current character
      final character = Character.fromJson(cachedData);

      // Extract character updates from segment response
      final characterUpdates = segmentUpdates['CharacterUpdates'] as Map<String, dynamic>?;

      if (characterUpdates == null || characterUpdates.isEmpty) {
        debugPrint('CharacterRepository: No character updates in segment response');
        return character;
      }

      // Apply updates to create new character state
      final updatedCharacter = _applyUpdates(character, characterUpdates);

      // Cache the updated character
      await _cacheCharacter(updatedCharacter);

      debugPrint('CharacterRepository: Segment updates applied successfully');
      return updatedCharacter;
    } catch (e) {
      debugPrint('CharacterRepository: Error applying segment updates: $e');
      // On error, try to fetch fresh from server
      return await getCharacter(characterId);
    }
  }

  /// Apply character updates to create new character instance.
  ///
  /// This is a pure function that takes the current character and updates,
  /// and returns a new character instance with the changes applied.
  Character _applyUpdates(Character character, Map<String, dynamic> updates) {
    // Health updates
    final health = updates['Health'] != null ? (updates['Health'] as num).toDouble() : character.health;

    // Essence updates
    final essence = updates['Essence'] != null ? (updates['Essence'] as num).toDouble() : character.essence;

    // Skill XP updates
    final skillUpdates = updates['Skills'] as Map<String, dynamic>?;
    final updatedSkills = Map<String, double>.from(character.skills);
    if (skillUpdates != null) {
      skillUpdates.forEach((key, value) {
        if (value is num) {
          // Add XP to existing skill value (or initialize if new skill)
          updatedSkills[key] = (updatedSkills[key] ?? 0.0) + value.toDouble();
        }
      });
    }

    // Attribute XP updates
    final attributeUpdates = updates['Attributes'] as Map<String, dynamic>?;
    final updatedAttributes = Map<String, double>.from(character.attributes);
    if (attributeUpdates != null) {
      attributeUpdates.forEach((key, value) {
        if (value is num) {
          // Add XP to existing attribute value
          updatedAttributes[key] = (updatedAttributes[key] ?? 0.0) + value.toDouble();
        }
      });
    }

    // Resource updates
    final resourceUpdates = updates['Resources'] as Map<String, dynamic>?;
    final updatedResources = Map<String, int>.from(character.resources);
    if (resourceUpdates != null) {
      resourceUpdates.forEach((key, value) {
        if (value is num) {
          // Add to existing resource value (or initialize if new)
          updatedResources[key] = (updatedResources[key] ?? 0) + value.round();
        }
      });
    }

    // Inventory updates (if provided)
    final inventoryUpdates = updates['Inventory'] as Map<String, dynamic>?;
    final updatedInventory = inventoryUpdates != null
        ? Map<String, dynamic>.from(inventoryUpdates)
        : character.inventory;

    // Inventory details updates (if provided)
    final inventoryDetailsUpdates = updates['InventoryDetails'] as Map<String, dynamic>?;
    final updatedInventoryDetails = inventoryDetailsUpdates != null
        ? Map<String, dynamic>.from(inventoryDetailsUpdates)
        : character.inventoryDetails;

    // Wounds updates
    final woundsUpdate = updates['Wounds'] as List<dynamic>?;
    final updatedWounds = woundsUpdate != null
        ? woundsUpdate.map((w) => w as Map<String, dynamic>).toList()
        : character.wounds;

    // Progress updates
    final progressUpdates = updates['Progress'] as Map<String, dynamic>?;
    final updatedProgress = progressUpdates != null
        ? {...character.progress, ...progressUpdates}
        : character.progress;

    // Create updated character using copyWith
    return character.copyWith(
      health: health,
      essence: essence,
      skills: updatedSkills,
      attributes: updatedAttributes,
      resources: updatedResources,
      inventory: updatedInventory,
      inventoryDetails: updatedInventoryDetails,
      wounds: updatedWounds,
      progress: updatedProgress,
      lastUpdated: DateTime.now(),
    );
  }

  /// Cache a character in IndexedDB.
  ///
  /// Converts the Character model to `Map<String, dynamic>` for storage.
  /// Silently fails if IndexedDB is unavailable (falls back to server-only mode).
  Future<void> _cacheCharacter(Character character) async {
    if (!_indexedDB.isSupported) {
      return;
    }

    try {
      final characterData = character.toJson();
      await _indexedDB.putCharacter(characterData);
      debugPrint('CharacterRepository: Cached character ${character.id}');
    } catch (e) {
      debugPrint('CharacterRepository: Failed to cache character: $e');
      // Don't throw - caching is best-effort
    }
  }

  /// Delete character from cache.
  ///
  /// Used when a character is deleted from the server.
  Future<void> deleteCharacterFromCache(String characterId) async {
    if (!_indexedDB.isSupported) {
      return;
    }

    try {
      await _indexedDB.deleteCharacter(characterId);
      debugPrint('CharacterRepository: Deleted character $characterId from cache');
    } catch (e) {
      debugPrint('CharacterRepository: Failed to delete character from cache: $e');
      // Don't throw - cache deletion is best-effort
    }
  }

  /// Get all cached characters for a player.
  ///
  /// Used for offline access or quick loading.
  /// Returns empty list if IndexedDB unavailable or error occurs.
  Future<List<Character>> getCachedPlayerCharacters(String playerId) async {
    if (!_indexedDB.isSupported) {
      return [];
    }

    try {
      final cachedData = await _indexedDB.getPlayerCharacters(playerId);
      return cachedData.map((data) => Character.fromJson(data)).toList();
    } catch (e) {
      debugPrint('CharacterRepository: Failed to get cached characters: $e');
      return [];
    }
  }

  /// Clear all cached character data.
  ///
  /// Used for testing or when forcing a complete refresh.
  Future<void> clearCache() async {
    if (!_indexedDB.isSupported) {
      return;
    }

    try {
      await _indexedDB.clearAll();
      debugPrint('CharacterRepository: Cache cleared');
    } catch (e) {
      debugPrint('CharacterRepository: Failed to clear cache: $e');
    }
  }
}
