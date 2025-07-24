// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';

class Character {
  final String id;
  final String name;
  final bool dead;
  final Map<String, dynamic>? attributes;
  final Map<String, dynamic>? skills;
  final int? health;
  final int? maxHealth;

  Character({
    required this.id,
    required this.name,
    required this.dead,
    this.attributes,
    this.skills,
    this.health,
    this.maxHealth,
  });

  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      id: json['CharacterID'] as String? ?? '',
      name: json['CharacterName'] as String? ?? '',
      dead: json['Dead'] as bool? ?? false,
      attributes: json['Attributes'] as Map<String, dynamic>?,
      skills: json['Skills'] as Map<String, dynamic>?,
      health: json['Health'] as int?,
      maxHealth: json['MaxHealth'] as int?,
    );
  }
}

class ApiService {
  static const String _apiDomain = String.fromEnvironment(
    'API_DOMAIN',
    defaultValue: 'api.darkrelics.net',
  );
  static const String _baseUrl = 'https://$_apiDomain';

  final AuthService _authService;

  ApiService(this._authService);

  Future<List<Character>> getCharacters() async {
    final session = _authService.session;
    if (session == null) {
      throw Exception('User not authenticated');
    }

    final idToken = session.getIdToken().getJwtToken();
    if (idToken == null || idToken.isEmpty) {
      throw Exception('No ID token available');
    }

    final response = await http.get(
      Uri.parse('$_baseUrl/characters'),
      headers: {
        'Authorization': 'Bearer $idToken',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final characterList =
          (data['characters'] as List)
              .map((char) => Character.fromJson(char as Map<String, dynamic>))
              .toList();
      return characterList;
    } else if (response.statusCode == 401) {
      throw Exception('Unauthorized');
    } else if (response.statusCode == 404) {
      return [];
    } else {
      throw Exception('Failed to load characters: ${response.statusCode}');
    }
  }

  Future<Character> getCharacter(String characterId) async {
    final session = _authService.session;
    if (session == null) {
      throw Exception('User not authenticated');
    }

    final idToken = session.getIdToken().getJwtToken();
    if (idToken == null || idToken.isEmpty) {
      throw Exception('No ID token available');
    }

    final response = await http.get(
      Uri.parse('$_baseUrl/character?characterId=$characterId'),
      headers: {
        'Authorization': 'Bearer $idToken',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 200) {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final characterData = data['character'] as Map<String, dynamic>;
      return Character.fromJson(characterData);
    } else if (response.statusCode == 401) {
      throw Exception('Unauthorized');
    } else if (response.statusCode == 404) {
      throw Exception('Character not found');
    } else {
      throw Exception('Failed to load character: ${response.statusCode}');
    }
  }

  Future<void> deleteCharacter(String characterId) async {
    final session = _authService.session;
    if (session == null) {
      throw Exception('User not authenticated');
    }

    final idToken = session.getIdToken().getJwtToken();
    if (idToken == null || idToken.isEmpty) {
      throw Exception('No ID token available');
    }

    final response = await http.delete(
      Uri.parse('$_baseUrl/character?characterId=$characterId'),
      headers: {
        'Authorization': 'Bearer $idToken',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode != 200) {
      if (response.statusCode == 401) {
        throw Exception('Unauthorized');
      } else if (response.statusCode == 404) {
        throw Exception('Character not found');
      } else {
        throw Exception('Failed to delete character: ${response.statusCode}');
      }
    }
  }
}
