import 'package:flutter/foundation.dart';
import '../models/character.dart';
import '../utils/api_parser.dart';
import '../utils/api_validation.dart';
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
    try {
      final json = await get<Map<String, dynamic>>(
        '/character',
        queryParams: {'CharacterID': characterId},
      );

      final characterData = json['Character'] as Map<String, dynamic>;

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

  /// List all characters for the player.
  ///
  /// Returns a list of all characters owned by the authenticated player.
  /// Returns an empty list if no characters exist.
  Future<List<CharacterInfo>> listCharacters() async {
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
    try {
      final json = await post<Map<String, dynamic>>(
        '/story/start',
        body: {'CharacterID': characterId, 'StoryID': storyId},
      );
      return json['Segment'] as Map<String, dynamic>;
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
  /// Initiates a rest period for the character to recover health.
  Future<Map<String, dynamic>> rest(String characterId) async {
    debugPrint('ApiService: Initiating rest for character: $characterId');

    final json = await post<Map<String, dynamic>>(
      '/segment/rest',
      body: {'CharacterID': characterId},
    );

    debugPrint('ApiService: Rest initiated successfully');
    return json;
  }

  /// Get available archetypes.
  ///
  /// Fetches all archetypes available for character creation
  /// from the server's DynamoDB storage.
  Future<List<ArchetypeInfo>> getArchetypes() async {
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
      name: json['ArchetypeName'] as String,
      description: json['Description'] as String? ?? '',
      attributes: Map<String, dynamic>.from(json['Attributes'] ?? {}),
      skills: Map<String, dynamic>.from(json['Skills'] ?? {}),
      health: json['Health'] as int? ?? 10,
      essence: json['Essence'] as int? ?? 3,
    );
  }
}
