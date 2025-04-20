import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/theme_provider.dart';
import 'services/auth_service.dart';
import 'utils/auth_state.dart';
import 'screens/splash_screen.dart';
import 'screens/login_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/character_management_screen.dart';
import 'utils/security_config.dart';

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

  // Set up error reporting (in production, use a proper error reporting service)
  FlutterError.onError = (FlutterErrorDetails details) {
    if (kDebugMode) {
      FlutterError.presentError(details);
    }
    // In production, send to error reporting service
  };

  final authService = AuthService();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthState(authService: authService),
        ),
        ChangeNotifierProvider(create: (_) => ThemeProvider.create()),
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
        return MaterialApp(
          title: 'Eidolon Engine',
          debugShowCheckedModeBanner: false,
          theme: themeProvider.theme,
          initialRoute: '/',
          onGenerateRoute: (settings) => _onGenerateRoute(context, settings),
          // Add a global key for navigation from anywhere
          navigatorKey: GlobalNavigationKey.navigatorKey,
        );
      },
    );
  }

  Route<dynamic>? _onGenerateRoute(
    BuildContext context,
    RouteSettings settings,
  ) {
    switch (settings.name) {
      case '/':
        return MaterialPageRoute(builder: (_) => const SplashScreen());
      case '/login':
        return MaterialPageRoute(builder: (_) => const LoginScreen());
      case '/register':
        return MaterialPageRoute(builder: (_) => const RegistrationScreen());
      case '/character-management':
        return MaterialPageRoute(
          builder:
              (_) =>
                  const AuthenticatedRoute(child: CharacterManagementScreen()),
        );
      default:
        return MaterialPageRoute(
          builder: (_) => const ErrorScreen(message: 'Route not found'),
        );
    }
  }
}

/// Global navigation key for accessing navigation from anywhere
class GlobalNavigationKey {
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();
}

/// Wrapper widget that checks authentication status for protected routes
class AuthenticatedRoute extends StatelessWidget {
  final Widget child;

  const AuthenticatedRoute({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthState>(
      builder: (context, authState, _) {
        // Check authentication status
        if (!authState.isAuthenticated) {
          // Schedule navigation after the frame is built
          WidgetsBinding.instance.addPostFrameCallback((_) {
            Navigator.of(context).pushReplacementNamed('/login');
          });
          // Show loading while redirecting
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        // User is authenticated, show the protected screen
        return child;
      },
    );
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
            Text(
              message,
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
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

  AppLifecycleObserver(this.authState);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        // Check authentication when app resumes
        authState.checkAuthStatus();
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
  State<AppWithLifecycleObserver> createState() =>
      _AppWithLifecycleObserverState();
}

class _AppWithLifecycleObserverState extends State<AppWithLifecycleObserver> {
  late final AppLifecycleObserver _observer;

  @override
  void initState() {
    super.initState();
    final authState = Provider.of<AuthState>(context, listen: false);
    _observer = AppLifecycleObserver(authState);
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
