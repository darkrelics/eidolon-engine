import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Overlay widget for showing loading states
class LoadingOverlay extends StatelessWidget {
  final bool isLoading;
  final Widget child;
  final String? message;
  final bool showProgress;

  const LoadingOverlay({
    super.key,
    required this.isLoading,
    required this.child,
    this.message,
    this.showProgress = true,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        child,
        if (isLoading)
          Container(
            color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.8),
            child: Center(
              child: Card(
                elevation: 8,
                child: Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (showProgress)
                        const CircularProgressIndicator()
                            .animate(onPlay: (controller) => controller.repeat())
                            .rotate(duration: 1000.ms),
                      if (message != null) ...[
                        const SizedBox(height: 16),
                        Text(
                          message!,
                          style: Theme.of(context).textTheme.bodyLarge,
                          textAlign: TextAlign.center,
                        ).animate()
                          .fadeIn(delay: 200.ms),
                      ],
                    ],
                  ),
                ),
              ).animate()
                .fadeIn(duration: 200.ms)
                .scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1)),
            ),
          ),
      ],
    );
  }
}

/// Inline loading indicator for smaller components
class InlineLoadingIndicator extends StatelessWidget {
  final String? message;
  final double size;

  const InlineLoadingIndicator({
    super.key,
    this.message,
    this.size = 16.0,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: size,
          height: size,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            valueColor: AlwaysStoppedAnimation<Color>(
              Theme.of(context).colorScheme.primary,
            ),
          ),
        ),
        if (message != null) ...[
          const SizedBox(width: 8),
          Text(
            message!,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    ).animate()
      .fadeIn()
      .slideX(begin: -0.1, end: 0);
  }
}

/// Skeleton loader for content placeholders
class SkeletonLoader extends StatelessWidget {
  final double width;
  final double height;
  final BorderRadius? borderRadius;

  const SkeletonLoader({
    super.key,
    required this.width,
    required this.height,
    this.borderRadius,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: borderRadius ?? BorderRadius.circular(4),
      ),
    ).animate(onPlay: (controller) => controller.repeat())
      .shimmer(duration: 1500.ms, color: Theme.of(context).colorScheme.surface);
  }
}

/// Story card skeleton loader
class StoryCardSkeleton extends StatelessWidget {
  const StoryCardSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const SkeletonLoader(width: 150, height: 20),
                const Spacer(),
                SkeletonLoader(
                  width: 60,
                  height: 24,
                  borderRadius: BorderRadius.circular(12),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const SkeletonLoader(width: double.infinity, height: 14),
            const SizedBox(height: 8),
            const SkeletonLoader(width: double.infinity, height: 14),
            const SizedBox(height: 8),
            const SkeletonLoader(width: 200, height: 14),
            const SizedBox(height: 16),
            Row(
              children: [
                const SkeletonLoader(width: 80, height: 16),
                const Spacer(),
                SkeletonLoader(
                  width: 100,
                  height: 28,
                  borderRadius: BorderRadius.circular(14),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Character panel skeleton loader
class CharacterPanelSkeleton extends StatelessWidget {
  const CharacterPanelSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            const SkeletonLoader(width: 120, height: 24),
            const SizedBox(height: 20),
            
            // Health bar
            const SkeletonLoader(width: double.infinity, height: 8),
            const SizedBox(height: 12),
            
            // Essence bar
            const SkeletonLoader(width: double.infinity, height: 8),
            const SizedBox(height: 20),
            
            // Stats
            for (int i = 0; i < 4; i++) ...[
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: const [
                  SkeletonLoader(width: 80, height: 16),
                  SkeletonLoader(width: 40, height: 16),
                ],
              ),
              const SizedBox(height: 8),
            ],
          ],
        ),
      ),
    );
  }
}

/// List skeleton loader
class ListSkeleton extends StatelessWidget {
  final int itemCount;
  final double itemHeight;
  final EdgeInsetsGeometry? padding;

  const ListSkeleton({
    super.key,
    this.itemCount = 5,
    this.itemHeight = 80,
    this.padding,
  });

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: padding,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: itemCount,
      itemBuilder: (context, index) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: SkeletonLoader(
            width: double.infinity,
            height: itemHeight,
            borderRadius: BorderRadius.circular(8),
          ),
        );
      },
    );
  }
}