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
import 'navigation.dart';

/// Monitors user sessions for security
class SessionMonitor {
  static const Duration _inactivityTimeout = Duration(minutes: 30);
  static const Duration _absoluteTimeout = Duration(hours: 24);

  Timer? _inactivityTimer;
  Timer? _absoluteTimer;
  DateTime? _sessionStartTime;
  DateTime? _lastActivityTime;
  DateTime? _lastServerVerification;
  AuthState? _authState;
  // Instead of storing BuildContext, use a callback for navigation
  void Function()? _onSessionExpired;

  /// Starts monitoring the session
  void startMonitoring(BuildContext context, AuthState authState) {
    // Store auth state but not the context
    _authState = authState;
    _sessionStartTime = DateTime.now();
    _lastActivityTime = DateTime.now();

    // Create a callback that captures Navigator operation
    // This avoids storing the context directly
    _onSessionExpired = () {
      // Only navigate if the context is still mounted
      if (context.mounted) {
        Navigator.of(context).pushReplacementNamed('/login');
      }
    };

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
    _lastServerVerification = null;
    _authState = null;
    _onSessionExpired = null;
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
    // Use BuildContext only from showDialog's builder function, not a stored context
    if (_authState != null && _onSessionExpired != null) {
      // Find the active context using the navigator key
      // This approach avoids storing BuildContext
      final context = GlobalNavigationKey.navigatorKey.currentContext;

      if (context != null && context.mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder:
              (dialogContext) => AlertDialog(
                title: const Text('Session Expired'),
                content: Text(message),
                actions: [
                  FilledButton(
                    onPressed: () async {
                      // Pop using the dialog's context
                      Navigator.of(dialogContext).pop();
                      if (_authState != null) {
                        await _authState.signOut();
                      }
                      // Use callback instead of stored context
                      if (_onSessionExpired != null) {
                        _onSessionExpired();
                      }
                    },
                    child: const Text('OK'),
                  ),
                ],
              ),
        );
      } else {
        // If no context is available, just sign out silently
        if (_authState != null) {
          _authState.signOut();
        }
      }
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

    // Check if session is valid locally
    final isLocallyValid =
        absoluteDuration < _absoluteTimeout &&
        inactiveDuration < _inactivityTimeout;

    // In a production app, also verify with the server
    if (isLocallyValid && _authState != null) {
      // For enhanced security, periodically verify token with server
      // This helps detect revoked tokens or security breaches
      _verifyTokenWithServer();
    }

    return isLocallyValid;
  }

  /// Verifies the current token with the server
  /// This prevents using revoked or invalid tokens
  Future<void> _verifyTokenWithServer() async {
    // Don't verify too frequently to reduce server load
    if (_lastServerVerification != null) {
      final timeSinceLastVerification = DateTime.now().difference(
        _lastServerVerification!,
      );
      if (timeSinceLastVerification < const Duration(minutes: 5)) {
        return; // Skip verification if done recently
      }
    }

    // Set last verification time
    _lastServerVerification = DateTime.now();

    // In a real implementation, call the backend to verify the token
    // If invalid, sign out the user
    if (_authState != null) {
      try {
        final isValid = await _authState!.checkAuthStatus();
        if (!isValid) {
          _handleInactivityTimeout();
        }
      } catch (e) {
        // On verification error, default to timeout for security
        _handleInactivityTimeout();
      }
    }
  }

  /// Gets remaining session time
  Duration getRemainingSessionTime() {
    if (_sessionStartTime == null) return Duration.zero;

    final now = DateTime.now();
    final absoluteDuration = now.difference(_sessionStartTime);
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
