import 'package:flutter/foundation.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/services/api_metrics.dart';
import 'package:eidolon_incremental/utils/api_parser.dart';
import 'package:eidolon_incremental/utils/api_validation.dart';
import 'package:eidolon_incremental/utils/json_parser.dart';
import 'base_api_service.dart';

/// Character info for listing
class CharacterInfo {
  final String name;
  final String id;
  final bool dead;

  CharacterInfo({required this.name, required this.id, required this.dead});

  factory CharacterInfo.fromJson(Map<String, dynamic> json) {
    return CharacterInfo(
      name: json['CharacterName'] as String,
      id: json['CharacterID'] as String? ?? '',
      dead: json['Dead'] as bool? ?? false,
    );
  }
}

/// Service for calling Lambda functions through API Gateway.
///
/// This service extends BaseApiService to inherit common HTTP functionality
/// while providing game-specific API methods. All HTTP operations (GET, POST, etc.)
/// are handled by the base class, ensuring consistent error handling, retries,
/// and authentication across all API calls.
///
/// The API_DOMAIN environment variable can be set at build time to override
/// the default API endpoint for different environments.
class ApiService extends BaseApiService {
  static const String _apiDomain = String.fromEnvironment(
    'API_DOMAIN',
    defaultValue: 'api.darkrelics.net',
  );
  static const String _defaultBaseUrl = 'https://$_apiDomain';

  ApiService({required super.authService, String? baseUrl, super.httpClient})
    : super(baseUrl: baseUrl ?? _defaultBaseUrl);

  /// Add a new character.
  ///
  /// Creates a new character with the specified name and archetype.
  /// Returns the created character data from the server.
  Future<Map<String, dynamic>> addCharacter({
    required String name,
    required String archetype,
  }) async {
    ApiMetrics.recordCall('POST /character', details: 'name=$name, archetype=$archetype');

    // Use base class post method for consistent error handling
    return post<Map<String, dynamic>>(
      '/character',
      body: {'CharacterName': name, 'ArchetypeName': archetype},
    );
  }

  /// Delete a character.
  ///
  /// Permanently deletes the specified character and all associated data.
  Future<Map<String, dynamic>> deleteCharacter(String characterId) async {
    ApiMetrics.recordCall('DELETE /character', details: 'id=$characterId');

    // Use base class delete method with query parameters
    return delete<Map<String, dynamic>>(
      '/character',
      queryParams: {'CharacterID': characterId},
    );
  }

  /// Get character by ID.
  ///
  /// Fetches the complete character data including active story and segment.
  /// Returns null if the character doesn't exist.
  Future<Character?> getCharacterById(String characterId) async {
    ApiMetrics.recordCall('GET /character', details: 'id=$characterId');

    try {
      final json = await get<Map<String, dynamic>>(
        '/character',
        queryParams: {'CharacterID': characterId},
      );

      final characterData = json['Character'] as Map<String, dynamic>?;
      if (characterData == null) {
        throw FormatException('Missing Character data in API response');
      }

      // ActiveStoryID and ActiveSegmentID are already in characterData from the server

      // Check if there's an active story and segment
      final activeStory = json['ActiveStory'] as Map<String, dynamic>?;
      final activeSegment = json['ActiveSegment'] as Map<String, dynamic>?;
      final availableStories = json['AvailableStories'] as List<dynamic>?;

      // Build story state with both story and segment data
      if (activeStory != null && activeSegment != null) {
        characterData['StoryState'] = {
          'Story': activeStory,
          'ActiveSegment': activeSegment,
        };
      } else if (activeSegment != null) {
        // Fallback for backward compatibility
        characterData['StoryState'] = activeSegment;
      }

      // If no active story but available stories are provided, add them to character data
      if (availableStories != null && activeStory == null) {
        characterData['AvailableStoriesDetails'] = availableStories;
      }

      return Character.fromJson(characterData);
    } catch (e) {
      if (e is NotFoundException) {
        return null;
      }
      rethrow;
    }
  }

