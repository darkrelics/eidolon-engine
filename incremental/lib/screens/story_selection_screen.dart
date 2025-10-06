import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/models/story.dart';
import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'game_screen.dart';

/// Screen for selecting available stories
class StorySelectionScreen extends StatefulWidget {
  final Character character;

  const StorySelectionScreen({super.key, required this.character});

  @override
  State<StorySelectionScreen> createState() => _StorySelectionScreenState();
}

class _StorySelectionScreenState extends State<StorySelectionScreen> {
  late ApiService _apiService;
  Future<List<StoryMetadata>>? _storiesFuture;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _apiService = ApiService(authService: AuthService.instance);
    _loadStories();
  }

  void _loadStories() {
    // Check if character already has available stories details
    if (widget.character.availableStoriesDetails != null) {
      setState(() {
        _storiesFuture = Future.value(
          widget.character.availableStoriesDetails!.map((story) => StoryMetadata.fromJson(story)).toList(),
        );
      });
    } else {
      // Fallback: fetch fresh character data to get stories
      setState(() {
        _storiesFuture = _apiService.getCharacterById(widget.character.id).then((character) {
          if (character == null) {
            throw Exception('Character not found');
          }
          if (character.availableStoriesDetails != null) {
            return character.availableStoriesDetails!.map((story) => StoryMetadata.fromJson(story)).toList();
          }
          return <StoryMetadata>[];
        });
      });
    }
  }

  Future<void> _startStory(StoryMetadata story) async {
    if (!story.available) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            story.cooldownRemaining > 0
                ? 'Story on cooldown for ${_formatCooldown(story.cooldownRemaining)}'
                : 'Story not available',
          ),
        ),
      );
      return;
    }

    if (!mounted) return;
    setState(() => _isLoading = true);

    try {
      // Capture provider and navigator references before async operations
      // This allows using them safely after await without accessing BuildContext
      final characterProvider = context.read<CharacterProvider>();
      final navigator = Navigator.of(context);

      final initialSegment = await _apiService.startStory(characterId: widget.character.id, storyId: story.storyID);

      if (!mounted) return;

      // Update character with story data
      final updatedCharacter = widget.character.copyWith(
        gameMode: 'Incremental',
        activeStoryId: initialSegment['StoryID']?.toString(),
        activeSegmentId: initialSegment['ActiveSegmentID']?.toString(),
        storyState: {
          'ActiveSegment': initialSegment,
          'Story': {'Title': story.title, 'Description': story.description, 'Type': story.type, 'StoryID': story.storyID},
        },
      );

      // Save to provider for reload persistence
      await characterProvider.updateCharacter(updatedCharacter);

      // Navigate to game screen with complete character data
      navigator.pushReplacement(
        MaterialPageRoute(
          builder: (context) => const GameScreen(),
          settings: RouteSettings(
            arguments: updatedCharacter,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ErrorHandler.getUserFriendlyMessage(e)), backgroundColor: Theme.of(context).colorScheme.error),
      );
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  String _formatCooldown(int seconds) {
    if (seconds < 60) return '$seconds seconds';
    if (seconds < 3600) return '${seconds ~/ 60} minutes';
    return '${seconds ~/ 3600} hours';
  }

  String _formatDuration(int seconds) {
    if (seconds < 60) return '< 1 min';
    if (seconds < 3600) return '${seconds ~/ 60} min';
    return '${seconds ~/ 3600}h ${(seconds % 3600) ~/ 60}m';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Select Story'),
        backgroundColor: theme.colorScheme.inversePrimary,
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _isLoading ? null : _loadStories)],
      ),
      body: Stack(
        children: [
          FutureBuilder<List<StoryMetadata>>(
            future: _storiesFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const Center(child: CircularProgressIndicator());
              }

              if (snapshot.hasError) {
                return Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.error_outline, size: 64, color: theme.colorScheme.error),
                      const SizedBox(height: 16),
                      Text('Failed to load stories', style: theme.textTheme.headlineSmall),
                      const SizedBox(height: 8),
                      Text(snapshot.error.toString(), style: theme.textTheme.bodyMedium, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      ElevatedButton(onPressed: _loadStories, child: const Text('Retry')),
                    ],
                  ),
                );
              }

              final stories = snapshot.data ?? [];

              if (stories.isEmpty) {
                return Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.auto_stories, size: 64, color: theme.colorScheme.onSurfaceVariant),
                      const SizedBox(height: 16),
                      Text('No Stories Available', style: theme.textTheme.headlineSmall),
                      const SizedBox(height: 8),
                      Text(
                        'Check back later for new adventures!',
                        style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                );
              }

              return ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: stories.length,
                itemBuilder: (context, index) {
                  final story = stories[index];
                  return _StoryCard(
                    story: story,
                    onTap: () => _startStory(story),
                    formatDuration: _formatDuration,
                    formatCooldown: _formatCooldown,
                  );
                },
              );
            },
          ),
          if (_isLoading)
            Container(
              color: Colors.black54,
              child: const Center(child: CircularProgressIndicator()),
            ),
        ],
      ),
    );
  }
}

class _StoryCard extends StatelessWidget {
  final StoryMetadata story;
  final VoidCallback onTap;
  final String Function(int) formatDuration;
  final String Function(int) formatCooldown;

  const _StoryCard({required this.story, required this.onTap, required this.formatDuration, required this.formatCooldown});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isAvailable = story.available;

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: InkWell(
        onTap: isAvailable ? onTap : null,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      story.title,
                      style: theme.textTheme.titleLarge?.copyWith(color: isAvailable ? null : theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  _StoryTypeChip(type: story.type),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                story.description,
                style: theme.textTheme.bodyMedium?.copyWith(color: isAvailable ? null : theme.colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.schedule, size: 16, color: theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text(formatDuration(story.estimatedDuration), style: theme.textTheme.bodySmall),
                  const Spacer(),
                  if (!isAvailable && story.cooldownRemaining > 0) ...[
                    Icon(Icons.timer_off, size: 16, color: theme.colorScheme.error),
                    const SizedBox(width: 4),
                    Text(
                      formatCooldown(story.cooldownRemaining),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                    ),
                  ] else if (isAvailable) ...[
                    Icon(Icons.play_circle_outline, color: theme.colorScheme.primary),
                    const SizedBox(width: 4),
                    Text(
                      'Available',
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.primary, fontWeight: FontWeight.bold),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StoryTypeChip extends StatelessWidget {
  final String type;

  const _StoryTypeChip({required this.type});

  Color _getTypeColor(BuildContext context) {
    final theme = Theme.of(context);
    switch (type.toLowerCase()) {
      case 'one-time':
        return Colors.purple;
      case 'daily':
        return Colors.blue;
      case 'repeatable':
        return Colors.green;
      default:
        return theme.colorScheme.onSurfaceVariant;
    }
  }

  IconData _getTypeIcon() {
    switch (type.toLowerCase()) {
      case 'one-time':
        return Icons.looks_one;
      case 'daily':
        return Icons.today;
      case 'repeatable':
        return Icons.all_inclusive;
      default:
        return Icons.help_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _getTypeColor(context);

    return Chip(
      label: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_getTypeIcon(), size: 16, color: color),
          const SizedBox(width: 4),
          Text(type, style: TextStyle(color: color)),
        ],
      ),
      backgroundColor: color.withValues(alpha: 0.1),
      visualDensity: VisualDensity.compact,
    );
  }
}
