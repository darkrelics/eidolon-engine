import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/character.dart';
import '../models/segment_outcome.dart';
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
  Future<String> addCharacter({
    required String name,
    required String archetype,
  }) async {
    debugPrint(
      'ApiService: Adding character - name: $name, archetype: $archetype',
    );
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/characters'),
      headers: headers,
      body: jsonEncode({'characterName': name, 'archetypeName': archetype}),
    );

    debugPrint(
      'ApiService: Add character response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Add character response body: ${response.body}');

    if (response.statusCode != 200 && response.statusCode != 201) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['error'] ?? 'Failed to add character');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['characterId'] as String;
  }

  /// Delete a character
  Future<void> deleteCharacter(String characterId) async {
    debugPrint('ApiService: Deleting character - id: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.delete(
      Uri.parse('$baseUrl/character?characterId=$characterId'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Delete character response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Delete character response body: ${response.body}');

    if (response.statusCode != 200) {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(errorBody['error'] ?? 'Failed to delete character');
    }
  }

  /// Get character by ID
  Future<Character?> getCharacterById(String characterId) async {
    debugPrint('ApiService: Getting character by ID: $characterId');
    final headers = await _getHeaders();
    final uri = Uri.parse('$baseUrl/character?characterId=$characterId');
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
      throw Exception('Failed to get character: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return Character.fromJson(json['character'] as Map<String, dynamic>);
  }

  /// List all characters for the player
  Future<List<CharacterInfo>> listCharacters() async {
    debugPrint('ApiService: Calling listCharacters...');
    debugPrint('ApiService: API URL: $baseUrl/characters');

    final headers = await _getHeaders();
    debugPrint('ApiService: Headers prepared, making request...');

    final response = await _httpClient.get(
      Uri.parse('$baseUrl/characters'),
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
      throw Exception('Failed to list characters: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final characterList = (json['characters'] as List)
        .map((char) => CharacterInfo.fromJson(char as Map<String, dynamic>))
        .toList();

    debugPrint(
      'ApiService: Successfully parsed ${characterList.length} characters',
    );
    return characterList;
  }

  /// Start a story segment
  Future<ActiveSegment> startSegment({
    required String storyId,
    required String segmentId,
  }) async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/segment/start'),
      headers: headers,
      body: jsonEncode({'storyId': storyId, 'segmentId': segmentId}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to start segment: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return ActiveSegment.fromJson(json['segment'] as Map<String, dynamic>);
  }

  /// Conclude a story segment
  Future<SegmentOutcome> concludeSegment({required String segmentId}) async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/segment/conclude'),
      headers: headers,
      body: jsonEncode({'segmentId': segmentId}),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to conclude segment: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return SegmentOutcome.fromJson(json['outcome'] as Map<String, dynamic>);
  }

  /// Abandon current story run
  Future<Character> abandonStory() async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/story/abandon'),
      headers: headers,
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to abandon story: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return Character.fromJson(json['character'] as Map<String, dynamic>);
  }

  /// Rest instead of continuing
  Future<Character> rest() async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/character/rest'),
      headers: headers,
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to rest: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return Character.fromJson(json['character'] as Map<String, dynamic>);
  }

  /// Get available stories for a character
  Future<List<StoryMetadata>> getStories(String characterId) async {
    debugPrint('ApiService: Getting stories for character: $characterId');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/stories?characterId=$characterId'),
      headers: headers,
    );

    debugPrint('ApiService: Get stories response status: ${response.statusCode}');
    debugPrint('ApiService: Get stories response body: ${response.body}');

    if (response.statusCode != 200) {
      throw Exception('Failed to get stories: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final stories = json['stories'] as List<dynamic>;
    return stories
        .map((s) => StoryMetadata.fromJson(s as Map<String, dynamic>))
        .toList();
  }

  /// Get available archetypes
  Future<List<ArchetypeInfo>> getArchetypes() async {
    debugPrint('ApiService: Getting archetypes...');
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/archetypes'),
      headers: headers,
    );

    debugPrint(
      'ApiService: Get archetypes response status: ${response.statusCode}',
    );
    debugPrint('ApiService: Get archetypes response body: ${response.body}');

    if (response.statusCode != 200) {
      throw Exception('Failed to get archetypes: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final archetypes = (json['archetypes'] as List)
        .map((a) => ArchetypeInfo.fromJson(a as Map<String, dynamic>))
        .toList();

    return archetypes;
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

/// Story metadata for browsing
class StoryMetadata {
  final String storyId;
  final String title;
  final String description;
  final String type;
  final bool available;
  final int cooldownRemaining;
  final int estimatedDuration;

  StoryMetadata({
    required this.storyId,
    required this.title,
    required this.description,
    required this.type,
    required this.available,
    required this.cooldownRemaining,
    required this.estimatedDuration,
  });

  factory StoryMetadata.fromJson(Map<String, dynamic> json) {
    return StoryMetadata(
      storyId: json['storyId'] as String,
      title: json['title'] as String,
      description: json['description'] as String,
      type: json['type'] as String,
      available: json['available'] as bool,
      cooldownRemaining: json['cooldownRemaining'] as int,
      estimatedDuration: json['estimatedDuration'] as int,
    );
  }
}
