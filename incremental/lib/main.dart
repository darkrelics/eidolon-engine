import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'providers/theme_provider.dart';
import 'screens/login_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/password_reset_screen.dart';
import 'screens/password_reset_confirm_screen.dart';
import 'screens/account_settings_screen.dart';
import 'screens/character_screen.dart';
import 'screens/game_screen.dart';

void main() {
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
  runZonedGuarded(() {
    runApp(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AuthProvider()),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ],
        child: const EidolonIncrementalApp(),
      ),
    );
  }, (error, stack) {
    debugPrint('========== ASYNC ERROR ==========');
    debugPrint('Error: $error');
    debugPrint('Stack trace:\n$stack');
    debugPrint('=================================');
  });
}

class EidolonIncrementalApp extends StatelessWidget {
  const EidolonIncrementalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, _) {
        return MaterialApp(
          title: 'Eidolon Incremental',
          theme: AppTheme.lightTheme(),
          darkTheme: AppTheme.darkTheme(),
          themeMode: themeProvider.themeMode,
          home: const AuthWrapper(),
          routes: {
            '/login': (context) => const LoginScreen(),
            '/register': (context) => const RegistrationScreen(),
            '/forgot-password': (context) => const PasswordResetScreen(),
            '/password-reset-confirm': (context) =>
                const PasswordResetConfirmScreen(),
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
        debugPrint(
          'AuthWrapper: Auth status changed to ${authProvider.status}',
        );
        switch (authProvider.status) {
          case AuthStatus.uninitialized:
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          case AuthStatus.unauthenticated:
            debugPrint('AuthWrapper: Showing LoginScreen');
            return const LoginScreen();
          case AuthStatus.authenticated:
            debugPrint('AuthWrapper: Showing CharacterScreen');
            return const CharacterScreen();
          case AuthStatus.loading:
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
        }
      },
    );
  }
}
