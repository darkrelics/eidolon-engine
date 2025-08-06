import 'package:flutter/material.dart';

/// A reusable loading dialog widget
class LoadingDialog extends StatelessWidget {
  final String title;
  final String message;
  final String? subtitle;

  const LoadingDialog({
    super.key,
    required this.title,
    required this.message,
    this.subtitle,
  });

  /// Show the loading dialog
  static Future<void> show({
    required BuildContext context,
    required String title,
    required String message,
    String? subtitle,
    bool barrierDismissible = false,
  }) {
    return showDialog(
      context: context,
      barrierDismissible: barrierDismissible,
      builder: (BuildContext context) {
        return LoadingDialog(
          title: title,
          message: message,
          subtitle: subtitle,
        );
      },
    );
  }

  /// Hide the loading dialog
  static void hide(BuildContext context) {
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return AlertDialog(
      title: Text(
        title,
        style: theme.textTheme.headlineSmall,
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 24),
          Text(
            message,
            style: theme.textTheme.bodyLarge,
            textAlign: TextAlign.center,
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 8),
            Text(
              subtitle!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}

/// A more advanced loading dialog with progress updates
class ProgressLoadingDialog extends StatefulWidget {
  final String title;
  final Stream<LoadingProgress> progressStream;
  final VoidCallback? onCancel;

  const ProgressLoadingDialog({
    super.key,
    required this.title,
    required this.progressStream,
    this.onCancel,
  });

  @override
  State<ProgressLoadingDialog> createState() => _ProgressLoadingDialogState();
}

class _ProgressLoadingDialogState extends State<ProgressLoadingDialog> {
  LoadingProgress _currentProgress = LoadingProgress(
    message: 'Initializing...',
    progress: 0.0,
  );

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AlertDialog(
      title: Text(
        widget.title,
        style: theme.textTheme.headlineSmall,
      ),
      content: StreamBuilder<LoadingProgress>(
        stream: widget.progressStream,
        initialData: _currentProgress,
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            _currentProgress = snapshot.data!;
          }

          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_currentProgress.progress != null)
                LinearProgressIndicator(
                  value: _currentProgress.progress,
                )
              else
                const CircularProgressIndicator(),
              const SizedBox(height: 24),
              Text(
                _currentProgress.message,
                style: theme.textTheme.bodyLarge,
                textAlign: TextAlign.center,
              ),
              if (_currentProgress.subtitle != null) ...[
                const SizedBox(height: 8),
                Text(
                  _currentProgress.subtitle!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ],
          );
        },
      ),
      actions: widget.onCancel != null
          ? [
              TextButton(
                onPressed: widget.onCancel,
                child: const Text('Cancel'),
              ),
            ]
          : null,
    );
  }
}

/// Progress data for loading operations
class LoadingProgress {
  final String message;
  final String? subtitle;
  final double? progress; // 0.0 to 1.0, null for indeterminate

  LoadingProgress({
    required this.message,
    this.subtitle,
    this.progress,
  });
}