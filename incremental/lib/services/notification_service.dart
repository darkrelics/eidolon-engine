import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Service for showing in-app notifications
class NotificationService {
  static void showSegmentComplete(
    BuildContext context, {
    required String segmentType,
    String? outcome,
  }) {
    final message = _getCompletionMessage(segmentType, outcome);
    final icon = _getCompletionIcon(segmentType, outcome);
    final color = _getCompletionColor(segmentType, outcome);

    showCustomNotification(
      context,
      message: message,
      icon: icon,
      color: color,
      duration: const Duration(seconds: 3),
    );
  }

  static void showStoryComplete(
    BuildContext context, {
    required String storyTitle,
    required String outcome,
  }) {
    showCustomNotification(
      context,
      message: 'Story Completed: $storyTitle',
      subtitle: 'Outcome: $outcome',
      icon: Icons.auto_stories,
      color: Colors.purple,
      duration: const Duration(seconds: 4),
    );
  }

  static void showReward(
    BuildContext context, {
    required String type,
    required dynamic value,
  }) {
    final icon = _getRewardIcon(type);
    final color = _getRewardColor(type);

    showCustomNotification(
      context,
      message: 'Reward Earned!',
      subtitle: '+$value $type',
      icon: icon,
      color: color,
      duration: const Duration(seconds: 2),
    );
  }

  static void showError(BuildContext context, {required String message}) {
    showCustomNotification(
      context,
      message: 'Error',
      subtitle: message,
      icon: Icons.error_outline,
      color: Colors.red,
      duration: const Duration(seconds: 3),
    );
  }

  static void showCustomNotification(
    BuildContext context, {
    required String message,
    String? subtitle,
    IconData? icon,
    Color? color,
    Duration duration = const Duration(seconds: 3),
  }) {
    final overlay = Overlay.of(context);
    final theme = Theme.of(context);

    late OverlayEntry overlayEntry;
    overlayEntry = OverlayEntry(
      builder: (context) => _NotificationOverlay(
        message: message,
        subtitle: subtitle,
        icon: icon ?? Icons.info,
        color: color ?? theme.colorScheme.primary,
        duration: duration,
        onDismiss: () {
          overlayEntry.remove();
        },
      ),
    );

    overlay.insert(overlayEntry);
  }

  static String _getCompletionMessage(String segmentType, String? outcome) {
    switch (segmentType.toLowerCase()) {
      case 'decision':
        return outcome != null
            ? 'Decision Made - $outcome'
            : 'Decision Submitted';
      case 'mechanical':
        return 'Actions Processed';
      case 'narrative':
        return 'Story Progressed';
      default:
        return 'Segment Complete';
    }
  }

  static IconData _getCompletionIcon(String segmentType, String? outcome) {
    switch (segmentType.toLowerCase()) {
      case 'decision':
        return Icons.psychology;
      case 'mechanical':
        return Icons.settings;
      case 'narrative':
        return Icons.auto_stories;
      default:
        return Icons.check_circle;
    }
  }

  static Color _getCompletionColor(String segmentType, String? outcome) {
    if (outcome != null) {
      switch (outcome.toLowerCase()) {
        case 'success':
        case 'exceptional':
          return Colors.green;
        case 'failure':
          return Colors.red;
        case 'normal':
          return Colors.blue;
        default:
          return Colors.grey;
      }
    }

    switch (segmentType.toLowerCase()) {
      case 'decision':
        return Colors.blue;
      case 'mechanical':
        return Colors.orange;
      case 'narrative':
        return Colors.purple;
      default:
        return Colors.grey;
    }
  }

  static IconData _getRewardIcon(String type) {
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

  static Color _getRewardColor(String type) {
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

class _NotificationOverlay extends StatefulWidget {
  final String message;
  final String? subtitle;
  final IconData icon;
  final Color color;
  final Duration duration;
  final VoidCallback onDismiss;

  const _NotificationOverlay({
    required this.message,
    this.subtitle,
    required this.icon,
    required this.color,
    required this.duration,
    required this.onDismiss,
  });

  @override
  State<_NotificationOverlay> createState() => _NotificationOverlayState();
}

class _NotificationOverlayState extends State<_NotificationOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );

    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, -1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

    _controller.forward();

    // Auto-dismiss after duration
    Future.delayed(widget.duration, () {
      if (mounted) {
        _dismiss();
      }
    });
  }

  void _dismiss() {
    _controller.reverse().then((_) {
      if (mounted) {
        widget.onDismiss();
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

    return Positioned(
      top: MediaQuery.of(context).padding.top + 16,
      left: 16,
      right: 16,
      child: SlideTransition(
        position: _slideAnimation,
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: Material(
            elevation: 8,
            borderRadius: BorderRadius.circular(12),
            color: Colors.transparent,
            child: InkWell(
              onTap: _dismiss,
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      theme.colorScheme.surface,
                      theme.colorScheme.surface.withValues(alpha: 0.95),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: widget.color.withValues(alpha: 0.3),
                    width: 2,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: widget.color.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Icon(
                            widget.icon,
                            color: widget.color,
                            size: 24,
                          ),
                        )
                        .animate()
                        .scale(delay: 100.ms)
                        .rotate(delay: 200.ms, duration: 300.ms),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            widget.message,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          if (widget.subtitle != null) ...[
                            const SizedBox(height: 2),
                            Text(
                              widget.subtitle!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    Icon(
                      Icons.close,
                      size: 20,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ],
                ),
              ),
            ),
          ).animate().shimmer(delay: 500.ms, duration: 1000.ms),
        ),
      ),
    );
  }
}
