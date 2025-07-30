import 'dart:async';
import 'package:flutter/material.dart';
import '../models/character.dart';
import '../models/story.dart';
import '../models/active_segment.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../utils/error_handler.dart';
import '../utils/json_utils.dart';
import '../widgets/mechanical_segment_display.dart';

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
    debugPrint(
      'GameScreen: didChangeDependencies called, args type: ${args.runtimeType}',
    );
    debugPrint('GameScreen: args: $args');
    if (args is CharacterInfo && args != _characterInfo) {
      debugPrint(
        'GameScreen: Got CharacterInfo - name: ${args.name}, id: ${args.id}',
      );
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
      debugPrint(
        'GameScreen: Character loaded: ${character != null ? 'success' : 'null'}',
      );

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
          _error = ErrorHandler.getUserFriendlyMessage(
            e,
            context: 'loading character',
          );
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
          _error = ErrorHandler.getUserFriendlyMessage(
            e,
            context: 'loading character',
          );
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
            FilledButton(onPressed: _loadCharacter, child: const Text('Retry')),
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

    // Debug logging
    debugPrint('CharacterPanel - attributes: ${character.attributes}');
    debugPrint('CharacterPanel - skills: ${character.skills}');
    debugPrint('CharacterPanel - health: ${character.health}/${character.maxHealth}');
    debugPrint('CharacterPanel - essence: ${character.essence}/${character.maxEssence}');

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
          ...Attributes.all.map(
            (attr) => Padding(
              padding: const EdgeInsets.only(bottom: 4.0),
              child: _buildAttributeRow(
                attr,
                character.attributes[attr] ?? 0.0,
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Skills
          if (character.skills.isNotEmpty) ...[
            Text('Skills', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...character.skills.entries.map(
              (entry) => Padding(
                padding: const EdgeInsets.only(bottom: 4.0),
                child: _buildAttributeRow(entry.key, entry.value),
              ),
            ),
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
          backgroundColor: Theme.of(
            context,
          ).colorScheme.surfaceContainerHighest,
          valueColor: AlwaysStoppedAnimation<Color>(color),
          minHeight: 8,
        ),
      ],
    );
  }

  Widget _buildAttributeRow(String name, double value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [Text(name), Text(value.toStringAsFixed(0))],
    );
  }
}

class ActionPanel extends StatefulWidget {
  final Character character;

  const ActionPanel({super.key, required this.character});

  @override
  State<ActionPanel> createState() => _ActionPanelState();
}

class _ActionPanelState extends State<ActionPanel> {
  late ApiService _apiService;
  Future<List<StoryMetadata>>? _storiesFuture;
  bool _showStoryList = false;
  bool _loadingCurrentStory = false;
  Map<String, dynamic>? _currentStoryData;
  Timer? _refreshTimer;
  Timer? _countdownTimer;
  int _timeRemaining = 0;
  String? _selectedStoryType;
  bool _showOnlyAvailable = false;
  
  // Configuration constants
  static const int _autoRefreshIntervalSeconds = 60; // Auto-refresh every 60 seconds
  static const int _countdownIntervalSeconds = 1;    // Update countdown every second

