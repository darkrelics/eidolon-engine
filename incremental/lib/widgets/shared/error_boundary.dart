import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

/// Error boundary widget that catches and displays errors gracefully
class ErrorBoundary extends StatefulWidget {
  final Widget child;
  final Widget Function(FlutterErrorDetails)? errorBuilder;
  final void Function(FlutterErrorDetails)? onError;

  const ErrorBoundary({
    super.key,
    required this.child,
    this.errorBuilder,
    this.onError,
  });

  @override
  State<ErrorBoundary> createState() => _ErrorBoundaryState();
}

class _ErrorBoundaryState extends State<ErrorBoundary> {
  FlutterErrorDetails? _errorDetails;

  @override
  void initState() {
    super.initState();
    _setupErrorHandling();
  }

  void _setupErrorHandling() {
    FlutterError.onError = (FlutterErrorDetails details) {
      if (mounted) {
        setState(() {
          _errorDetails = details;
        });
        widget.onError?.call(details);
      }
      
      // Log error in debug mode
      if (kDebugMode) {
        FlutterError.presentError(details);
      }
    };
  }

  void _resetError() {
    setState(() {
      _errorDetails = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_errorDetails != null) {
      return widget.errorBuilder?.call(_errorDetails!) ??
          DefaultErrorWidget(
            errorDetails: _errorDetails!,
            onRetry: _resetError,
          );
    }

    return widget.child;
  }
}

/// Default error widget display
class DefaultErrorWidget extends StatelessWidget {
  final FlutterErrorDetails errorDetails;
  final VoidCallback? onRetry;

  const DefaultErrorWidget({
    super.key,
    required this.errorDetails,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Scaffold(
      body: Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 400),
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: theme.colorScheme.errorContainer,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.error_outline,
                  size: 48,
                  color: theme.colorScheme.onErrorContainer,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'Something went wrong',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'An unexpected error occurred. Please try again.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
              if (kDebugMode) ...[
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SelectableText(
                    _getErrorMessage(),
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                      color: theme.colorScheme.error,
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 24),
              if (onRetry != null)
                FilledButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Try Again'),
                ),
            ],
          ),
        ),
      ),
    );
  }

  String _getErrorMessage() {
    String message = errorDetails.exception.toString();
    if (message.length > 200) {
      message = '${message.substring(0, 200)}...';
    }
    return message;
  }
}

/// Widget-level error handler
class WidgetErrorBoundary extends StatelessWidget {
  final Widget child;
  final String? fallbackMessage;

  const WidgetErrorBoundary({
    super.key,
    required this.child,
    this.fallbackMessage,
  });

  @override
  Widget build(BuildContext context) {
    return Builder(
      builder: (context) {
        try {
          return child;
        } catch (error, stackTrace) {
          // Log error in debug mode
          if (kDebugMode) {
            debugPrint('Widget Error: $error');
            debugPrintStack(stackTrace: stackTrace);
          }

          return _buildErrorWidget(context, error);
        }
      },
    );
  }

  Widget _buildErrorWidget(BuildContext context, Object error) {
    final theme = Theme.of(context);
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: theme.colorScheme.error.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.warning,
            color: theme.colorScheme.error,
            size: 32,
          ),
          const SizedBox(height: 8),
          Text(
            fallbackMessage ?? 'Unable to load content',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.error,
            ),
            textAlign: TextAlign.center,
          ),
          if (kDebugMode) ...[
            const SizedBox(height: 8),
            Text(
              error.toString(),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onErrorContainer,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}