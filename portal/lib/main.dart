import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/theme_provider.dart';
import 'services/auth_service.dart';
import 'utils/auth_state.dart';
import 'screens/splash_screen.dart';
import 'screens/login_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/character_management_screen.dart';

void main() {
  final authService = AuthService();
  
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthState(authService: authService),
        ),
        ChangeNotifierProvider(
          create: (_) => ThemeProvider.create(),
        ),
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
        );
      },
    );
  }
  
  Route<dynamic>? _onGenerateRoute(BuildContext context, RouteSettings settings) {
    // Check if user is authenticated for protected routes
    final authState = Provider.of<AuthState>(context, listen: false);

    if (settings.name == '/character-management' &&
        !authState.isAuthenticated) {
      return MaterialPageRoute(builder: (_) => const LoginScreen());
    }

    switch (settings.name) {
      case '/':
        return MaterialPageRoute(
          builder: (_) => const SplashScreen(),
        );
      case '/login':
        return MaterialPageRoute(builder: (_) => const LoginScreen());
      case '/register':
        return MaterialPageRoute(
          builder: (_) => const RegistrationScreen(),
        );
      case '/character-management':
        return MaterialPageRoute(
          builder: (_) => const CharacterManagementScreen(),
        );
      default:
        return MaterialPageRoute(
          builder: (_) => const SplashScreen(),
        );
    }
  }
}