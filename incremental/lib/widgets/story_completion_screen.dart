import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../providers/segment_provider.dart';

class StoryCompletionScreen extends StatefulWidget {
  final String characterId;
  final String storyTitle;
  final Map<String, dynamic>? storyRewards;
  final VoidCallback? onContinue;

  const StoryCompletionScreen({
    super.key,
    required this.characterId,
    required this.storyTitle,
    this.storyRewards,
    this.onContinue,
  });

  @override
  State<StoryCompletionScreen> createState() => _StoryCompletionScreenState();
}

class _StoryCompletionScreenState extends State<StoryCompletionScreen> 
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _scaleAnimation;
  bool _isStartingNewStory = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeIn,
    );

    _scaleAnimation = Tween<double>(
      begin: 0.8,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.elasticOut,
    ));

    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _startNewStory() async {
    setState(() {
      _isStartingNewStory = true;
      _errorMessage = null;
    });

    try {
      final apiService = context.read<ApiService>();
      final segmentProvider = context.read<SegmentProvider>();
      
      // Get available stories
      final stories = await apiService.getStories(widget.characterId);
      
      if (stories.isEmpty) {
        throw Exception('No stories available');
      }
      
      // Start the first available story
      await apiService.startStory(
        characterId: widget.characterId,
        storyId: stories.first.storyID,
      );
      
      // Reload the current story/segment
      await segmentProvider.loadCurrentStory(widget.characterId);
      
      // Call the continuation callback if provided
      if (widget.onContinue != null) {
        widget.onContinue!();
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to start new story: ${e.toString()}';
      });
    } finally {
      setState(() {
        _isStartingNewStory = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Scaffold(
      backgroundColor: theme.colorScheme.surface,
      body: SafeArea(
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ScaleTransition(
                scale: _scaleAnimation,
                child: Card(
                  elevation: 8,
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 500),
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Victory icon
                        Container(
                          width: 80,
                          height: 80,
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primaryContainer,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            Icons.emoji_events,
                            size: 48,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        
                        // Title
                        Text(
                          'Story Complete!',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        
                        // Story title
                        Text(
                          widget.storyTitle,
                          style: theme.textTheme.titleLarge,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 32),
                        
                        // Rewards section
                        if (widget.storyRewards != null && 
                            widget.storyRewards!.isNotEmpty) ...[
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.secondaryContainer
                                  .withValues(alpha: 0.3),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Icon(
                                      Icons.card_giftcard,
                                      color: theme.colorScheme.secondary,
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      'Rewards Earned',
                                      style: theme.textTheme.titleMedium?.copyWith(
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                _buildRewardsList(widget.storyRewards!),
                              ],
                            ),
                          ),
                          const SizedBox(height: 24),
                        ],
                        
                        // Error message
                        if (_errorMessage != null)
                          Container(
                            margin: const EdgeInsets.only(bottom: 16),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.errorContainer,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  Icons.error_outline,
                                  color: theme.colorScheme.onErrorContainer,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _errorMessage!,
                                    style: TextStyle(
                                      color: theme.colorScheme.onErrorContainer,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        
                        // Continue button
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            onPressed: _isStartingNewStory ? null : _startNewStory,
                            icon: _isStartingNewStory
                                ? const SizedBox(
                                    width: 20,
                                    height: 20,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.play_arrow),
                            label: Text(
                              _isStartingNewStory 
                                  ? 'Starting...' 
                                  : 'Start New Adventure',
                            ),
                            style: ElevatedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 24,
                                vertical: 12,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRewardsList(Map<String, dynamic> rewards) {
    final theme = Theme.of(context);
    final rewardWidgets = <Widget>[];

    // Experience rewards
    if (rewards['experience'] != null) {
      final xp = rewards['experience'] as Map<String, dynamic>;
      xp.forEach((skill, amount) {
        rewardWidgets.add(
          _buildRewardItem(
            Icons.trending_up,
            '$skill: +$amount XP',
            Colors.green,
          ),
        );
      });
    }

    // Item rewards
    if (rewards['items'] != null) {
      final items = rewards['items'] as List;
      for (final item in items) {
        rewardWidgets.add(
          _buildRewardItem(
            Icons.inventory_2,
            item['name'] ?? 'Unknown Item',
            Colors.blue,
          ),
        );
      }
    }

    // Currency rewards
    if (rewards['currency'] != null) {
      final currency = rewards['currency'] as Map<String, dynamic>;
      currency.forEach((type, amount) {
        rewardWidgets.add(
          _buildRewardItem(
            Icons.monetization_on,
            '$type: +$amount',
            Colors.amber,
          ),
        );
      });
    }

    // If no rewards, show a default message
    if (rewardWidgets.isEmpty) {
      rewardWidgets.add(
        Text(
          'Experience gained from your journey',
          style: theme.textTheme.bodyMedium?.copyWith(
            fontStyle: FontStyle.italic,
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: rewardWidgets,
    );
  }

  Widget _buildRewardItem(IconData icon, String text, Color iconColor) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Icon(
            icon,
            size: 20,
            color: iconColor,
          ),
          const SizedBox(width: 8),
          Text(
            text,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}