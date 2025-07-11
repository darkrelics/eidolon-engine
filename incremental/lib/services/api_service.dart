import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/character.dart';
import '../models/segment_outcome.dart';
import 'auth_service.dart';

/// Character info for listing
class CharacterInfo {
  final String name;
  final bool dead;

  CharacterInfo({required this.name, required this.dead});

  factory CharacterInfo.fromJson(Map<String, dynamic> json) {
    return CharacterInfo(
      name: json['name'] as String,
      dead: json['dead'] as bool? ?? false,
    );
  }
}

/// Service for calling Lambda functions through API Gateway
class ApiService {
  final AuthService _authService;
  final http.Client _httpClient;
  static const String _apiDomain = String.fromEnvironment('API_DOMAIN', defaultValue: 'darkrelics.net');
  static const String _defaultBaseUrl = 'https://api.$_apiDomain';
  final String baseUrl;

  ApiService({
    required AuthService authService,
    String? baseUrl,
    http.Client? httpClient,
  })  : _authService = authService,
        _httpClient = httpClient ?? http.Client(),
        baseUrl = baseUrl ?? _defaultBaseUrl;

  /// Get authorization headers
  Future<Map<String, String>> _getHeaders() async {
    final token = await _authService.getIdToken();
    if (token == null) {
      throw Exception('Not authenticated');
    }

    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  /// Create a new character
  Future<Character> createCharacter({
    required String name,
    required String archetypeId,
  }) async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/character/create'),
      headers: headers,
      body: jsonEncode({
        'name': name,
        'archetypeId': archetypeId,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to create character: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return Character.fromJson(json['character'] as Map<String, dynamic>);
  }

  /// Get current character
  Future<Character?> getCharacter() async {
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/character'),
      headers: headers,
    );

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
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/characters'),
      headers: headers,
    );

    if (response.statusCode == 404) {
      return [];
    }

    if (response.statusCode != 200) {
      throw Exception('Failed to list characters: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final characterList = (json['characters'] as List)
        .map((char) => CharacterInfo.fromJson(char as Map<String, dynamic>))
        .toList();
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
      body: jsonEncode({
        'storyId': storyId,
        'segmentId': segmentId,
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to start segment: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return ActiveSegment.fromJson(json['segment'] as Map<String, dynamic>);
  }

  /// Conclude a story segment
  Future<SegmentOutcome> concludeSegment({
    required String segmentId,
  }) async {
    final headers = await _getHeaders();
    final response = await _httpClient.post(
      Uri.parse('$baseUrl/segment/conclude'),
      headers: headers,
      body: jsonEncode({
        'segmentId': segmentId,
      }),
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

  /// Get available stories
  Future<List<StoryMetadata>> getStories() async {
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/stories'),
      headers: headers,
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to get stories: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    final stories = json['stories'] as List<dynamic>;
    return stories
        .map((s) => StoryMetadata.fromJson(s as Map<String, dynamic>))
        .toList();
  }
}

/// Story metadata for browsing
class StoryMetadata {
  final String id;
  final String name;
  final String description;
  final String author;
  final List<String> tags;
  final int estimatedDuration;
  final int minLevel;

  StoryMetadata({
    required this.id,
    required this.name,
    required this.description,
    required this.author,
    required this.tags,
    required this.estimatedDuration,
    required this.minLevel,
  });

  factory StoryMetadata.fromJson(Map<String, dynamic> json) {
    return StoryMetadata(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String,
      author: json['author'] as String? ?? 'Unknown',
      tags: List<String>.from(json['tags'] ?? []),
      estimatedDuration: json['estimatedDuration'] as int? ?? 0,
      minLevel: json['minLevel'] as int? ?? 0,
    );
  }
}