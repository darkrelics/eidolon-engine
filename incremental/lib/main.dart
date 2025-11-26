import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'providers/auth_provider.dart';
import 'providers/character_provider.dart';
import 'providers/theme_provider.dart';
import 'providers/timer_provider.dart';
import 'repositories/character_repository.dart';
import 'screens/account_settings_screen.dart';
import 'screens/character_screen.dart';
import 'screens/game_screen.dart';
import 'screens/login_screen.dart';
import 'screens/password_reset_confirm_screen.dart';
import 'screens/password_reset_screen.dart';
import 'screens/registration_screen.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/indexeddb_service.dart';

void main() async {
  // Ensure Flutter is initialized
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize SharedPreferences
  final prefs = await SharedPreferences.getInstance();

  // Initialize IndexedDB (web only)
  if (kIsWeb && IndexedDBService().isSupported) {
    await IndexedDBService().initialize();
    debugPrint('IndexedDB initialization completed');
  }

  // Initialize Services & Repositories
  final apiService = ApiService(authService: AuthService.instance);
  final characterRepository = CharacterRepository(apiService: apiService, indexedDBService: IndexedDBService());

  // Set up global error handlers
  FlutterError.onError = (FlutterErrorDetails details) {
    debugPrint('========== FLUTTER ERROR ==========');
    debugPrint('Error: ${details.exception}');
    debugPrint('Stack trace:\n${details.stack}');
    debugPrint('Library: ${details.library}');
    debugPrint('===================================');
    FlutterError.presentError(details);
  };

  // Catch async errors
  runZonedGuarded(
    () {
      runApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(create: (_) => AuthProvider()),
            ChangeNotifierProvider(
              create: (_) => CharacterProvider(prefs: prefs, repository: characterRepository),
            ),
            ChangeNotifierProvider(create: (_) => ThemeProvider.create()),
            ChangeNotifierProvider(create: (_) => TimerProvider()),
          ],
          child: const EidolonIncrementalApp(),
        ),
      );
    },
    (error, stack) {
      debugPrint('========== ASYNC ERROR ==========');
      debugPrint('Error: $error');
      debugPrint('Stack trace:\n$stack');
      debugPrint('=================================');
    },
  );
}

class EidolonIncrementalApp extends StatelessWidget {
  const EidolonIncrementalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, _) {
        return MaterialApp(
          title: 'Eidolon Incremental',
          theme: themeProvider.getThemeForMode(context),
          darkTheme: themeProvider.theme,
          themeMode: themeProvider.themeMode,
          home: const AuthWrapper(),
          routes: {
            '/login': (context) => const LoginScreen(),
            '/register': (context) => const RegistrationScreen(),
            '/forgot-password': (context) => const PasswordResetScreen(),
            '/password-reset-confirm': (context) => const PasswordResetConfirmScreen(),
            '/account-settings': (context) => const AccountSettingsScreen(),
            '/character-selection': (context) => const CharacterScreen(),
            '/game': (context) => const GameScreen(),
          },
        );
      },
    );
  }
}

class AuthWrapper extends StatelessWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, _) {
        // debugPrint(
        //   'AuthWrapper: Auth status changed to ${authProvider.status}',
        // );
        switch (authProvider.status) {
          case AuthStatus.uninitialized:
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
          case AuthStatus.unauthenticated:
            // debugPrint('AuthWrapper: Showing LoginScreen');
            return const LoginScreen();
          case AuthStatus.authenticated:
            // debugPrint('AuthWrapper: Showing CharacterScreen');
            return const CharacterScreen();
          case AuthStatus.loading:
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
      },
    );
  }
}
