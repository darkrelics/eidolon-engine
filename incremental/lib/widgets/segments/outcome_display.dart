import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Animated display for segment outcomes
class AnimatedOutcomeDisplay extends StatefulWidget {
  final Map<String, dynamic> outcome;
  final VoidCallback? onDismiss;

  const AnimatedOutcomeDisplay({
    super.key,
    required this.outcome,
    this.onDismiss,
  });

  @override
  State<AnimatedOutcomeDisplay> createState() => _AnimatedOutcomeDisplayState();
}

class _AnimatedOutcomeDisplayState extends State<AnimatedOutcomeDisplay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  bool _showDetails = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _controller.forward();

    // Auto-show details after initial animation
    Future.delayed(const Duration(milliseconds: 800), () {
      if (mounted) {
        setState(() {
          _showDetails = true;
        });
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final type = widget.outcome['Type'] ?? 'unknown';
    final description = widget.outcome['Description'] ?? '';
    final rewards = widget.outcome['Rewards'] as Map<String, dynamic>?;
    final consequences = widget.outcome['Consequences'] as Map<String, dynamic>?;

    return Container(
      margin: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Outcome Icon Animation
          _OutcomeIcon(type: type)
              .animate()
              .scale(
                duration: 500.ms,
                curve: Curves.elasticOut,
              )
              .then()
              .shake(delay: 100.ms, duration: 300.ms),

          const SizedBox(height: 16),

          // Outcome Title
          Text(
            _getOutcomeTitle(type),
            style: theme.textTheme.headlineMedium?.copyWith(
              color: _getOutcomeColor(type),
              fontWeight: FontWeight.bold,
            ),
          ).animate()
            .fadeIn(delay: 300.ms)
            .slideY(begin: 0.2, end: 0),

          if (description.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                description,
                style: theme.textTheme.bodyLarge,
                textAlign: TextAlign.center,
              ),
            ).animate()
              .fadeIn(delay: 500.ms)
              .slideY(begin: 0.1, end: 0),
          ],

          // Rewards Section
          if (_showDetails && rewards != null && rewards.isNotEmpty) ...[
            const SizedBox(height: 20),
            _RewardsSection(rewards: rewards)
                .animate()
                .fadeIn(delay: 100.ms)
                .slideY(begin: 0.1, end: 0),
          ],

          // Consequences Section
          if (_showDetails && consequences != null && consequences.isNotEmpty) ...[
            const SizedBox(height: 16),
            _ConsequencesSection(consequences: consequences)
                .animate()
                .fadeIn(delay: 200.ms)
                .slideY(begin: 0.1, end: 0),
          ],

          // Continue Button
          if (_showDetails && widget.onDismiss != null) ...[
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: widget.onDismiss,
              icon: const Icon(Icons.arrow_forward),
              label: const Text('Continue'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ).animate()
              .fadeIn(delay: 300.ms)
              .scale(delay: 400.ms),
          ],
        ],
      ),
    );
  }

  String _getOutcomeTitle(String type) {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return 'Success!';
      case 'normal':
        return 'Completed';
      case 'minimal':
        return 'Barely Made It';
      case 'failure':
        return 'Failed';
      case 'death':
        return 'Defeated';
      default:
        return 'Outcome';
    }
  }

  Color _getOutcomeColor(String type) {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Colors.green;
      case 'normal':
        return Colors.blue;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      case 'death':
        return Colors.red.shade900;
      default:
        return Colors.grey;
    }
  }
}

class _OutcomeIcon extends StatelessWidget {
  final String type;

  const _OutcomeIcon({required this.type});

  @override
  Widget build(BuildContext context) {
    final color = _getColor();
    final icon = _getIcon();

    return Container(
      width: 100,
      height: 100,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [
            color.withValues(alpha: 0.2),
            color.withValues(alpha: 0.1),
            color.withValues(alpha: 0.05),
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.3),
            blurRadius: 20,
            spreadRadius: 5,
          ),
        ],
      ),
      child: Icon(
        icon,
        size: 50,
        color: color,
      ).animate(onPlay: (controller) => controller.repeat())
        .shimmer(duration: 2000.ms, color: color.withValues(alpha: 0.5)),
    );
  }

  Color _getColor() {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Colors.green;
      case 'normal':
        return Colors.blue;
      case 'minimal':
        return Colors.orange;
      case 'failure':
        return Colors.red;
      case 'death':
        return Colors.red.shade900;
      default:
        return Colors.grey;
    }
  }

  IconData _getIcon() {
    switch (type.toLowerCase()) {
      case 'success':
      case 'exceptional':
        return Icons.emoji_events;
      case 'normal':
        return Icons.check_circle;
      case 'minimal':
        return Icons.warning;
      case 'failure':
        return Icons.cancel;
      case 'death':
        return Icons.dangerous;
      default:
        return Icons.help_outline;
    }
  }
}

class _RewardsSection extends StatelessWidget {
  final Map<String, dynamic> rewards;

  const _RewardsSection({required this.rewards});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.green.withValues(alpha: 0.1),
            Colors.green.withValues(alpha: 0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.green.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.card_giftcard,
                color: Colors.green,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                'Rewards',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: Colors.green,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: rewards.entries.toList().asMap().entries.map((entry) {
              final index = entry.key;
              final rewardEntry = entry.value;
              return _RewardChip(
                type: rewardEntry.key,
                value: rewardEntry.value,
              ).animate()
                .fadeIn(delay: Duration(milliseconds: 100 * index))
                .scale(delay: Duration(milliseconds: 100 * index));
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _RewardChip extends StatelessWidget {
  final String type;
  final dynamic value;

  const _RewardChip({
    required this.type,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final icon = _getIcon();
    final color = _getColor();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 6),
          Text(
            '+$value',
            style: theme.textTheme.titleSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(width: 4),
          Text(
            type,
            style: theme.textTheme.bodySmall?.copyWith(
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  IconData _getIcon() {
    switch (type.toLowerCase()) {
      case 'xp':
      case 'experience':
        return Icons.trending_up;
      case 'gold':
      case 'coins':
        return Icons.monetization_on;
      case 'item':
      case 'items':
        return Icons.inventory_2;
      case 'health':
        return Icons.favorite;
      case 'essence':
        return Icons.water_drop;
      default:
        return Icons.card_giftcard;
    }
  }

  Color _getColor() {
    switch (type.toLowerCase()) {
      case 'xp':
      case 'experience':
        return Colors.purple;
      case 'gold':
      case 'coins':
        return Colors.orange;
      case 'health':
        return Colors.red;
      case 'essence':
        return Colors.blue;
      default:
        return Colors.grey;
    }
  }
}

class _ConsequencesSection extends StatelessWidget {
  final Map<String, dynamic> consequences;

  const _ConsequencesSection({required this.consequences});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: theme.colorScheme.error.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.warning_amber,
                color: theme.colorScheme.error,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                'Consequences',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: theme.colorScheme.error,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...consequences.entries.map((entry) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Icon(
                      Icons.remove,
                      size: 16,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${entry.key}: ${entry.value}',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.error,
                      ),
                    ),
                  ],
                ),
              )),
        ],
      ),
    );
  }
}