// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/theme_provider.dart';
import 'screens/account_settings_screen.dart';
import 'screens/character_management_screen.dart';
import 'screens/login_screen.dart';
import 'screens/password_reset_confirm_screen.dart';
import 'screens/password_reset_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/splash_screen.dart';
import 'services/auth_service.dart';
import 'utils/auth_state.dart';
import 'utils/global_error_handler.dart';
import 'utils/navigation.dart';
import 'utils/route_guard.dart';
import 'utils/security_config.dart';
import 'utils/session_monitor.dart';

void main() {
  // Enable proper error handling for the app
  WidgetsFlutterBinding.ensureInitialized();

  // Apply security configurations for web
  if (kIsWeb) {
    SecurityConfig.applyWebSecurityConfig();

    // Validate security headers in debug mode
    if (kDebugMode) {
      SecurityConfig.validateSecurityHeaders();
    }
  }

  // Initialize global error handler
  GlobalErrorHandler.initialize();

  final authService = AuthService();
  final sessionMonitor = SessionMonitor();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthState(authService: authService)),
        ChangeNotifierProvider(create: (_) => ThemeProvider.create()),
        Provider.value(value: sessionMonitor),
        Provider.value(value: authService),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, child) {
        final sessionMonitor = Provider.of<SessionMonitor>(context, listen: false);

        return MaterialApp(
          title: 'Eidolon Engine',
          debugShowCheckedModeBanner: false,
          theme: themeProvider.theme,
          initialRoute: '/',
          onGenerateRoute: (settings) => _onGenerateRoute(context, settings),
          // Add a global key for navigation from anywhere
          navigatorKey: GlobalNavigationKey.navigatorKey,
          builder: (context, child) {
            return ActivityMonitor(sessionMonitor: sessionMonitor, child: child ?? const SizedBox.shrink());
          },
        );
      },
    );
  }

  Route<dynamic>? _onGenerateRoute(BuildContext context, RouteSettings settings) {
    // Route guard for protected routes
    if (RouteGuard.isProtectedRoute(settings.name)) {
      final authState = Provider.of<AuthState>(context, listen: false);
      if (!authState.isAuthenticated) {
        return MaterialPageRoute(builder: (_) => LoginScreen(redirectRoute: settings.name, redirectArgs: settings.arguments));
      }
    }

    switch (settings.name) {
      case '/':
        return MaterialPageRoute(builder: (_) => const SplashScreen());
      case '/login':
        String? redirectRoute;
        Object? redirectArgs;
        if (settings.arguments is Map<String, dynamic>) {
          final args = settings.arguments as Map<String, dynamic>;
          redirectRoute = args['redirectRoute'] as String?;
          redirectArgs = args['redirectArgs'];
        }
        return MaterialPageRoute(builder: (_) => LoginScreen(redirectRoute: redirectRoute, redirectArgs: redirectArgs));
      case '/register':
        return MaterialPageRoute(builder: (_) => const RegistrationScreen());
      case '/password-reset':
        return MaterialPageRoute(builder: (_) => const PasswordResetScreen());
      case '/password-reset-confirm':
        return MaterialPageRoute(builder: (_) => const PasswordResetConfirmScreen(), settings: settings);
      case '/character-management':
        return MaterialPageRoute(builder: (_) => const CharacterManagementScreen());
      case '/account-settings':
        return MaterialPageRoute(builder: (_) => const AccountSettingsScreen());
      default:
        return MaterialPageRoute(builder: (_) => const ErrorScreen(message: 'Route not found'));
    }
  }
}

/// Error screen for unknown routes or errors
class ErrorScreen extends StatelessWidget {
  final String message;

  const ErrorScreen({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.red),
            const SizedBox(height: 16),
            Text(message, style: Theme.of(context).textTheme.headlineSmall, textAlign: TextAlign.center),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () {
                Navigator.of(context).pushReplacementNamed('/');
              },
              child: const Text('Return to Home'),
            ),
          ],
        ),
      ),
    );
  }
}

/// App lifecycle observer to handle app state changes
class AppLifecycleObserver extends WidgetsBindingObserver {
  final AuthState authState;
  final SessionMonitor sessionMonitor;

  AppLifecycleObserver(this.authState, this.sessionMonitor);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        // Check authentication when app resumes
        authState.checkAuthStatus();
        if (authState.isAuthenticated) {
          sessionMonitor.registerActivity();
        }
        break;
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        // No action needed
        break;
    }
  }
}

/// App widget with lifecycle observer
class AppWithLifecycleObserver extends StatefulWidget {
  final Widget child;

  const AppWithLifecycleObserver({super.key, required this.child});

  @override
  State<AppWithLifecycleObserver> createState() => _AppWithLifecycleObserverState();
}

class _AppWithLifecycleObserverState extends State<AppWithLifecycleObserver> {
  late final AppLifecycleObserver _observer;

  @override
  void initState() {
    super.initState();
    final authState = Provider.of<AuthState>(context, listen: false);
    final sessionMonitor = Provider.of<SessionMonitor>(context, listen: false);
    _observer = AppLifecycleObserver(authState, sessionMonitor);
    WidgetsBinding.instance.addObserver(_observer);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(_observer);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
