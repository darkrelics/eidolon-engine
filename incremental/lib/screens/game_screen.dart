import 'package:flutter/material.dart';
import '../models/character.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../utils/error_handler.dart';

class GameScreen extends StatefulWidget {
  const GameScreen({super.key});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  late ApiService _apiService;
  Character? _character;
  CharacterInfo? _characterInfo;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    debugPrint('GameScreen: initState called');
    _apiService = ApiService(authService: AuthService.instance);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Get character info from route arguments
    final args = ModalRoute.of(context)?.settings.arguments;
    debugPrint('GameScreen: didChangeDependencies called, args type: ${args.runtimeType}');
    debugPrint('GameScreen: args: $args');
    if (args is CharacterInfo && args != _characterInfo) {
      debugPrint('GameScreen: Got CharacterInfo - name: ${args.name}, id: ${args.id}');
      _characterInfo = args;
      _selectAndLoadCharacter();
    } else {
      debugPrint('GameScreen: No valid CharacterInfo in arguments');
    }
  }

  Future<void> _selectAndLoadCharacter() async {
    debugPrint('GameScreen: _selectAndLoadCharacter called');
    if (_characterInfo == null) {
      debugPrint('GameScreen: _characterInfo is null, returning');
      return;
    }
    
    debugPrint('GameScreen: Loading character with ID: ${_characterInfo!.id}');
    
    try {
      setState(() {
        _isLoading = true;
        _error = null;
      });

      // Load the character data by ID
      debugPrint('GameScreen: Calling getCharacterById...');
      final character = await _apiService.getCharacterById(_characterInfo!.id);
      debugPrint('GameScreen: Character loaded: ${character != null ? 'success' : 'null'}');
      
      if (mounted) {
        setState(() {
          _character = character;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('GameScreen: ERROR loading character: $e');
      debugPrint('GameScreen: Error stack trace: ${StackTrace.current}');
      if (mounted) {
        setState(() {
          _error = ErrorHandler.getUserFriendlyMessage(e, context: 'loading character');
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _loadCharacter() async {
    if (_characterInfo == null) return;
    
    try {
      setState(() {
        _isLoading = true;
        _error = null;
      });

      final character = await _apiService.getCharacterById(_characterInfo!.id);
      
      if (mounted) {
        setState(() {
          _character = character;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('Error loading character: $e');
      if (mounted) {
        setState(() {
          _error = ErrorHandler.getUserFriendlyMessage(e, context: 'loading character');
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
        title: Text(_characterInfo?.name ?? 'Eidolon Incremental'),
        leading: IconButton(
          icon: const Icon(Icons.chevron_left),
          onPressed: () {
            Navigator.pushReplacementNamed(context, '/character-selection');
          },
          tooltip: 'Back to Character Selection',
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadCharacter,
            tooltip: 'Refresh',
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/account-settings');
            },
          ),
        ],
      ),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? _buildErrorWidget()
                : _character == null
                    ? _buildNoCharacterWidget()
                    : _buildGameInterface(),
      ),
    );
  }

  Widget _buildErrorWidget() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              'Error loading character',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _loadCharacter,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoCharacterWidget() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.person_off,
              size: 64,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 16),
            Text(
              'No character data found',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () {
                Navigator.pushReplacementNamed(context, '/character-selection');
              },
              child: const Text('Back to Character Selection'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGameInterface() {
    return Row(
      children: [
        // Character Panel (Left)
        Expanded(
          flex: 2,
          child: Container(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              border: Border(
                right: BorderSide(
                  color: Theme.of(context).colorScheme.outline,
                  width: 1,
                ),
              ),
            ),
            child: CharacterPanel(character: _character!),
          ),
        ),

        // Action Panel (Center)
        Expanded(
          flex: 3,
          child: Container(
            color: Theme.of(context).colorScheme.surface,
            child: ActionPanel(character: _character!),
          ),
        ),

        // Inventory Panel (Right)
        Expanded(
          flex: 2,
          child: Container(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              border: Border(
                left: BorderSide(
                  color: Theme.of(context).colorScheme.outline,
                  width: 1,
                ),
              ),
            ),
            child: InventoryPanel(character: _character!),
          ),
        ),
      ],
    );
  }
}

class CharacterPanel extends StatelessWidget {
  final Character character;

  const CharacterPanel({super.key, required this.character});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Character', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 16),
          
          // Basic Info
          _buildInfoRow('Name', character.name),
          _buildInfoRow('Archetype', character.archetypeName),
          const SizedBox(height: 16),
          
          // Health & Essence
          _buildStatBar(
            context,
            'Health',
            character.health,
            character.maxHealth,
            colorScheme.error,
          ),
          const SizedBox(height: 8),
          _buildStatBar(
            context,
            'Essence',
            character.essence,
            character.maxEssence,
            colorScheme.primary,
          ),
          const SizedBox(height: 24),
          
          // Attributes
          Text('Attributes', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ...Attributes.all.map((attr) => Padding(
                padding: const EdgeInsets.only(bottom: 4.0),
                child: _buildAttributeRow(
                  attr,
                  character.attributes[attr] ?? 0.0,
                ),
              )),
          const SizedBox(height: 24),
          
          // Skills
          if (character.skills.isNotEmpty) ...[
            Text('Skills', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...character.skills.entries.map((entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 4.0),
                  child: _buildAttributeRow(entry.key, entry.value),
                )),
          ],
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
        Text(value),
      ],
    );
  }

  Widget _buildStatBar(
    BuildContext context,
    String label,
    double current,
    double max,
    Color color,
  ) {
    final percentage = max > 0 ? (current / max).clamp(0.0, 1.0) : 0.0;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
            Text('${current.toInt()}/${max.toInt()}'),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: percentage,
          backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
          valueColor: AlwaysStoppedAnimation<Color>(color),
          minHeight: 8,
        ),
      ],
    );
  }

  Widget _buildAttributeRow(String name, double value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(name),
        Text(value.toStringAsFixed(0)),
      ],
    );
  }
}

class ActionPanel extends StatelessWidget {
  final Character character;

  const ActionPanel({super.key, required this.character});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            'Current Action',
            style: theme.textTheme.headlineSmall,
          ),
          const SizedBox(height: 32),
          
          // Check if character has active story
          if (character.storyState != null &&
              character.storyState!['segmentId'] != null) ...[
            LinearProgressIndicator(
              value: 0.3, // This would be calculated from actual progress
              minHeight: 20,
              backgroundColor:
                  Theme.of(context).colorScheme.surfaceContainerHighest,
            ),
            const SizedBox(height: 16),
            Text('Story: ${character.storyState!['storyName'] ?? 'Unknown'}'),
            Text('Segment: ${character.storyState!['segmentName'] ?? 'Unknown'}'),
          ] else ...[
            Icon(
              Icons.explore,
              size: 64,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: 16),
            Text(
              'No active story',
              style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () {
                // TODO: Navigate to story selection
              },
              icon: const Icon(Icons.play_arrow),
              label: const Text('Start Adventure'),
            ),
          ],
        ],
      ),
    );
  }
}