  @override
  void initState() {
    super.initState();
    _apiService = ApiService(authService: AuthService.instance);
    _loadCurrentStory();
    _startTimers();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _startTimers() {
    // Refresh story data periodically
    _refreshTimer = Timer.periodic(
      Duration(seconds: _autoRefreshIntervalSeconds), 
      (_) {
        if (widget.character.storyState != null) {
          _loadCurrentStory();
        }
      },
    );

    // Update countdown timer
    _countdownTimer = Timer.periodic(
      Duration(seconds: _countdownIntervalSeconds), 
      (_) {
        if (_timeRemaining > 0 && mounted) {
          setState(() {
            _timeRemaining--;
          });
        }
      },
    );
  }

  Future<void> _loadCurrentStory() async {
    setState(() {
      _loadingCurrentStory = true;
    });

    try {
      var currentStory = await _apiService.getCurrentStory(
        characterId: widget.character.id,
      );
      
      // Check if we have a mechanical segment that needs history data
      if (currentStory != null) {
        final activeSegmentData = currentStory['ActiveSegment'] as Map<String, dynamic>?;
        if (activeSegmentData != null) {
          final segmentType = activeSegmentData['SegmentType'] as String?;
          final processingStatus = activeSegmentData['ProcessingStatus'] as String?;
          final clientEvents = activeSegmentData['ClientEvents'] as List<dynamic>?;
          
          // If mechanical segment is processed but missing client events, fetch from history
          if (segmentType == 'mechanical' && 
              processingStatus == 'processed' && 
              clientEvents == null) {
            try {
              final history = await _apiService.getSegmentHistory(
                characterId: widget.character.id,
              );
              
              if (history.isNotEmpty) {
                // Find matching segment in history
                final activeSegmentId = activeSegmentData['ActiveSegmentID'] as String;
                final historySegment = history.firstWhere(
                  (seg) => seg['ActiveSegmentID'] == activeSegmentId,
                  orElse: () => <String, dynamic>{},
                );
                
                if (historySegment.isNotEmpty) {
                  // Merge history data into active segment
                  activeSegmentData['ClientEvents'] = historySegment['ClientEvents'];
                  activeSegmentData['CharacterUpdates'] = historySegment['CharacterUpdates'];
                  activeSegmentData['Outcome'] = historySegment['Outcome'];
                }
              }
            } catch (e) {
              debugPrint('Error fetching segment history: $e');
            }
          }
        }
      }

      if (mounted) {
        setState(() {
          _loadingCurrentStory = false;
          _currentStoryData = currentStory;
          
          // Update character's story state if we have current story
          if (currentStory != null) {
            final storyData = JsonUtils.getFlexibleMap(currentStory, 'Story', 'story');
            final segmentData = JsonUtils.getFlexibleMap(currentStory, 'Segment', 'segment');
            _timeRemaining = JsonUtils.getFlexibleRequired<int>(
              segmentData,
              'TimeRemaining',
              'timeRemaining',
              defaultValue: 0,
            );
            
            final narrative = JsonUtils.getFlexible<String>(segmentData, 'Narrative', 'narrative') ?? '';
            final shortStatus = JsonUtils.getFlexible<String>(segmentData, 'ShortStatus', 'shortStatus') ?? 'In progress';
            final segmentName = narrative.isNotEmpty ? 
              (narrative.length > 50 ? narrative.substring(0, 50) : narrative) : shortStatus;
            
            widget.character.storyState = {
              'storyId': JsonUtils.getFlexible<String>(storyData, 'StoryID', 'storyId'),
              'storyName': JsonUtils.getFlexible<String>(storyData, 'Title', 'title'),
              'segmentId': JsonUtils.getFlexible<String>(segmentData, 'SegmentID', 'segmentId'),
              'segmentType': JsonUtils.getFlexible<String>(segmentData, 'SegmentType', 'segmentType'),
              'segmentName': segmentName,
              'timeRemaining': JsonUtils.getFlexible<int>(segmentData, 'TimeRemaining', 'timeRemaining'),
              'totalSegments': JsonUtils.getFlexible<int>(storyData, 'TotalSegments', 'totalSegments'),
              'currentSegmentIndex': JsonUtils.getFlexible<int>(storyData, 'CurrentSegmentIndex', 'currentSegmentIndex'),
            };
          } else {
            widget.character.storyState = null;
          }
        });
        
        // For mechanical segments still processing, poll more frequently
        if (_currentStoryData != null) {
          final activeSegmentData = _currentStoryData!['ActiveSegment'] as Map<String, dynamic>?;
          if (activeSegmentData != null) {
            final segmentType = activeSegmentData['SegmentType'] as String?;
            final processingStatus = activeSegmentData['ProcessingStatus'] as String?;
            
            if (segmentType == 'mechanical' && processingStatus != 'processed') {
              // Cancel existing refresh timer
              _refreshTimer?.cancel();
              // Poll every 2 seconds for mechanical segment processing
              _refreshTimer = Timer(const Duration(seconds: 2), () {
                if (mounted) {
                  _loadCurrentStory();
                }
              });
            }
          }
        }
      }
    } catch (e) {
      debugPrint('Error loading current story: $e');
      if (mounted) {
        setState(() {
          _loadingCurrentStory = false;
        });
      }
    }
  }

  void _toggleStoryList() {
    setState(() {
      _showStoryList = !_showStoryList;
      if (_showStoryList && _storiesFuture == null) {
        _loadStories();
      }
    });
  }

  void _loadStories() {
    setState(() {
      _storiesFuture = _apiService.getStories(widget.character.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text('Adventures', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 32),

          // Show loading indicator while checking for current story
          if (_loadingCurrentStory) ...[
            const CircularProgressIndicator(),
          ] else if (widget.character.storyState != null &&
              widget.character.storyState!['segmentId'] != null) ...[
            _buildActiveStory(theme),
          ] else if (_showStoryList) ...[
            _buildStorySelection(theme),
          ] else ...[
            _buildNoActiveStory(theme),
          ],
        ],
      ),
    );
  }

  Widget _buildActiveStory(ThemeData theme) {
    final storyData = _currentStoryData;
    final Map<String, dynamic> story = storyData != null 
        ? JsonUtils.getFlexibleMap(storyData, 'Story', 'story') 
        : <String, dynamic>{};
    final Map<String, dynamic> segment = storyData != null 
        ? JsonUtils.getFlexibleMap(storyData, 'Segment', 'segment') 
        : <String, dynamic>{};
    
    // Check if we have an active segment that's mechanical and processed
    final activeSegmentData = storyData?['ActiveSegment'] as Map<String, dynamic>?;
    ActiveSegment? activeSegment;
    if (activeSegmentData != null) {
      activeSegment = ActiveSegment.fromJson(activeSegmentData);
    }
    
    final segmentType = JsonUtils.getFlexibleRequired<String>(
      segment,
      'Type',
      'type',
      defaultValue: 'narrative',
    );
    
    // Calculate progress
    final currentIndex = JsonUtils.getFlexibleRequired<int>(
      story,
      'CurrentSegmentIndex',
      'currentSegmentIndex',
      defaultValue: 0,
    );
    final totalSegments = JsonUtils.getFlexibleRequired<int>(
      story,
      'TotalSegments',
      'totalSegments',
      defaultValue: 1,
    );
    final progress = totalSegments > 0 ? (currentIndex + 1) / totalSegments : 0.0;
    
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Story Header Card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          JsonUtils.getFlexibleRequired<String>(
                            story,
                            'Title',
                            'title',
                            defaultValue: 'Unknown Story',
                          ),
                          style: theme.textTheme.titleLarge,
                        ),
                      ),
                      _buildStoryTypeChip(
                        JsonUtils.getFlexibleRequired<String>(
                          story,
                          'Type',
                          'type',
                          defaultValue: 'unknown',
                        ),
                        theme,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  // Progress Bar
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Progress',
                            style: theme.textTheme.labelMedium,
                          ),
                          Text(
                            '${currentIndex + 1} / $totalSegments',
                            style: theme.textTheme.labelMedium,
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      LinearProgressIndicator(
                        value: progress,
                        minHeight: 8,
                        backgroundColor: theme.colorScheme.surfaceContainerHighest,
                      ),
                    ],
                  ),
                  if (_timeRemaining > 0) ...[
                    const SizedBox(height: 12),
                    _buildTimerDisplay(theme),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Segment Content Card
          if (activeSegment != null && 
              activeSegment.segmentType == 'mechanical' &&
              (activeSegment.processingStatus == 'processed' || activeSegment.clientEvents != null)) ...[
            // Use mechanical segment display for processed mechanical segments
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: SizedBox(
                  height: 400, // Fixed height for the mechanical display
                  child: MechanicalSegmentDisplay(
                    segment: activeSegment,
                    onComplete: () {
                      // Handle segment completion
                      _loadCurrentStory();
                    },
                  ),
                ),
              ),
            ),
          ] else ...[
            // Use regular display for other segment types or unprocessed mechanical
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          _getSegmentIcon(segmentType),
                          size: 20,
                          color: theme.colorScheme.primary,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _getSegmentTypeLabel(segmentType),
                          style: theme.textTheme.titleMedium,
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Text(
                      JsonUtils.getFlexibleRequired<String>(
                        segment,
                        'Content',
                        'content',
                        defaultValue: 'Loading segment content...',
                      ),
                      style: theme.textTheme.bodyLarge,
                    ),
                    if (JsonUtils.getFlexible<String>(segment, 'ImageUrl', 'imageUrl') != null) ...[
                      const SizedBox(height: 16),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.network(
                          JsonUtils.getFlexible<String>(segment, 'ImageUrl', 'imageUrl')!,
                          fit: BoxFit.cover,
                          height: 200,
                          width: double.infinity,
                          errorBuilder: (context, error, stackTrace) {
                            return Container(
                              height: 200,
                              color: theme.colorScheme.surfaceContainerHighest,
                              child: const Center(
                                child: Icon(Icons.broken_image, size: 48),
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],

          // Decision Options (if decision segment)
          if (segmentType == 'decision' && JsonUtils.getFlexible(segment, 'Options', 'options') != null) ...[
            const SizedBox(height: 16),
            _buildDecisionOptions(JsonUtils.getFlexible(segment, 'Options', 'options'), theme),
          ],

          // Challenge Results (if narrative segment)
          if (segmentType == 'narrative' && JsonUtils.getFlexible(segment, 'ChallengeResults', 'challengeResults') != null) ...[
            const SizedBox(height: 16),
            _buildChallengeResults(JsonUtils.getFlexible(segment, 'ChallengeResults', 'challengeResults'), theme),
          ],

          // Action Buttons
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: _loadCurrentStory,
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
              ),
              const SizedBox(width: 16),
              FilledButton.icon(
                onPressed: _timeRemaining == 0 ? () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Segment completion not yet implemented'),
                    ),
                  );
                } : null,
                icon: const Icon(Icons.arrow_forward),
                label: Text(_timeRemaining == 0 ? 'Continue' : 'Processing...'),
              ),
              // Show rest option if not already in a rest segment
              if (segmentType != 'rest') ...[
                const SizedBox(width: 16),
                OutlinedButton.icon(
                  onPressed: _initiateRest,
                  icon: const Icon(Icons.healing),
                  label: const Text('Rest'),
                ),
              ],
              const SizedBox(width: 16),
              OutlinedButton.icon(
                onPressed: () => _abandonStory(),
                icon: const Icon(Icons.exit_to_app),
                label: const Text('Abandon'),
              ),
            ],
          ),
        ],
      ),
    );
  }
  
  Widget _buildTimerDisplay(ThemeData theme) {
    final minutes = _timeRemaining ~/ 60;
    final seconds = _timeRemaining % 60;
    final timerText = '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
    
    return Row(
      children: [
        Icon(
          Icons.timer,
          size: 16,
          color: _timeRemaining < 60 
              ? theme.colorScheme.error 
              : theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 4),
        Text(
          'Time remaining: $timerText',
          style: theme.textTheme.labelLarge?.copyWith(
            color: _timeRemaining < 60 
                ? theme.colorScheme.error 
                : null,
          ),
        ),
      ],
    );
  }

  Widget _buildStoryTypeChip(String type, ThemeData theme) {
    Color backgroundColor;
    IconData icon;
    
    switch (type.toLowerCase()) {
      case 'one-time':
        backgroundColor = theme.colorScheme.primaryContainer;
        icon = Icons.stars;
        break;
      case 'daily':
        backgroundColor = theme.colorScheme.secondaryContainer;
        icon = Icons.today;
        break;
      case 'repeatable':
        backgroundColor = theme.colorScheme.tertiaryContainer;
        icon = Icons.refresh;
        break;
      default:
        backgroundColor = theme.colorScheme.surfaceContainerHighest;
        icon = Icons.help_outline;
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16),
          const SizedBox(width: 4),
          Text(
            type,
            style: theme.textTheme.labelMedium,
          ),
        ],
      ),
    );
  }

  IconData _getSegmentIcon(String type) {
    switch (type.toLowerCase()) {
      case 'decision':
        return Icons.psychology;
      case 'narrative':
        return Icons.book;
      case 'combat':
        return Icons.sports_kabaddi;
      case 'mechanical':
        return Icons.engineering;
      case 'rest':
        return Icons.healing;
      default:
        return Icons.help_outline;
    }
  }

  String _getSegmentTypeLabel(String type) {
    switch (type.toLowerCase()) {
      case 'decision':
        return 'Decision Point';
      case 'narrative':
        return 'Story Segment';
      case 'combat':
        return 'Combat Encounter';
      case 'mechanical':
        return 'Challenge';
      case 'rest':
        return 'Rest & Recovery';
      default:
        return 'Unknown Segment';
    }
  }

  Widget _buildDecisionOptions(List<dynamic> options, ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Available Choices',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Note: Decision submission coming soon',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            ...options.map((option) => Padding(
              padding: const EdgeInsets.only(bottom: 8.0),
              child: OutlinedButton(
                onPressed: null, // Disabled until api_submit_decision is implemented
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(double.infinity, 48),
                ),
                child: Text(
                  option is Map<String, dynamic> 
                    ? JsonUtils.getFlexibleRequired<String>(
                        option,
                        'Text',
                        'text',
                        defaultValue: option.toString(),
                      )
                    : option.toString(),
                  textAlign: TextAlign.center,
                ),
              ),
            )),
          ],
        ),
      ),
    );
  }

  Widget _buildChallengeResults(List<dynamic> results, ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Challenge Results',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            ...results.map((result) => Padding(
              padding: const EdgeInsets.only(bottom: 8.0),
              child: Row(
                children: [
                  Icon(
                    result['success'] == true ? Icons.check_circle : Icons.cancel,
                    color: result['success'] == true 
                        ? Colors.green 
                        : Colors.red,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '${result['skill'] ?? 'Unknown'}: ${result['roll'] ?? 0}/${result['difficulty'] ?? 0}',
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
            )),
          ],
        ),
      ),
    );
  }

  Widget _buildNoActiveStory(ThemeData theme) {
    return Column(
      children: [
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
          onPressed: _toggleStoryList,
          icon: const Icon(Icons.play_arrow),
          label: const Text('Choose Adventure'),
        ),
      ],
    );
  }

  Widget _buildStorySelection(ThemeData theme) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Available Stories', style: theme.textTheme.titleLarge),
            IconButton(
              onPressed: _toggleStoryList,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // Filter Controls
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12.0),
            child: Column(
              children: [
                // Story Type Filter
                Row(
                  children: [
                    const Text('Type: '),
                    const SizedBox(width: 8),
                    FilterChip(
                      label: const Text('All'),
                      selected: _selectedStoryType == null,
                      onSelected: (selected) {
                        setState(() {
                          _selectedStoryType = selected ? null : _selectedStoryType;
                        });
                      },
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      label: const Text('One-time'),
                      selected: _selectedStoryType == 'one-time',
                      onSelected: (selected) {
                        setState(() {
                          _selectedStoryType = selected ? 'one-time' : null;
                        });
                      },
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      label: const Text('Daily'),
                      selected: _selectedStoryType == 'daily',
                      onSelected: (selected) {
                        setState(() {
                          _selectedStoryType = selected ? 'daily' : null;
                        });
                      },
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      label: const Text('Repeatable'),
                      selected: _selectedStoryType == 'repeatable',
                      onSelected: (selected) {
                        setState(() {
                          _selectedStoryType = selected ? 'repeatable' : null;
                        });
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                // Availability Filter
                Row(
                  children: [
                    Checkbox(
                      value: _showOnlyAvailable,
                      onChanged: (value) {
                        setState(() {
                          _showOnlyAvailable = value ?? false;
                        });
                      },
                    ),
                    const Text('Show only available stories'),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        if (_storiesFuture == null)
          const CircularProgressIndicator()
        else
          FutureBuilder<List<StoryMetadata>>(
            future: _storiesFuture,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const CircularProgressIndicator();
              }

              if (snapshot.hasError) {
                return Column(
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Colors.red),
                    const SizedBox(height: 8),
                    Text('Failed to load stories'),
                    TextButton(
                      onPressed: _loadStories,
                      child: const Text('Retry'),
                    ),
                  ],
                );
              }

              final allStories = snapshot.data ?? [];
              
              // Apply filters
              final filteredStories = allStories.where((story) {
                // Type filter
                if (_selectedStoryType != null && story.type.toLowerCase() != _selectedStoryType) {
                  return false;
                }
                // Availability filter
                if (_showOnlyAvailable && !story.available) {
                  return false;
                }
                return true;
              }).toList();
              
              // Sort by availability, then by type
              filteredStories.sort((a, b) {
                if (a.available != b.available) {
                  return a.available ? -1 : 1; // Available stories first
                }
                return a.type.compareTo(b.type);
              });
              
              if (filteredStories.isEmpty) {
                return Column(
                  children: [
                    Icon(
                      Icons.book_outlined,
                      size: 48,
                      color: theme.colorScheme.outline,
                    ),
                    const SizedBox(height: 8),
                    Text(_showOnlyAvailable || _selectedStoryType != null 
                        ? 'No stories match your filters' 
                        : 'No stories available'),
                  ],
                );
              }

              return Column(
                children: filteredStories.map((story) => 
                  _StoryCard(
                    story: story,
                    onTap: story.available
                        ? () => _startStory(story)
                        : null,
                  ),
                ).toList(),
              );
            },
          ),
      ],
    );
  }

  Future<void> _initiateRest() async {
    try {
      // Show loading indicator
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Row(
            children: [
              CircularProgressIndicator(strokeWidth: 2),
              SizedBox(width: 16),
              Text('Initiating rest...'),
            ],
          ),
          duration: Duration(seconds: 30),
        ),
      );

      // Call rest API
      await _apiService.rest(widget.character.id);
      
      // Clear the loading snackbar
      if (mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
      }
      
      // Show success message
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Rest initiated. You will heal over time.'),
            backgroundColor: Colors.green,
          ),
        );
      }
      
      // Reload current story to show the rest segment
      await _loadCurrentStory();
      
    } catch (e) {
      // Clear any existing snackbars
      if (mounted) {
        ScaffoldMessenger.of(context).clearSnackBars();
      }
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to initiate rest: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _abandonStory() async {
    // Show confirmation dialog
    final confirm = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Abandon Story?'),
          content: const Text(
            'Are you sure you want to abandon this story? Your progress will be lost.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Abandon'),
            ),
          ],
        );
      },
    );

    if (confirm != true) return;

    try {
      // Call abandon story API
      final result = await _apiService.abandonStory(widget.character.id);
      
      // Check if abandonment was successful
      if (result['Abandoned'] == true) {
        // Clear local story state
        setState(() {
          widget.character.storyState = null;
        });

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Story "${result['storyTitle']}" abandoned successfully'),
            ),
          );
        }
        
        // Reload story state
        await _loadCurrentStory();
      } else {
        throw Exception('Server did not confirm story abandonment');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to abandon story: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _startStory(StoryMetadata story) async {
    try {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Starting ${story.title}...'),
        ),
      );

      // Call API to start the story
      final segment = await _apiService.startStory(
        characterId: widget.character.id,
        storyId: story.storyID,
      );

      // Check if widget is still mounted before using context
      if (!mounted) return;

      // Update character's story state with the segment info
      setState(() {
        widget.character.storyState = {
          'storyId': story.storyID,
          'storyName': story.title,
          'segmentId': JsonUtils.getFlexible<String>(segment, 'SegmentId', 'segmentId'),
          'segmentType': JsonUtils.getFlexible<String>(segment, 'Type', 'type'),
          'segmentName': JsonUtils.getFlexible<String>(segment, 'ShortStatus', 'shortStatus') ?? 'In progress',
          'timeRemaining': JsonUtils.getFlexible<int>(segment, 'TimeRemaining', 'timeRemaining'),
        };
        _showStoryList = false;
      });

      // Show success message
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Started: ${story.title}'),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to start story: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
}

