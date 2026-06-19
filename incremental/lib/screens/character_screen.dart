// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:eidolon_incremental/controllers/character_screen_controller.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/widgets/shared/loading_dialog.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class CharacterScreen extends StatelessWidget {
  const CharacterScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => CharacterScreenController(
        apiService: ApiService(authService: AuthService.instance),
        characterProvider: context.read<CharacterProvider>(),
      ),
      child: const _CharacterScreenView(),
    );
  }
}

class _CharacterScreenView extends StatefulWidget {
  const _CharacterScreenView();

  @override
  State<_CharacterScreenView> createState() => _CharacterScreenViewState();
}

class _CharacterScreenViewState extends State<_CharacterScreenView> {
  @override
  void initState() {
    super.initState();
    debugPrint('CharacterScreen: initState called');
    // Load characters when the view is initialized
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<CharacterScreenController>().loadCharacters();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final controller = context.watch<CharacterScreenController>();
    final characters = controller.characters;
    final isLoading = controller.isLoading;
    final error = controller.error;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Select Character'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: controller.loadCharacters,
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
      body: SafeArea(
        child: _buildBody(context, controller, characters, isLoading, error),
      ),
      floatingActionButton: characters != null && characters.isNotEmpty
          ? FloatingActionButton.extended(
              onPressed: () => _showAddCharacterDialog(),
              label: const Text('Add Character'),
              icon: const Icon(Icons.add),
              backgroundColor: colorScheme.primaryContainer,
              foregroundColor: colorScheme.onPrimaryContainer,
            )
          : null,
      floatingActionButtonLocation: FloatingActionButtonLocation.endFloat,
    );
  }

  Widget _buildBody(
    BuildContext context,
    CharacterScreenController controller,
    List<CharacterInfo>? characters,
    bool isLoading,
    String? error,
  ) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    debugPrint(
      'CharacterScreen: _buildBody - isLoading: $isLoading, error: $error, characters: ${characters?.length ?? "null"}',
    );

    if (isLoading && (characters == null || characters.isEmpty)) {
      return const Center(child: CircularProgressIndicator());
    }

    if (error != null && (characters == null || characters.isEmpty)) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.error_outline, size: 64, color: colorScheme.error),
              const SizedBox(height: 16),
              Text(
                error,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: controller.loadCharacters,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (characters == null || characters.isEmpty) {
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
                onPressed: () => _showAddCharacterDialog(),
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
            child: RefreshIndicator(
              onRefresh: controller.loadCharacters,
              child: ListView.builder(
                itemCount: characters.length,
                itemBuilder: (context, index) {
                  final character = characters[index];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: InkWell(
                      onTap: character.dead
                          ? null
                          : () {
                              debugPrint(
                                'CharacterScreen: Character tapped - ${character.name} (${character.id})',
                              );
                              debugPrint(
                                'CharacterScreen: Showing loading dialog for character selection',
                              );
                              _showEnterGameDialog(context, character);
                            },
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
                              onPressed: () =>
                                  _showDeleteCharacterDialog(character),
                            ),
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
          ),
        ],
      ),
    );
  }

  Future<void> _showAddCharacterDialog() async {
    final controller = context.read<CharacterScreenController>();
    List<ArchetypeInfo> archetypes;
    try {
      archetypes = await controller.getArchetypes();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              ErrorHandler.getUserFriendlyMessage(
                e,
                context: 'loading archetypes',
              ),
            ),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
      return;
    }

    if (!mounted) return;

    final nameController = TextEditingController();
    String? selectedArchetype = archetypes.isNotEmpty
        ? archetypes.first.name
        : null;

    await showDialog(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Create New Character'),
          content: StatefulBuilder(
            builder: (sbContext, setDialogState) {
              return Column(
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
                    autofocus: true,
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
                            final isSelected =
                                selectedArchetype == archetype.name;
                            return Card(
                              elevation: isSelected ? 2 : 0,
                              color: isSelected
                                  ? Theme.of(
                                      sbContext,
                                    ).colorScheme.primaryContainer
                                  : Theme.of(sbContext).colorScheme.surface,
                              margin: const EdgeInsets.symmetric(vertical: 4),
                              child: ListTile(
                                selected: isSelected,
                                title: Text(
                                  archetype.name,
                                  style: TextStyle(
                                    fontWeight: isSelected
                                        ? FontWeight.bold
                                        : FontWeight.normal,
                                  ),
                                ),
                                subtitle: archetype.description.isNotEmpty
                                    ? Text(
                                        archetype.description,
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: Theme.of(
                                          sbContext,
                                        ).textTheme.bodySmall,
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
                        color: Theme.of(
                          sbContext,
                        ).colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            Icons.info_outline,
                            size: 20,
                            color: Theme.of(
                              sbContext,
                            ).colorScheme.onSurfaceVariant,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'No archetypes available. Default stats will be used.',
                              style: Theme.of(sbContext).textTheme.bodySmall
                                  ?.copyWith(
                                    color: Theme.of(
                                      sbContext,
                                    ).colorScheme.onSurfaceVariant,
                                  ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              );
            },
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                final name = nameController.text.trim();
                if (name.isEmpty) {
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(
                      content: Text('Please enter a character name'),
                    ),
                  );
                  return;
                }
                Navigator.of(dialogContext).pop();
                _createCharacter(name, selectedArchetype ?? 'default');
              },
              child: const Text('Create'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _createCharacter(String name, String archetype) async {
    final controller = context.read<CharacterScreenController>();

    await controller.createCharacter(
      name,
      archetype,
      onSuccess: (message) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(message), backgroundColor: Colors.green),
          );
        }
      },
      onError: (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(error),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
    );
  }

  Future<void> _showDeleteCharacterDialog(CharacterInfo character) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Character'),
        content: Text(
          'Are you sure you want to delete "${character.name}"? This action cannot be undone.',
        ),
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
      if (mounted) {
        _deleteCharacter(character);
      }
    }
  }

  Future<void> _deleteCharacter(CharacterInfo character) async {
    final controller = context.read<CharacterScreenController>();

    await controller.deleteCharacter(
      character,
      onSuccess: (message) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(message), backgroundColor: Colors.green),
          );
        }
      },
      onError: (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(error),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
    );
  }

  Future<void> _showEnterGameDialog(
    BuildContext context,
    CharacterInfo character,
  ) async {
    final controller = context.read<CharacterScreenController>();
    final rootNavigator = Navigator.of(context, rootNavigator: true);
    final navigator = Navigator.of(context);

    // Show loading dialog
    LoadingDialog.show(
      context: context,
      title: 'Entering Game',
      message: 'Loading ${character.name}...',
      subtitle: 'Preparing your adventure',
      barrierDismissible: false,
    );

    await controller.enterGame(
      character,
      onSuccess: () {
        // Close loading dialog
        rootNavigator.pop();

        // Navigate to game
        navigator.pushReplacementNamed(
          '/game',
          arguments:
              character, // We pass info, game screen will load full data if needed or use provider
        );
      },
      onError: (error) {
        // Close loading dialog
        rootNavigator.pop();

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(error),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
    );
  }
}
