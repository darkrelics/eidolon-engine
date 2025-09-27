import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// A wrapper widget that handles common UI states
class StateWrapper extends StatelessWidget {
  final bool isLoading;
  final String? error;
  final bool isEmpty;
  final Widget child;
  final VoidCallback? onRetry;
  final String? emptyMessage;
  final String? emptyTitle;
  final IconData? emptyIcon;
  final Widget? loadingWidget;
  final Widget? errorWidget;
  final Widget? emptyWidget;
  final bool showLoadingOverlay;

  const StateWrapper({
    super.key,
    required this.child,
    this.isLoading = false,
    this.error,
    this.isEmpty = false,
    this.onRetry,
    this.emptyMessage,
    this.emptyTitle,
    this.emptyIcon,
    this.loadingWidget,
    this.errorWidget,
    this.emptyWidget,
    this.showLoadingOverlay = false,
  });

  @override
  Widget build(BuildContext context) {
    // Show error state
    if (error != null && error!.isNotEmpty) {
      return errorWidget ?? _buildDefaultError(context);
    }

    // Show empty state
    if (isEmpty && !isLoading) {
      return emptyWidget ?? _buildDefaultEmpty(context);
    }

    // Show loading state
    if (isLoading && !showLoadingOverlay) {
      return loadingWidget ?? _buildDefaultLoading(context);
    }

    // Show content with optional loading overlay
    if (showLoadingOverlay && isLoading) {
      return Stack(children: [child, _buildLoadingOverlay(context)]);
    }

    // Show content
    return child;
  }

  Widget _buildDefaultLoading(BuildContext context) {
    return Center(
      child:
          Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(
                    'Loading...',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              )
              .animate()
              .fadeIn(duration: 300.ms)
              .scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1)),
    );
  }

  Widget _buildDefaultError(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 64, color: theme.colorScheme.error)
                .animate()
                .fadeIn()
                .scale(begin: const Offset(0.8, 0.8), end: const Offset(1, 1)),
            const SizedBox(height: 16),
            Text(
              'Something went wrong',
              style: theme.textTheme.headlineSmall?.copyWith(
                color: theme.colorScheme.error,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              error!,
              style: theme.textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Try Again'),
              ),
            ],
          ],
        ).animate().fadeIn(duration: 300.ms).slideY(begin: 0.1, end: 0),
      ),
    );
  }

  Widget _buildDefaultEmpty(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              emptyIcon ?? Icons.inbox,
              size: 64,
              color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
            ).animate().fadeIn().scale(
              begin: const Offset(0.8, 0.8),
              end: const Offset(1, 1),
            ),
            const SizedBox(height: 16),
            Text(
              emptyTitle ?? 'No Data',
              style: theme.textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            if (emptyMessage != null) ...[
              const SizedBox(height: 8),
              Text(
                emptyMessage!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Refresh'),
              ),
            ],
          ],
        ).animate().fadeIn(duration: 300.ms).slideY(begin: 0.1, end: 0),
      ),
    );
  }

  Widget _buildLoadingOverlay(BuildContext context) {
    return Positioned.fill(
      child: Container(
        color: Colors.black.withValues(alpha: 0.3),
        child: Center(
          child:
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(height: 16),
                      Text(
                        'Please wait...',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
              ).animate().fadeIn().scale(
                begin: const Offset(0.9, 0.9),
                end: const Offset(1, 1),
              ),
        ),
      ),
    );
  }
}

/// A more advanced state wrapper with builder pattern
class StateWrapperBuilder<T> extends StatelessWidget {
  final Future<T>? future;
  final T? data;
  final bool isLoading;
  final String? error;
  final Widget Function(BuildContext context, T data) builder;
  final Widget Function(BuildContext context)? loadingBuilder;
  final Widget Function(BuildContext context, String error)? errorBuilder;
  final Widget Function(BuildContext context)? emptyBuilder;
  final bool Function(T? data)? isEmpty;
  final VoidCallback? onRetry;

  const StateWrapperBuilder({
    super.key,
    this.future,
    this.data,
    this.isLoading = false,
    this.error,
    required this.builder,
    this.loadingBuilder,
    this.errorBuilder,
    this.emptyBuilder,
    this.isEmpty,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    // If future is provided, use FutureBuilder
    if (future != null) {
      return FutureBuilder<T>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return loadingBuilder?.call(context) ??
                const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return errorBuilder?.call(context, snapshot.error.toString()) ??
                StateWrapper(
                  error: snapshot.error.toString(),
                  onRetry: onRetry,
                  child: const SizedBox(),
                );
          }

          final data = snapshot.data;
          if (data == null || (isEmpty?.call(data) ?? false)) {
            return emptyBuilder?.call(context) ??
                StateWrapper(
                  isEmpty: true,
                  onRetry: onRetry,
                  child: const SizedBox(),
                );
          }

          return builder(context, data);
        },
      );
    }

    // Use provided state
    if (error != null) {
      return errorBuilder?.call(context, error!) ??
          StateWrapper(error: error, onRetry: onRetry, child: const SizedBox());
    }

    if (isLoading) {
      return loadingBuilder?.call(context) ??
          const Center(child: CircularProgressIndicator());
    }

    final currentData = data;
    if (currentData == null || (isEmpty?.call(currentData) ?? false)) {
      return emptyBuilder?.call(context) ??
          StateWrapper(
            isEmpty: true,
            onRetry: onRetry,
            child: const SizedBox(),
          );
    }

    return builder(context, currentData);
  }
}