  /// Get raw character response including ActiveStory and ActiveSegment.
  ///
  /// Returns the complete API response with Character, ActiveStory, and ActiveSegment fields.
  /// Used by polling service to get authoritative character state after story completion.
  Future<Map<String, dynamic>> getCharacter({required String characterId}) async {
    ApiMetrics.recordCall('GET /character (raw)', details: 'id=$characterId');

    return await get<Map<String, dynamic>>(
      '/character',
      queryParams: {'CharacterID': characterId},
    );
  }

  /// List all characters for the player.
  ///
  /// Returns a list of all characters owned by the authenticated player.
  /// Returns an empty list if no characters exist.
  Future<List<CharacterInfo>> listCharacters() async {
    ApiMetrics.recordCall('GET /character/list');

    try {
      final json = await get<Map<String, dynamic>>('/character/list');

      // Use new parser with validation
      final charactersData = ApiParser.parseCharactersList(json);
      final characterList = charactersData
          .map((char) => CharacterInfo.fromJson(char))
          .toList();

      return characterList;
    } catch (e) {
      if (e is NotFoundException) {
        throw ApiException(
          'Player account not found. Please sign out and back in.',
          statusCode: 404,
        );
      }
      if (e is ValidationException) {
        debugPrint('ApiService: Validation error - $e');
        throw Exception('Invalid response format: ${e.message}');
      }
      rethrow;
    }
  }

  /// Start a story for a character.
  ///
  /// Begins a new story run for the specified character.
  /// Returns the initial segment of the story.
  ///
  /// Throws specific exceptions for:
  /// - 403: Story not available (prerequisites not met)
  /// - 409: Character already in a story or game mode
  Future<Map<String, dynamic>> startStory({
    required String characterId,
    required String storyId,
  }) async {
    ApiMetrics.recordCall('POST /story/start', details: 'story=$storyId');

    try {
      final json = await post<Map<String, dynamic>>(
        '/story/start',
        body: {'CharacterID': characterId, 'StoryID': storyId},
      );
      final segment = json['Segment'] as Map<String, dynamic>?;
      if (segment == null) {
        throw FormatException('Missing Segment data in API response');
      }
      return segment;
    } catch (e) {
      if (e is ApiException) {
        if (e.statusCode == 403) {
          throw Exception('Story not available');
        }
        if (e.statusCode == 409) {
          throw Exception('Character is already in a story or game mode');
        }
        debugPrint('ApiService: Start story error - ${e.message}');
      }
      rethrow;
    }
  }

  /// Submit a decision for a story segment.
  ///
  /// Submits the player's choice for a decision segment.
  /// Returns the updated segment state.
  Future<Map<String, dynamic>> submitDecision({
    required String characterId,
    required String decision,
  }) async {
    ApiMetrics.recordCall('POST /segment/decision', details: 'choice=$decision');

    debugPrint(
      'ApiService: Submitting decision - characterId: $characterId, decision: $decision',
    );

    try {
      final json = await post<Map<String, dynamic>>(
        '/segment/decision',
        body: {'CharacterID': characterId, 'Decision': decision},
      );

      debugPrint('ApiService: Decision submitted successfully');
      return json;
    } catch (e) {
      if (e is ApiException) {
        if (e.statusCode == 403) {
          throw Exception('Access denied');
        }
        if (e.statusCode == 404) {
          throw Exception('Segment not found');
        }
        if (e.statusCode == 409) {
          throw Exception('Decision already submitted');
        }
      }
      rethrow;
    }
  }

  /// Get segment outcome for a completed segment.
  ///
  /// Fetches the results of a completed segment including
  /// rewards, XP gained, and character updates.