class InventoryPanel extends StatelessWidget {
  final Character character;

  const InventoryPanel({super.key, required this.character});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Inventory', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 16),
          
          // Resources
          if (character.resources.isNotEmpty) ...[
            Text('Resources', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...character.resources.entries.map((entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 4.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_formatResourceName(entry.key)),
                      Text(entry.value.toString()),
                    ],
                  ),
                )),
            const SizedBox(height: 16),
          ],
          
          // Equipment
          if (character.inventory.isNotEmpty) ...[
            Text('Equipment', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...character.inventory.entries.map((entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 4.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_formatSlotName(entry.key)),
                      Expanded(
                        child: Text(
                          entry.value,
                          textAlign: TextAlign.right,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                )),
          ] else ...[
            Text(
              'No items equipped',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _formatResourceName(String name) {
    // Capitalize first letter and handle common resource names
    switch (name.toLowerCase()) {
      case 'gold':
        return 'Gold';
      case 'supplies':
        return 'Supplies';
      case 'reputation':
        return 'Reputation';
      default:
        return name[0].toUpperCase() + name.substring(1);
    }
  }

  String _formatSlotName(String slot) {
    // Format equipment slot names
    return slot
        .split('_')
        .map((word) => word[0].toUpperCase() + word.substring(1))
        .join(' ');
  }
}