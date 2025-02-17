import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'auth_service.dart';
import 'auth_state.dart';

void main() {
  final authService = AuthService();
  runApp(
    ChangeNotifierProvider(
      create: (context) => AuthState(authService: authService),
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Eidolon Engine Email Verification',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: Colors.black,
        primaryColor: Colors.white,
        colorScheme: const ColorScheme.dark(
          primary: Colors.white,
          secondary: Colors.white70,
          surface: Colors.black,
          onPrimary: Colors.black,
          onSecondary: Colors.black,
          onSurface: Colors.white,
        ),
        inputDecorationTheme: const InputDecorationTheme(
          labelStyle: TextStyle(color: Colors.white70),
          enabledBorder: UnderlineInputBorder(
            borderSide: BorderSide(color: Colors.white70),
          ),
          focusedBorder: UnderlineInputBorder(
            borderSide: BorderSide(color: Colors.white),
          ),
        ),
        textTheme: const TextTheme(
          bodyLarge: TextStyle(color: Colors.white),
          bodyMedium: TextStyle(color: Colors.white),
          titleMedium: TextStyle(color: Colors.white),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            foregroundColor: Colors.black,
            backgroundColor: Colors.white,
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: Colors.white,
          ),
        ),
      ),
      home: const AuthScreen(),
    );
  }
}

class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          context.watch<AuthState>().isSignUpMode ? 'Sign Up' : 'Sign In',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.black,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          child: Consumer<AuthState>(
            builder: (context, authState, child) => Column(
              children: <Widget>[
                if (authState.isSignUpMode) ...[
                  TextFormField(
                    controller: authState.emailController,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your email';
                      }
                      return null;
                    },
                  ),
                  TextFormField(
                    controller: authState.passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password'),
                    style: const TextStyle(color: Colors.white),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed:
                        authState.isLoading ? null : () => authState.signUp(),
                    child: const Text('Sign Up'),
                  ),
                  const SizedBox(height: 20),
                  TextButton(
                    onPressed: () => authState.toggleAuthMode(),
                    child: const Text('Already have an account? Sign in'),
                  ),
                ] else if (!authState.isVerificationMode) ...[
                  TextFormField(
                    controller: authState.emailController,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your email';
                      }
                      return null;
                    },
                  ),
                  TextFormField(
                    controller: authState.passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password'),
                    style: const TextStyle(color: Colors.white),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed:
                        authState.isLoading ? null : () => authState.signIn(),
                    child: const Text('Sign In'),
                  ),
                  const SizedBox(height: 20),
                  TextButton(
                    onPressed: () => authState.toggleAuthMode(),
                    child: const Text('Need an Account? Sign up'),
                  ),
                ] else ...[
                  TextFormField(
                    controller: authState.verificationCodeController,
                    decoration:
                        const InputDecoration(labelText: 'Verification Code'),
                    style: const TextStyle(color: Colors.white),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter verification code';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: authState.isLoading
                        ? null
                        : () => authState.confirmRegistration(),
                    child: const Text('Verify'),
                  ),
                ],
                const SizedBox(height: 20),
                if (authState.isLoading)
                  const CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  )
                else if (authState.message.isNotEmpty)
                  Text(
                    authState.message,
                    style: TextStyle(
                      color: authState.message.toLowerCase().contains('error')
                          ? Colors.red
                          : Colors.green[300],
                    ),
                    textAlign: TextAlign.center,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}