  /// Abandon current story run.
  ///
  /// Ends the current story run early, allowing the character
  /// to start a new story.
  Future<Map<String, dynamic>> abandonStory(String characterId) async {
    ApiMetrics.recordCall('POST /story/abandon', details: 'id=$characterId');

    debugPrint('ApiService: Abandoning story for character: $characterId');

    final json = await post<Map<String, dynamic>>(
      '/story/abandon',
      body: {'CharacterID': characterId},
    );

    debugPrint('ApiService: Story abandoned successfully');
    return json;
  }

  /// Rest instead of continuing.
  ///

  /// Get available archetypes.
  ///
  /// Fetches all archetypes available for character creation
  /// from the server's DynamoDB storage.
  Future<List<ArchetypeInfo>> getArchetypes() async {
    ApiMetrics.recordCall('GET /archetype');

    debugPrint('ApiService: Getting archetypes...');

    final json = await get<Map<String, dynamic>>('/archetype');

    final archetypes = (json['Archetypes'] as List<dynamic>)
        .map((a) => ArchetypeInfo.fromJson(a as Map<String, dynamic>))
        .toList();

    debugPrint('ApiService: Retrieved ${archetypes.length} archetypes');
    return archetypes;
  }

  /// Get segment history.
  ///
  /// Fetches the history of completed segments for the character's
  /// current story run.
  Future<List<Map<String, dynamic>>> getSegmentHistory({
    required String characterId,
  }) async {
    ApiMetrics.recordCall('GET /segment/history', details: 'id=$characterId');

    debugPrint(
      'ApiService: Getting segment history for character: $characterId',
    );

    final json = await get<Map<String, dynamic>>(
      '/segment/history',
      queryParams: {'CharacterID': characterId},
    );

    final segments = json['Segments'] as List<dynamic>?;
    final result =
        segments?.map((s) => s as Map<String, dynamic>).toList() ?? [];

    debugPrint(
      'ApiService: Retrieved ${result.length} segment history entries',
    );
    return result;
  }

  /// Get segment status.
  ///
  /// Fetches the current status of the character's active segment.
  Future<Map<String, dynamic>> getSegmentStatus({
    required String characterId,
  }) async {
    ApiMetrics.recordCall('GET /segment/status', details: 'id=$characterId');

    debugPrint(
      'ApiService: Getting segment status for character: $characterId',
    );

    try {
      final json = await get<Map<String, dynamic>>(
        '/segment/status',
        queryParams: {'CharacterID': characterId},
      );

      debugPrint('ApiService: Segment status retrieved successfully');
      return json;
    } catch (e) {
      if (e is NotFoundException) {
        throw Exception('No active segment found');
      }
      rethrow;
    }
  }

  /// Get item brief (ItemID, PrototypeID, Quantity only).
  ///
  /// Fetches lightweight item data for IndexedDB caching.
  /// Returns item brief data.
  Future<Map<String, dynamic>> getItemBrief(String itemId) async {
    ApiMetrics.recordCall('GET /item/brief', details: 'itemId=$itemId');

    return get<Map<String, dynamic>>(
      '/item/brief',
      queryParams: {'ItemID': itemId},
    );
  }

  /// Get full item prototype definition.
  ///
  /// Fetches complete prototype data including all properties and stats.
  /// Prototypes are immutable and safe to cache indefinitely.
  /// Returns full prototype data.
  Future<Map<String, dynamic>> getItemPrototype(String prototypeId) async {
    ApiMetrics.recordCall('GET /item/prototype', details: 'prototypeId=$prototypeId');

    return get<Map<String, dynamic>>(
      '/item/prototype',
      queryParams: {'PrototypeID': prototypeId},
    );
  }

  /// Consume an inventory item.
  ///
  /// Uses a consumable item and applies its effects server-side.
  /// Returns effect summary and remaining quantity.
  Future<Map<String, dynamic>> consumeItem({
    required String characterId,
    required String itemId,
  }) async {
    ApiMetrics.recordCall('POST /item/consume', details: 'characterId=$characterId, itemId=$itemId');

    return post<Map<String, dynamic>>(
      '/item/consume',
      body: {'CharacterID': characterId, 'ItemID': itemId},
    );
  }

