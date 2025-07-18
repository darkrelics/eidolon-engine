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
  State<CharacterSelectionScreen> createState() =>
      _CharacterSelectionScreenState();
}

class _CharacterSelectionScreenState extends State<CharacterSelectionScreen> {
  late ApiService _apiService;
  List<CharacterInfo>? _characters;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    debugPrint('CharacterSelectionScreen: initState called');
    _initializeApiService();
    _loadCharacters();
  }

  void _initializeApiService() {
    _apiService = ApiService(authService: AuthService.instance);
  }

  Future<void> _loadCharacters() async {
    try {
      debugPrint('CharacterSelectionScreen: Loading characters...');
      setState(() {
        _isLoading = true;
        _error = null;
      });

      final characters = await _apiService.listCharacters();
      debugPrint(
        'CharacterSelectionScreen: Loaded ${characters.length} characters',
      );

      if (mounted) {
        setState(() {
          _characters = characters;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('CharacterSelectionScreen: ERROR loading characters: $e');
      debugPrint('CharacterSelectionScreen: Error type: ${e.runtimeType}');
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
            icon: const Icon(Icons.add),
            onPressed: _showAddCharacterDialog,
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/account-settings');
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              final authProvider = Provider.of<AuthProvider>(
                context,
                listen: false,
              );
              final navigator = Navigator.of(context);
              await authProvider.signOut();
              if (mounted) {
                navigator.pushReplacementNamed('/login');
              }
            },
          ),
        ],
      ),
      body: SafeArea(child: _buildBody()),
    );
  }

  Future<void> _showAddCharacterDialog() async {
    // First load archetypes
    List<ArchetypeInfo> archetypes = [];
    try {
      archetypes = await _apiService.getArchetypes();
    } catch (e) {
      debugPrint('Error loading archetypes: $e');
      // Continue with empty archetypes - the server will use defaults
    }

    if (!mounted) return;

    final nameController = TextEditingController();
    String? selectedArchetype = archetypes.isNotEmpty ? archetypes.first.name : null;

    await showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create New Character'),
        content: StatefulBuilder(
          builder: (context, setDialogState) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: nameController,
                decoration: const InputDecoration(
                  labelText: 'Character Name',
                  hintText: 'Enter character name',
                ),
                textCapitalization: TextCapitalization.words,
              ),
              if (archetypes.isNotEmpty) ...[
                const SizedBox(height: 16),
                const Text('Archetype:'),
                const SizedBox(height: 8),
                DropdownButton<String>(
                  isExpanded: true,
                  value: selectedArchetype,
                  items: archetypes.map((archetype) {
                    return DropdownMenuItem(
                      value: archetype.name,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(archetype.name),
                          if (archetype.description.isNotEmpty)
                            Text(
                              archetype.description,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                        ],
                      ),
                    );
                  }).toList(),
                  onChanged: (value) {
                    setDialogState(() {
                      selectedArchetype = value;
                    });
                  },
                ),
              ] else ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.info_outline,
                        size: 20,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'No archetypes available. Default stats will be used.',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                final name = nameController.text.trim();
                if (name.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Please enter a character name')),
                  );
                  return;
                }
                
                Navigator.of(context).pop();
                debugPrint('Creating character with name: $name, archetype: ${selectedArchetype ?? 'default'}');
                await _createCharacter(name, selectedArchetype ?? '');
              },
              child: const Text('Create'),
            ),
          ],
      ),
    );
  }

  Future<void> _createCharacter(String name, String archetype) async {
    try {
      debugPrint('CharacterSelectionScreen: _createCharacter called with name: $name, archetype: $archetype');
      
      setState(() {
        _isLoading = true;
      });

      debugPrint('CharacterSelectionScreen: Calling API to add character...');
      final characterId = await _apiService.addCharacter(name: name, archetype: archetype);
      debugPrint('CharacterSelectionScreen: Character created with ID: $characterId');
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Created character: $name')),
        );
      }

      // Reload characters
      debugPrint('CharacterSelectionScreen: Reloading characters...');
      await _loadCharacters();
    } catch (e, stackTrace) {
      debugPrint('CharacterSelectionScreen: Error creating character: $e');
      debugPrint('CharacterSelectionScreen: Stack trace: $stackTrace');
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to create character: ${e.toString()}'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Future<void> _showDeleteCharacterDialog(CharacterInfo character) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Character'),
        content: Text('Are you sure you want to delete "${character.name}"? This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed ?? false) {
      await _deleteCharacter(character);
    }
  }

  Future<void> _deleteCharacter(CharacterInfo character) async {
    try {
      setState(() {
        _isLoading = true;
      });

      await _apiService.deleteCharacter(character.id);
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Deleted character: ${character.name}')),
        );
      }

      // Reload characters
      await _loadCharacters();
    } catch (e) {
      debugPrint('Error deleting character: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to delete character: $e'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
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
              Icon(Icons.error_outline, size: 64, color: colorScheme.error),
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
                style: TextStyle(color: colorScheme.onSurfaceVariant),
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
              Text('No Characters Found', style: theme.textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text(
                'Create your first character to begin your incremental adventure.',
                style: TextStyle(color: colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _showAddCharacterDialog,
                icon: const Icon(Icons.add),
                label: const Text('Create Character'),
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
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.delete),
                          onPressed: () => _showDeleteCharacterDialog(character),
                        ),
                        const Icon(Icons.arrow_forward_ios),
                      ],
                    ),
                    enabled: !character.dead,
                    onTap: character.dead
                        ? null
                        : () {
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
