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

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class CharacterSelectionScreen extends StatefulWidget {
  const CharacterSelectionScreen({super.key});

  @override
  State<CharacterSelectionScreen> createState() => _CharacterSelectionScreenState();
}

class _CharacterSelectionScreenState extends State<CharacterSelectionScreen> {
  late ApiService _apiService;
  List<CharacterInfo>? _characters;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initializeApiService();
    _loadCharacters();
  }

  void _initializeApiService() {
    _apiService = ApiService(authService: AuthService.instance);
  }

  Future<void> _loadCharacters() async {
    try {
      setState(() {
        _isLoading = true;
        _error = null;
      });

      final characters = await _apiService.listCharacters();
      
      if (mounted) {
        setState(() {
          _characters = characters;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Select Character'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/account-settings');
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              final authProvider = Provider.of<AuthProvider>(context, listen: false);
              final navigator = Navigator.of(context);
              await authProvider.signOut();
              if (mounted) {
                navigator.pushReplacementNamed('/login');
              }
            },
          ),
        ],
      ),
      body: SafeArea(
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.error_outline,
                size: 64,
                color: colorScheme.error,
              ),
              const SizedBox(height: 16),
              Text(
                'Error loading characters',
                style: theme.textTheme.headlineSmall?.copyWith(
                  color: colorScheme.error,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _loadCharacters,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (_characters == null || _characters!.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.person_off,
                size: 64,
                color: colorScheme.onSurfaceVariant,
              ),
              const SizedBox(height: 16),
              Text(
                'No Characters Found',
                style: theme.textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                'Create your first character in the main game to begin your incremental adventure.',
                style: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Select a Character',
            style: theme.textTheme.headlineMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          Expanded(
            child: ListView.builder(
              itemCount: _characters!.length,
              itemBuilder: (context, index) {
                final character = _characters![index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: Icon(
                      character.dead ? Icons.person_off : Icons.person,
                      color: character.dead 
                          ? colorScheme.error 
                          : colorScheme.primary,
                    ),
                    title: Text(
                      character.name,
                      style: TextStyle(
                        decoration: character.dead 
                            ? TextDecoration.lineThrough 
                            : null,
                      ),
                    ),
                    subtitle: character.dead 
                        ? Text(
                            'Deceased',
                            style: TextStyle(color: colorScheme.error),
                          )
                        : Text(
                            'Active',
                            style: TextStyle(color: colorScheme.primary),
                          ),
                    trailing: const Icon(Icons.arrow_forward_ios),
                    enabled: !character.dead,
                    onTap: character.dead ? null : () {
                      Navigator.pushReplacementNamed(
                        context, 
                        '/game',
                        arguments: character.name,
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}