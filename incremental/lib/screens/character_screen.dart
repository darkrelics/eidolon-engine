// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../utils/error_handler.dart';
import '../widgets/shared/loading_dialog.dart';

class CharacterScreen extends StatefulWidget {
  const CharacterScreen({super.key});

  @override
  State<CharacterScreen> createState() => _CharacterScreenState();
}

class _CharacterScreenState extends State<CharacterScreen> {
  late ApiService _apiService;
  List<CharacterInfo>? _characters;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    debugPrint('CharacterScreen: initState called');
    _initializeApiService();
    _loadCharacters();
  }

  void _initializeApiService() {
    _apiService = ApiService(authService: AuthService.instance);
  }

  Future<void> _loadCharacters() async {
    try {
      debugPrint('CharacterScreen: Loading characters...');
      setState(() {
        _isLoading = true;
        _error = null;
      });

      final characters = await _apiService.listCharacters();
      debugPrint('CharacterScreen: Loaded ${characters.length} characters');

      if (mounted) {
        setState(() {
          _characters = characters;
          _isLoading = false;
        });
        debugPrint('CharacterScreen: State updated - isLoading: $_isLoading, characters: ${_characters?.length ?? "null"}');
      }
    } catch (e) {
      debugPrint('CharacterScreen: ERROR loading characters: $e');
      debugPrint('CharacterScreen: Error type: ${e.runtimeType}');
      if (mounted) {
        // Extract user-friendly error message
        String errorMessage = 'Unable to load characters. Please try again.';
        if (e.toString().contains('Internal server error')) {
          errorMessage = 'Server error occurred. Please try again later.';
        } else if (e.toString().contains('Network')) {
          errorMessage = 'Connection error. Please check your internet connection.';
        }
        
        setState(() {
          _error = errorMessage;
          _isLoading = false;
        });
        
        // Show immediate error feedback
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
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
            icon: const Icon(Icons.refresh),
            onPressed: _loadCharacters,
            tooltip: 'Refresh',
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/account-settings');
            },
            tooltip: 'Settings',
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              final authProvider = context.read<AuthProvider>();
              final navigator = Navigator.of(context);
              await authProvider.signOut();
              navigator.pushReplacementNamed('/login');
            },
            tooltip: 'Sign Out',
          ),
        ],
      ),
      body: SafeArea(child: _buildBody()),
      floatingActionButton: _characters != null && _characters!.isNotEmpty
          ? FloatingActionButton.extended(
              onPressed: _showAddCharacterDialog,
              label: const Text('Add Character'),
              icon: const Icon(Icons.add),
              backgroundColor: colorScheme.primaryContainer,
              foregroundColor: colorScheme.onPrimaryContainer,
            )
          : null,
      floatingActionButtonLocation: FloatingActionButtonLocation.endFloat,
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
                decoration: const InputDecoration(labelText: 'Character Name', hintText: 'Enter character name'),
                textCapitalization: TextCapitalization.words,
              ),
              if (archetypes.isNotEmpty) ...[
                const SizedBox(height: 16),
                const Text('Archetype:'),
                const SizedBox(height: 8),
                Container(
                  constraints: const BoxConstraints(maxHeight: 300),
                  child: SingleChildScrollView(
                    child: Column(
                      children: archetypes.map((archetype) {
                        final isSelected = selectedArchetype == archetype.name;
                        return Card(
                          elevation: isSelected ? 2 : 0,
                          color: isSelected 
                            ? Theme.of(context).colorScheme.primaryContainer 
                            : Theme.of(context).colorScheme.surface,
                          margin: const EdgeInsets.symmetric(vertical: 4),
                          child: ListTile(
                            selected: isSelected,
                            title: Text(
                              archetype.name,
                              style: TextStyle(
                                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                              ),
                            ),
                            subtitle: archetype.description.isNotEmpty
                              ? Text(
                                  archetype.description,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context).textTheme.bodySmall,
                                )
                              : null,
                            onTap: () {
                              setDialogState(() {
                                selectedArchetype = archetype.name;
                              });
                            },
                          ),
                        );
                      }).toList(),
                    ),
                  ),
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
                      Icon(Icons.info_outline, size: 20, color: Theme.of(context).colorScheme.onSurfaceVariant),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'No archetypes available. Default stats will be used.',
                          style: Theme.of(
                            context,
                          ).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
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
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () async {
              final name = nameController.text.trim();
              if (name.isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please enter a character name')));
                return;
              }

              Navigator.of(context).pop();
              debugPrint('Creating character with name: $name, archetype: ${selectedArchetype ?? 'default'}');
              await _createCharacter(name, selectedArchetype ?? 'default');
            },
            child: const Text('Create'),
          ),
        ],
      ),
    );
  }

  Future<void> _createCharacter(String name, String archetype) async {
    try {
      debugPrint('CharacterScreen: _createCharacter called with name: $name, archetype: $archetype');

      setState(() {
        _isLoading = true;
      });

      debugPrint('CharacterScreen: Calling API to add character...');
      final result = await _apiService.addCharacter(name: name, archetype: archetype);
      final characterId = result['CharacterID'] ?? '';
      final createdName = result['CharacterName'] ?? name;
      final createdArchetype = result['Archetype'] ?? archetype;
      debugPrint('CharacterScreen: Character created with ID: $characterId');

      if (mounted) {
        String message = 'Created character: $createdName';
        if (createdArchetype != 'default' && createdArchetype.isNotEmpty) {
          message += ' ($createdArchetype)';
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(message),
            backgroundColor: Colors.green,
          ),
        );
      }

      // Reload characters
      debugPrint('CharacterScreen: Reloading characters...');
      await _loadCharacters();
    } catch (e, stackTrace) {
      debugPrint('CharacterScreen: Error creating character: $e');
      debugPrint('CharacterScreen: Stack trace: $stackTrace');
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        // Extract error message
        String errorMessage = e.toString();
        if (errorMessage.contains('Character name is already taken')) {
          errorMessage = 'That character name is already taken. Please choose another.';
        } else if (errorMessage.contains('Character limit reached')) {
          errorMessage = 'You have reached the maximum number of characters.';
        } else if (errorMessage.contains('Character name is not available')) {
          errorMessage = 'That character name is not available. Please choose another.';
        } else {
          errorMessage = ErrorHandler.getUserFriendlyMessage(e, context: 'createCharacter');
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
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
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed ?? false) {
      await _deleteCharacter(character);
    }
  }

  Future<void> _showEnterGameDialog(CharacterInfo character) async {
    // Show loading dialog
    LoadingDialog.show(
      context: context,
      title: 'Entering Game',
      message: 'Loading ${character.name}...',
      subtitle: 'Preparing your adventure',
      barrierDismissible: false,
    );

    try {
      // Pre-load character data
      final fullCharacter = await _apiService.getCharacterById(character.id);
      
      if (!mounted) return;
      
      // Close the loading dialog
      LoadingDialog.hide(context);
      
      // Navigate to game screen with pre-loaded character data
      Navigator.pushReplacementNamed(
        context,
        '/game',
        arguments: fullCharacter ?? character,
      );
    } catch (e) {
      if (!mounted) return;
      
      // Close the loading dialog
      LoadingDialog.hide(context);
      
      // Show error
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ErrorHandler.getUserFriendlyMessage(e, context: 'loading character'),
          ),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  Future<void> _deleteCharacter(CharacterInfo character) async {
    try {
      setState(() {
        _isLoading = true;
      });

      final deleteResult = await _apiService.deleteCharacter(character.id);

      if (mounted) {
        // Use character name from response if available, otherwise use local name
        final deletedName = deleteResult['CharacterName'] ?? character.name;
        final itemsDeleted = deleteResult['ItemsDeleted'] ?? 0;
        final segmentsDeleted = deleteResult['ActiveSegmentsDeleted'] ?? 0;
        
        // Build detailed message
        String message = 'Deleted character: $deletedName';
        if (itemsDeleted > 0 || segmentsDeleted > 0) {
          message += ' ($itemsDeleted items, $segmentsDeleted segments)';
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(message),
            backgroundColor: Colors.green,
          ),
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
        // Extract error message
        String errorMessage = e.toString();
        if (errorMessage.contains('Character not found')) {
          errorMessage = 'Character not found';
        } else if (errorMessage.contains('Access denied')) {
          errorMessage = 'You do not have permission to delete this character';
        } else {
          errorMessage = ErrorHandler.getUserFriendlyMessage(e, context: 'deleteCharacter');
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Widget _buildBody() {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    debugPrint('CharacterScreen: _buildBody - isLoading: $_isLoading, error: $_error, characters: ${_characters?.length ?? "null"}');

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
                _error!,
                style: theme.textTheme.titleMedium?.copyWith(color: colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton(onPressed: _loadCharacters, child: const Text('Retry')),
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
              Icon(Icons.person_off, size: 64, color: colorScheme.onSurfaceVariant),
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
          Text('Select a Character', style: theme.textTheme.headlineMedium, textAlign: TextAlign.center),
          const SizedBox(height: 24),
          Expanded(
            child: ListView.builder(
              itemCount: _characters!.length,
              itemBuilder: (context, index) {
                final character = _characters![index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: InkWell(
                    onTap: character.dead
                        ? null
                        : () {
                            debugPrint('CharacterScreen: Character tapped - ${character.name} (${character.id})');
                            debugPrint('CharacterScreen: Showing loading dialog for character selection');
                            _showEnterGameDialog(character);
                          },
                    child: ListTile(
                      leading: Icon(
                        character.dead ? Icons.person_off : Icons.person,
                        color: character.dead ? colorScheme.error : colorScheme.primary,
                      ),
                      title: Text(character.name, style: TextStyle(decoration: character.dead ? TextDecoration.lineThrough : null)),
                      subtitle: character.dead
                          ? Text('Deceased', style: TextStyle(color: colorScheme.error))
                          : Text('Active', style: TextStyle(color: colorScheme.primary)),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(icon: const Icon(Icons.delete), onPressed: () => _showDeleteCharacterDialog(character)),
                          const Icon(Icons.chevron_right),
                        ],
                      ),
                      enabled: !character.dead,
                    ),
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
