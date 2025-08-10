import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/character.dart';
import '../utils/api_parser.dart';
import '../utils/api_validation.dart';
import 'auth_service.dart';

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

/// Service for calling Lambda functions through API Gateway
class ApiService {
  final AuthService _authService;
  final http.Client _httpClient;
  static const String _apiDomain = String.fromEnvironment(
    'API_DOMAIN',
    defaultValue: 'api.darkrelics.net',
  );
  static const String _defaultBaseUrl = 'https://$_apiDomain';
  final String baseUrl;

  ApiService({
    required AuthService authService,
    String? baseUrl,
    http.Client? httpClient,
  }) : _authService = authService,
       _httpClient = httpClient ?? http.Client(),
       baseUrl = baseUrl ?? _defaultBaseUrl;

  /// Get authorization headers
  Future<Map<String, String>> _getHeaders() async {
    debugPrint('ApiService: Getting ID token...');
    final token = await _authService.getIdToken();
    if (token == null) {
      debugPrint('ApiService: ERROR - No ID token available');
      throw Exception('Not authenticated');
    }

    debugPrint('ApiService: Got ID token, length: ${token.length}');
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  /// Add a new character
  Future<Map<String, dynamic>> addCharacter({
    required String name,
    required String archetype,
  }) async {
    debugPrint(
      'ApiService: Adding character - name: $name, archetype: $archetype',
    );
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/character'),
      headers: headers,
      body: jsonEncode({'CharacterName': name, 'ArchetypeName': archetype}),
    );

    debugPrint(
      'ApiService: Add character response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Add character response body: ${response.body}');

    if (response.statusCode != 200 && response.statusCode != 201) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to add character');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }

  /// Delete a character
  Future<Map<String, dynamic>> deleteCharacter(String characterId) async {
    debugPrint('ApiService: Deleting character - id: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.delete(
      Uri.parse('$baseUrl/character?CharacterID=$characterId'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Delete character response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Delete character response body: ${response.body}');

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to delete character');
    }
    
    // Return the response data
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }

  /// Get character by ID
  Future<Character?> getCharacterById(String characterId) async {
    debugPrint('ApiService: Getting character by ID: $characterId');
    final headers = await _getHeaders();
    final uri = Uri.parse('$baseUrl/character?CharacterID=$characterId');
    debugPrint('ApiService: Request URI: $uri');

    final response = await _httpClient.get(uri, headers: headers);

    debugPrint(
      'ApiService: Get character response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Get character response body: ${response.body}');

    if (response.statusCode == 404) {
      return null;
    }

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to get character');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final characterData = json['Character'] as Map<String, dynamic>;
    
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
      debugPrint('ApiService: Found active story: ${activeStory['Title']}');
      debugPrint('ApiService: Found active segment: ${activeSegment['SegmentType']}');
    } else if (activeSegment != null) {
      // Fallback for backward compatibility
      characterData['StoryState'] = activeSegment;
      debugPrint('ApiService: Found active segment (no story): ${activeSegment['SegmentType']}');
    }
    
    // If no active story but available stories are provided, add them to character data
    if (availableStories != null && activeStory == null) {
      characterData['AvailableStoriesDetails'] = availableStories;
      debugPrint('ApiService: Found ${availableStories.length} available stories from character response');
    }
    
    return Character.fromJson(characterData);
  }

  /// List all characters for the player
  Future<List<CharacterInfo>> listCharacters() async {
    debugPrint('ApiService: Calling listCharacters...');
    debugPrint('ApiService: API URL: $baseUrl/character/list');

    final headers = await _getHeaders();
    debugPrint('ApiService: Headers prepared, making request...');

    final response = await _httpClient.get(
      Uri.parse('$baseUrl/character/list'),
      headers: headers,
    );

    debugPrint('ApiService: Response status: ${response.statusCode}');
    debugPrint('ApiService: Response body: ${response.body}');

    if (response.statusCode == 404) {
      debugPrint('ApiService: No characters found (404)');
      return [];
    }

    if (response.statusCode != 200) {
      debugPrint('ApiService: ERROR - Failed to list characters');
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to list characters');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    
    try {
      // Use new parser with validation
      final charactersData = ApiParser.parseCharactersList(json);
      final characterList = charactersData
          .map((char) => CharacterInfo.fromJson(char))
          .toList();

      debugPrint(
        'ApiService: Successfully parsed ${characterList.length} characters',
      );
      return characterList;
    } catch (e) {
      debugPrint('ApiService: Validation error - $e');
      if (e is ValidationException) {
        throw Exception('Invalid response format: ${e.message}');
      }
      rethrow;
    }
  }

  /// Start a story for a character
  Future<Map<String, dynamic>> startStory({
    required String characterId,
    required String storyId,
  }) async {
    debugPrint('ApiService: Starting story - characterId: $characterId, storyId: $storyId');
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/story/start'),
      headers: headers,
      body: jsonEncode({'CharacterID': characterId, 'StoryID': storyId}),
    );

    debugPrint('ApiService: Start story response status: ${response.statusCode}');
    debugPrint('ApiService: Start story response body: ${response.body}');

    if (response.statusCode == 403) {
      throw Exception('Story not available');
    }
    
    if (response.statusCode == 409) {
      throw Exception('Character is already in a story or game mode');
    }

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to start story');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['Segment'] as Map<String, dynamic>;
  }

  /// Submit a decision for a story segment
  Future<Map<String, dynamic>> submitDecision({
    required String characterId,
    required String decision,
  }) async {
    debugPrint('ApiService: Submitting decision - characterId: $characterId, decision: $decision');
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/segment/decision'),
      headers: headers,
      body: jsonEncode({'CharacterID': characterId, 'Decision': decision}),
    );

    debugPrint('ApiService: Submit decision response status: ${response.statusCode}');
    debugPrint('ApiService: Submit decision response body: ${response.body}');

    if (response.statusCode == 404) {
      throw Exception('Segment not found');
    }

    if (response.statusCode == 409) {
      throw Exception('Decision already submitted');
    }

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to submit decision');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }

  /// Get segment outcome for a completed segment
  Future<Map<String, dynamic>> getSegmentOutcome({
    required String characterId,
    required String segmentId,
  }) async {
    debugPrint('ApiService: Getting segment outcome - characterId: $characterId, segmentId: $segmentId');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/segment/outcome?CharacterID=$characterId&SegmentID=$segmentId'),
      headers: headers,
    );

    debugPrint('ApiService: Get segment outcome response status: ${response.statusCode}');
    debugPrint('ApiService: Get segment outcome response body: ${response.body}');

    if (response.statusCode == 404) {
      throw Exception('Segment not found');
    }

    if (response.statusCode == 409) {
      throw Exception('Segment not yet completed');
    }

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to get segment outcome');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }

  /// Abandon current story run
  Future<Map<String, dynamic>> abandonStory(String characterId) async {
    debugPrint('ApiService: Abandoning story for character: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/story/abandon?CharacterID=$characterId'),
      headers: headers,
    );

    debugPrint('ApiService: Abandon story response status: ${response.statusCode}');
    debugPrint('ApiService: Abandon story response body: ${response.body}');

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['error'] ?? 'Failed to abandon story');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }

  /// Rest instead of continuing
  Future<Map<String, dynamic>> rest(String characterId) async {
    debugPrint('ApiService: Initiating rest for character: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/segment/rest'),
      headers: headers,
      body: jsonEncode({'CharacterID': characterId}),
    );

    debugPrint('ApiService: Rest response status: ${response.statusCode}');
    debugPrint('ApiService: Rest response body: ${response.body}');

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to rest');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
  }


  /// Get available archetypes
  Future<List<ArchetypeInfo>> getArchetypes() async {
    debugPrint('ApiService: Getting archetypes...');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/archetype'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Get archetypes response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Get archetypes response body: ${response.body}');

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to get archetypes');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final archetypes = (json['Archetypes'] as List<dynamic>)
        .map((a) => ArchetypeInfo.fromJson(a as Map<String, dynamic>))
        .toList();

    return archetypes;
  }

  /// Get segment history Lambda
  Future<List<Map<String, dynamic>>> getSegmentHistory({
    required String characterId,
  }) async {
    debugPrint('ApiService: Getting segment history for character: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/segment/history?CharacterID=$characterId'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Get segment history response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Get segment history response body: ${response.body}');

    if (response.statusCode == 404) {
      return [];
    }

    if (response.statusCode != 200) {
      throw Exception('Failed to get segment history: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final segments = json['Segments'] as List<dynamic>?;
    return segments
        ?.map((s) => s as Map<String, dynamic>)
        .toList() ?? [];
  }

  /// Get segment status
  Future<Map<String, dynamic>> getSegmentStatus({
    required String characterId,
  }) async {
    debugPrint('ApiService: Getting segment status for character: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/segment/status?CharacterID=$characterId'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Get segment status response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Get segment status response body: ${response.body}');

    if (response.statusCode == 404) {
      throw Exception('No active segment found');
    }

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['Error'] ?? errorBody['error'] ?? 'Failed to get segment status');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json;
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

