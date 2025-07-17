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
  final String name;
  final bool dead;

  Character({required this.name, required this.dead});

  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      name: json['name'] as String,
      dead: json['dead'] as bool? ?? false,
    );
  }
}

class ApiService {
  static const String _apiDomain = String.fromEnvironment('API_DOMAIN', defaultValue: 'api.darkrelics.net');
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
      final characterList = (data['characters'] as List)
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
}