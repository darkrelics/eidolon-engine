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
import 'package:flutter/material.dart';
import 'auth_state.dart';

/// Monitors user sessions for security
class SessionMonitor {
  static const Duration _inactivityTimeout = Duration(minutes: 30);
  static const Duration _absoluteTimeout = Duration(hours: 24);
  
  Timer? _inactivityTimer;
  Timer? _absoluteTimer;
  DateTime? _sessionStartTime;
  DateTime? _lastActivityTime;
  AuthState? _authState;
  BuildContext? _context;
  
  /// Starts monitoring the session
  void startMonitoring(BuildContext context, AuthState authState) {
    _context = context;
    _authState = authState;
    _sessionStartTime = DateTime.now();
    _lastActivityTime = DateTime.now();
    
    _startInactivityTimer();
    _startAbsoluteTimer();
  }
  
  /// Stops monitoring the session
  void stopMonitoring() {
    _inactivityTimer?.cancel();
    _absoluteTimer?.cancel();
    _inactivityTimer = null;
    _absoluteTimer = null;
    _sessionStartTime = null;
    _lastActivityTime = null;
    _authState = null;
    _context = null;
  }
  
  /// Registers activity to reset inactivity timer
  void registerActivity() {
    _lastActivityTime = DateTime.now();
    _resetInactivityTimer();
  }
  
  /// Starts the inactivity timer
  void _startInactivityTimer() {
    _inactivityTimer?.cancel();
    _inactivityTimer = Timer(_inactivityTimeout, _handleInactivityTimeout);
  }
  
  /// Resets the inactivity timer
  void _resetInactivityTimer() {
    _inactivityTimer?.cancel();
    _startInactivityTimer();
  }
  
  /// Starts the absolute session timer
  void _startAbsoluteTimer() {
    _absoluteTimer?.cancel();
    _absoluteTimer = Timer(_absoluteTimeout, _handleAbsoluteTimeout);
  }
  
  /// Handles inactivity timeout
  void _handleInactivityTimeout() {
    _showTimeoutDialog('Your session has expired due to inactivity');
  }
  
  /// Handles absolute session timeout
  void _handleAbsoluteTimeout() {
    _showTimeoutDialog('Your session has expired for security reasons');
  }
  
  /// Shows timeout dialog and logs out user
  void _showTimeoutDialog(String message) {
    if (_context != null && _authState != null) {
      showDialog(
        context: _context!,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          title: const Text('Session Expired'),
          content: Text(message),
          actions: [
            FilledButton(
              onPressed: () async {
                Navigator.of(context).pop();
                await _authState!.signOut();
                if (_context!.mounted) {
                  Navigator.of(_context!).pushReplacementNamed('/login');
                }
              },
              child: const Text('OK'),
            ),
          ],
        ),
      );
    }
  }
  
  /// Checks if the session is still valid
  bool isSessionValid() {
    if (_sessionStartTime == null || _lastActivityTime == null) {
      return false;
    }
    
    final now = DateTime.now();
    final absoluteDuration = now.difference(_sessionStartTime!);
    final inactiveDuration = now.difference(_lastActivityTime!);
    
    return absoluteDuration < _absoluteTimeout && 
           inactiveDuration < _inactivityTimeout;
  }
  
  /// Gets remaining session time
  Duration getRemainingSessionTime() {
    if (_sessionStartTime == null) return Duration.zero;
    
    final now = DateTime.now();
    final absoluteDuration = now.difference(_sessionStartTime!);
    return _absoluteTimeout - absoluteDuration;
  }
  

}

/// Widget that monitors user activity
class ActivityMonitor extends StatefulWidget {
  final Widget child;
  final SessionMonitor sessionMonitor;

  const ActivityMonitor({
    super.key,
    required this.child,
    required this.sessionMonitor,
  });

  @override
  State<ActivityMonitor> createState() => _ActivityMonitorState();
}

class _ActivityMonitorState extends State<ActivityMonitor> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => widget.sessionMonitor.registerActivity(),
      onPanUpdate: (_) => widget.sessionMonitor.registerActivity(),
      behavior: HitTestBehavior.translucent,
      child: Listener(
        onPointerDown: (_) => widget.sessionMonitor.registerActivity(),
        onPointerMove: (_) => widget.sessionMonitor.registerActivity(),
        child: widget.child,
      ),
    );
  }
}