class _StoryCard extends StatelessWidget {
  final StoryMetadata story;
  final VoidCallback? onTap;

  const _StoryCard({
    required this.story,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isAvailable = story.available;
    
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      story.title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: isAvailable
                            ? null
                            : theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  if (!isAvailable)
                    Icon(
                      Icons.lock_outline,
                      size: 20,
                      color: theme.colorScheme.outline,
                    ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                story.description,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  _StoryTypeChip(type: story.type),
                  const SizedBox(width: 8),
                  Icon(
                    Icons.timer_outlined,
                    size: 14,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${story.estimatedDuration ~/ 60} min',
                    style: theme.textTheme.labelSmall,
                  ),
                  if (!isAvailable && story.cooldownRemaining > 0) ...[
                    const SizedBox(width: 8),
                    Icon(
                      Icons.schedule,
                      size: 14,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _formatCooldown(story.cooldownRemaining),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.error,
                      ),
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

  String _formatCooldown(int seconds) {
    if (seconds < 60) {
      return '$seconds sec';
    } else if (seconds < 3600) {
      return '${seconds ~/ 60} min';
    } else if (seconds < 86400) {
      return '${seconds ~/ 3600} hr';
    } else {
      return '${seconds ~/ 86400} days';
    }
  }
}

class _StoryTypeChip extends StatelessWidget {
  final String type;

  const _StoryTypeChip({required this.type});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    Color backgroundColor;
    IconData icon;
    
    switch (type.toLowerCase()) {
      case 'one-time':
        backgroundColor = theme.colorScheme.primaryContainer;
        icon = Icons.stars;
        break;
      case 'daily':
        backgroundColor = theme.colorScheme.secondaryContainer;
        icon = Icons.today;
        break;
      case 'repeatable':
        backgroundColor = theme.colorScheme.tertiaryContainer;
        icon = Icons.refresh;
        break;
      default:
        backgroundColor = theme.colorScheme.surfaceContainerHighest;
        icon = Icons.help_outline;
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12),
          const SizedBox(width: 2),
          Text(
            type,
            style: theme.textTheme.labelSmall,
          ),
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

    // Debug logging
    debugPrint('InventoryPanel - inventory: ${character.inventory}');
    debugPrint('InventoryPanel - inventoryDetails: ${character.inventoryDetails}');
    debugPrint('InventoryPanel - resources: ${character.resources}');

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
            ...character.resources.entries.map(
              (entry) => Padding(
                padding: const EdgeInsets.only(bottom: 4.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(_formatResourceName(entry.key)),
                    Text(entry.value.toString()),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Equipment - Use enriched data if available
          if (character.inventory.isNotEmpty || character.inventoryDetails.isNotEmpty) ...[
            Text('Equipment', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ..._buildEquipmentList(),
          ],
        ],
      ),
    );
  }

  List<Widget> _buildEquipmentList() {
    // Use enriched inventory details if available
    if (character.inventoryDetails.isNotEmpty) {
      return character.inventoryDetails.entries.map((entry) {
        final slot = entry.key;
        final itemData = entry.value as Map<String, dynamic>?;
        
        if (itemData == null) {
          return const SizedBox.shrink();
        }
        
        return Padding(
          padding: const EdgeInsets.only(bottom: 8.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 80,
                child: Text(
                  _formatSlotName(slot),
                  style: const TextStyle(fontWeight: FontWeight.w500),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      itemData['name'] ?? 'Unknown Item',
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                    if (itemData['description'] != null && itemData['description'].toString().isNotEmpty)
                      Text(
                        itemData['description'],
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey[600],
                        ),
                      ),
                    if (itemData['quantity'] != null && itemData['quantity'] > 1)
                      Text(
                        'Quantity: ${itemData['quantity']}',
                        style: const TextStyle(fontSize: 12),
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList();
    } else {
      // Fallback to simple item IDs
      return character.inventory.entries.map(
        (entry) => Padding(
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
        ),
      ).toList();
    }
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
