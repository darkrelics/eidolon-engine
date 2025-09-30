import 'dart:async';
import 'package:flutter/material.dart';

/// A simple countdown timer widget that updates every second
class CountdownTimer extends StatefulWidget {
  final int initialSeconds;
  final VoidCallback? onComplete;
  final TextStyle? textStyle;

  const CountdownTimer({
    super.key,
    required this.initialSeconds,
    this.onComplete,
    this.textStyle,
  });

  @override
  State<CountdownTimer> createState() => _CountdownTimerState();
}

class _CountdownTimerState extends State<CountdownTimer> {
  late int _remainingSeconds;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _remainingSeconds = widget.initialSeconds;
    if (_remainingSeconds > 0) {
      _startTimer();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }

      setState(() {
        _remainingSeconds--;
      });

      if (_remainingSeconds <= 0) {
        timer.cancel();
        widget.onComplete?.call();
      }
    });
  }

  String _formatTime(int seconds) {
    if (seconds <= 0) return '00:00';

    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Text(_formatTime(_remainingSeconds), style: widget.textStyle);
  }
}
