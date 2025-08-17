import 'dart:async';
import 'package:flutter/material.dart';

/// Widget showing progress for mechanical segments
class MechanicalSegmentProgress extends StatefulWidget {
  final String status;
  final String? processingStatus;
  final Duration estimatedDuration;
  final VoidCallback? onComplete;

  const MechanicalSegmentProgress({
    super.key,
    required this.status,
    this.processingStatus,
    this.estimatedDuration = const Duration(minutes: 1),
    this.onComplete,
  });

  @override
  State<MechanicalSegmentProgress> createState() => _MechanicalSegmentProgressState();
}

class _MechanicalSegmentProgressState extends State<MechanicalSegmentProgress>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _progressAnimation;
  Timer? _timer;
  int _elapsedSeconds = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.estimatedDuration,
    );
    _progressAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    ));

    if (widget.processingStatus == 'processing') {
      _startProgress();
    }
  }

  void _startProgress() {
    _controller.forward();
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _elapsedSeconds++;
        });
      }
    });

    _controller.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        widget.onComplete?.call();
      }
    });
  }

  @override
  void didUpdateWidget(MechanicalSegmentProgress oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.processingStatus == 'processed' && 
        oldWidget.processingStatus == 'processing') {
      _controller.stop();
      _timer?.cancel();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _timer?.cancel();
    super.dispose();
  }

  String _formatTime(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isProcessing = widget.processingStatus == 'processing';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.colorScheme.primaryContainer,
            theme.colorScheme.primaryContainer.withValues(alpha: 0.5),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withValues(alpha: 0.1),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.orange.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  Icons.settings,
                  color: Colors.orange,
                  size: 24,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Mechanical Segment',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onPrimaryContainer,
                      ),
                    ),
                    Text(
                      widget.status,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.8),
                      ),
                    ),
                  ],
                ),
              ),
              if (isProcessing)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.orange.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.orange),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SizedBox(
                        width: 12,
                        height: 12,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.orange),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'PROCESSING',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: Colors.orange,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),

          const SizedBox(height: 20),

          // Progress Bar
          AnimatedBuilder(
            animation: _progressAnimation,
            builder: (context, child) {
              return Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Progress',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.8),
                        ),
                      ),
                      Text(
                        '${(_progressAnimation.value * 100).toInt()}%',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onPrimaryContainer,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: LinearProgressIndicator(
                      value: isProcessing ? _progressAnimation.value : 1.0,
                      minHeight: 12,
                      backgroundColor: theme.colorScheme.onPrimaryContainer.withValues(alpha: 0.2),
                      valueColor: AlwaysStoppedAnimation<Color>(
                        isProcessing ? Colors.orange : Colors.green,
                      ),
                    ),
                  ),
                ],
              );
            },
          ),

          const SizedBox(height: 16),

          // Timer and Status
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              // Elapsed Time
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.timer,
                      size: 16,
                      color: theme.colorScheme.primary,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      _formatTime(_elapsedSeconds),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontFamily: 'monospace',
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),

              // Status Message
              if (widget.processingStatus == 'processed')
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.green.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.green),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.check_circle,
                        size: 16,
                        color: Colors.green,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'COMPLETE',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: Colors.green,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),

          // Processing indicator removed for performance
        ],
      ),
    );
  }
}