  /// Discard an inventory item.
  ///
  /// Removes an item from inventory. For stackable items, can discard
  /// a partial quantity. Returns discard results.
  ///
  /// Parameters:
  /// - [characterId]: Character UUID
  /// - [itemId]: Item UUID to discard
  /// - [slot]: Optional inventory slot for faster lookup
  /// - [quantity]: Optional quantity to discard (for stackable items).
  ///   If null or >= stack quantity, discards entire item.
  Future<Map<String, dynamic>> discardItem({
    required String characterId,
    required String itemId,
    String? slot,
    int? quantity,
  }) async {
    ApiMetrics.recordCall(
      'POST /item/discard',
      details: 'characterId=$characterId, itemId=$itemId, slot=$slot, qty=$quantity',
    );

    final body = <String, dynamic>{
      'CharacterID': characterId,
      'ItemID': itemId,
    };
    if (slot != null) {
      body['InventorySlot'] = slot;
    }
    if (quantity != null) {
      body['Quantity'] = quantity;
    }

    return post<Map<String, dynamic>>('/item/discard', body: body);
  }

  /// Consolidate stackable item stacks.
  ///
  /// Merges multiple stacks of the same item type into fewer stacks,
  /// respecting MaxStack limits.
  ///
  /// Parameters:
  /// - [characterId]: Character UUID
  /// - [prototypeId]: Optional - consolidate only stacks of this item type
  /// - [consolidateAll]: If true, consolidates all stackable items (default)
  Future<Map<String, dynamic>> consolidateStacks({
    required String characterId,
    String? prototypeId,
    bool consolidateAll = true,
  }) async {
    ApiMetrics.recordCall(
      'POST /item/consolidate',
      details: 'characterId=$characterId, prototypeId=$prototypeId, all=$consolidateAll',
    );

    final body = <String, dynamic>{
      'CharacterID': characterId,
      'ConsolidateAll': consolidateAll,
    };
    if (prototypeId != null) {
      body['PrototypeID'] = prototypeId;
    }

    return post<Map<String, dynamic>>('/item/consolidate', body: body);
  }

  /// Split a stackable item into two stacks.
  ///
  /// Creates a new stack with the specified quantity from an existing stack.
  ///
  /// Parameters:
  /// - [characterId]: Character UUID
  /// - [slot]: Inventory slot containing the stack to split
  /// - [quantity]: Number of items to split into the new stack
  Future<Map<String, dynamic>> splitStack({
    required String characterId,
    required String slot,
    required int quantity,
  }) async {
    ApiMetrics.recordCall(
      'POST /item/split',
      details: 'characterId=$characterId, slot=$slot, qty=$quantity',
    );

    return post<Map<String, dynamic>>(
      '/item/split',
      body: {
        'CharacterID': characterId,
        'Slot': slot,
        'Quantity': quantity,
      },
    );
  }
}

/// Archetype info for character creation
class ArchetypeInfo {
  final String name;
  final String description;
  final Map<String, dynamic> attributes;
  final Map<String, dynamic> skills;
  final int health;
  final int essence;

  ArchetypeInfo({
    required this.name,
    required this.description,
    required this.attributes,
    required this.skills,
    required this.health,
    required this.essence,
  });

  factory ArchetypeInfo.fromJson(Map<String, dynamic> json) {
    return ArchetypeInfo(
      name: JsonParser.getString(json, 'ArchetypeName'),
      description: JsonParser.getString(json, 'Description'),
      attributes: JsonParser.getMap(json, 'Attributes'),
      skills: JsonParser.getMap(json, 'Skills'),
      health: JsonParser.getInt(json, 'Health', defaultValue: 10),
      essence: JsonParser.getInt(json, 'Essence', defaultValue: 3),
    );
  }
}
