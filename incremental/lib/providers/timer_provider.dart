// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import 'dart:async';

import 'package:flutter/foundation.dart';

/// Global timer provider that manages a single timer for all segment timers
/// to prevent performance issues from multiple simultaneous setState calls
class TimerProvider extends ChangeNotifier {
  // 1 second interval ensures smooth countdown timers without choppy jumps
  static const Duration _updateInterval = Duration(seconds: 1);

  Timer? _timer;
  DateTime _lastUpdate = DateTime.now();
  bool _isActive = false;
  int _listenerCount = 0;

  /// The current time that all timers should use for calculations
  DateTime get currentTime => _lastUpdate;

  /// Whether the global timer is currently running
  bool get isActive => _isActive;

  @override
  void addListener(VoidCallback listener) {
    super.addListener(listener);
    _listenerCount++;
    // Auto-start timer when first listener is added
    if (_listenerCount == 1) {
      startTimer();
    }
  }

  @override
  void removeListener(VoidCallback listener) {
    super.removeListener(listener);
    _listenerCount--;
    // Auto-stop timer when last listener is removed
    if (_listenerCount == 0) {
      stopTimer();
    }
  }

  /// Starts the global timer if not already running
  void startTimer() {
    if (_isActive) return;

    _isActive = true;
    _lastUpdate = DateTime.now();

    _timer = Timer.periodic(_updateInterval, (_) {
      _lastUpdate = DateTime.now();
      notifyListeners();
    });

    debugPrint('TimerProvider: Global timer started');
  }

  /// Stops the global timer
  void stopTimer() {
    if (!_isActive) return;

    _timer?.cancel();
    _timer = null;
    _isActive = false;

    debugPrint('TimerProvider: Global timer stopped');
  }

  /// Gets the remaining seconds until the given end time
  int getRemainingSeconds(DateTime endTime) {
    final difference = endTime.difference(_lastUpdate);
    return difference.inSeconds > 0 ? difference.inSeconds : 0;
  }

  /// Gets the progress (0.0 to 1.0) between start and end times
  double getProgress(DateTime startTime, DateTime endTime) {
    final totalDurationMs = endTime.difference(startTime).inMilliseconds;
    final elapsedMs = _lastUpdate.difference(startTime).inMilliseconds;

    if (totalDurationMs <= 0) return 0.0;
    return (elapsedMs / totalDurationMs).clamp(0.0, 1.0);
  }

  @override
  void dispose() {
    stopTimer();
    super.dispose();
  }
}
