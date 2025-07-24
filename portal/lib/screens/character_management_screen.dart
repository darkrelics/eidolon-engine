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
import '../utils/auth_state.dart';
import '../widgets/ui_components.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class CharacterManagementScreen extends StatefulWidget {
  const CharacterManagementScreen({super.key});

  @override
  State<CharacterManagementScreen> createState() =>
      _CharacterManagementScreenState();
}

class _CharacterManagementScreenState extends State<CharacterManagementScreen> {
  late ApiService _apiService;
  List<Character>? _characters;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadCharacters();
  }

  Future<void> _loadCharacters() async {
    try {
      final authService = Provider.of<AuthService>(context, listen: false);
      _apiService = ApiService(authService);

      setState(() {
        _isLoading = true;
        _error = null;
      });

      final characters = await _apiService.getCharacters();

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

  Future<void> _viewCharacter(Character character) async {
    try {
      final fullCharacter = await _apiService.getCharacter(character.id);

      if (!mounted) return;

      await showDialog(
        context: context,
        builder:
            (context) => AlertDialog(
              title: Text(fullCharacter.name),
              content: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      fullCharacter.dead
                          ? 'Status: Deceased'
                          : 'Status: Active',
                      style: TextStyle(
                        color:
                            fullCharacter.dead
                                ? Theme.of(context).colorScheme.error
                                : Theme.of(context).colorScheme.primary,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),
                    if (fullCharacter.health != null &&
                        fullCharacter.maxHealth != null)
                      Text(
                        'Health: ${fullCharacter.health}/${fullCharacter.maxHealth}',
                      ),
                    const SizedBox(height: 8),
                    if (fullCharacter.attributes != null) ...[
                      const Text(
                        'Attributes:',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                      ...fullCharacter.attributes!.entries.map(
                        (e) => Text('  ${e.key}: ${e.value}'),
                      ),
                    ],
                    const SizedBox(height: 8),
                    if (fullCharacter.skills != null) ...[
                      const Text(
                        'Skills:',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                      ...fullCharacter.skills!.entries.map(
                        (e) => Text('  ${e.key}: ${e.value}'),
                      ),
                    ],
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('CLOSE'),
                ),
              ],
            ),
      );
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error loading character: ${e.toString()}'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  Future<void> _deleteCharacter(Character character) async {
    await CustomDialog.show(
      context,
      title: 'Delete Character',
      content:
          'Are you sure you want to delete ${character.name}? This action cannot be undone.',
      confirmText: 'DELETE',
      cancelText: 'CANCEL',
      onConfirm: () async {
        Navigator.of(context).pop();

        try {
          await _apiService.deleteCharacter(character.id);
          await _loadCharacters();

          if (!mounted) return;

          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Character deleted successfully')),
          );
        } catch (e) {
          if (!mounted) return;

          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Error deleting character: ${e.toString()}'),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
      isDestructive: true,
    );
  }

  void _playStory(Character character) {
    // TODO: Navigate to story gameplay screen
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Story gameplay coming soon!')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = Provider.of<AuthState>(context);
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    // Double-check authentication on build
    if (!authState.isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.of(context).pushReplacementNamed('/login');
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Character Management'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.of(context).pushNamed('/account-settings');
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              // Show confirmation dialog
              await CustomDialog.show(
                context,
                title: 'Sign Out',
                content: 'Are you sure you want to sign out?',
                confirmText: 'SIGN OUT',
                cancelText: 'CANCEL',
                onConfirm: () async {
                  Navigator.of(context).pop();
                  await authState.signOut();
                  if (context.mounted) {
                    Navigator.of(context).pushReplacementNamed('/');
                  }
                },
                isDestructive: true,
              );
            },
          ),
        ],
      ),
      body: BackgroundContainer(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Welcome, Adventurer',
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                if (_isLoading)
                  const Center(child: CircularProgressIndicator())
                else if (_error != null)
                  Card(
                    color: colorScheme.error.withValues(alpha: 0.1),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: [
                          Text(
                            'Error loading characters',
                            style: TextStyle(color: colorScheme.error),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            _error!,
                            style: TextStyle(
                              color: colorScheme.onSurface.withValues(alpha: 0.7),
                              fontSize: 12,
                            ),
                          ),
                          const SizedBox(height: 16),
                          ElevatedButton(
                            onPressed: _loadCharacters,
                            child: const Text('Retry'),
                          ),
                        ],
                      ),
                    ),
                  )
                else if (_characters == null || _characters!.isEmpty)
                  Card(
                    color: colorScheme.surface.withValues(alpha: 0.1),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                      side: BorderSide(
                        color: colorScheme.outline.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(24.0),
                      child: Column(
                        children: [
                          Text(
                            'No Characters Found',
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'Create your first character in the game to begin your adventure.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: colorScheme.onSurface.withValues(alpha: 0.7),
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Your Characters',
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 16),
                      ..._characters!.map(
                        (character) => Card(
                          color: colorScheme.surface.withValues(alpha: 0.1),
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            leading: Icon(
                              character.dead ? Icons.person_off : Icons.person,
                              color:
                                  character.dead
                                      ? colorScheme.error
                                      : colorScheme.primary,
                            ),
                            title: Text(
                              character.name,
                              style: TextStyle(
                                decoration:
                                    character.dead
                                        ? TextDecoration.lineThrough
                                        : null,
                              ),
                            ),
                            subtitle:
                                character.dead
                                    ? Text(
                                      'Deceased',
                                      style: TextStyle(
                                        color: colorScheme.error,
                                      ),
                                    )
                                    : Text(
                                      'Active',
                                      style: TextStyle(
                                        color: colorScheme.primary,
                                      ),
                                    ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.visibility),
                                  onPressed: () => _viewCharacter(character),
                                  tooltip: 'View Character',
                                ),
                                if (!character.dead)
                                  IconButton(
                                    icon: const Icon(Icons.play_arrow),
                                    onPressed: () => _playStory(character),
                                    tooltip: 'Play Story',
                                  ),
                                IconButton(
                                  icon: Icon(
                                    Icons.delete,
                                    color: colorScheme.error,
                                  ),
                                  onPressed: () => _deleteCharacter(character),
                                  tooltip: 'Delete Character',
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                const SizedBox(height: 40),
                Center(
                  child: Text(
                    'Stay tuned for updates!',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontStyle: FontStyle.italic,
                      color: colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
