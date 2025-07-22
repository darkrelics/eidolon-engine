import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/password_reset_screen.dart';
import 'screens/password_reset_confirm_screen.dart';
import 'screens/account_settings_screen.dart';
import 'screens/character_selection_screen.dart';
import 'screens/game_screen.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [ChangeNotifierProvider(create: (_) => AuthProvider())],
      child: const EidolonIncrementalApp(),
    ),
  );
}

class EidolonIncrementalApp extends StatelessWidget {
  const EidolonIncrementalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Eidolon Incremental',
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const AuthWrapper(),
      routes: {
        '/login': (context) => const LoginScreen(),
        '/register': (context) => const RegistrationScreen(),
        '/forgot-password': (context) => const PasswordResetScreen(),
        '/password-reset-confirm': (context) =>
            const PasswordResetConfirmScreen(),
        '/account-settings': (context) => const AccountSettingsScreen(),
        '/character-selection': (context) => const CharacterSelectionScreen(),
        '/game': (context) => const GameScreen(),
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
            debugPrint('AuthWrapper: Showing CharacterSelectionScreen');
            return const CharacterSelectionScreen();
          case AuthStatus.loading:
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
        }
      },
    );
  }
}
