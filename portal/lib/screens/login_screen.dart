import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../utils/auth_state.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sign In'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Consumer<AuthState>(
            builder: (context, authState, child) {
              // If authenticated, navigate to character management
              if (authState.isAuthenticated) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  Navigator.of(context)
                      .pushReplacementNamed('/character-management');
                });
              }

              return Form(
                autovalidateMode: AutovalidateMode.onUserInteraction,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      const SizedBox(height: 24),
                      TextField(
                        controller: authState.emailController,
                        decoration: InputDecoration(
                          labelText: 'Email',
                          prefixIcon: Icon(
                            Icons.email_outlined,
                            color: colorScheme.onSurfaceVariant,
                          ),
                          hintText: 'Enter your email',
                          border: const OutlineInputBorder(),
                        ),
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        style: TextStyle(color: colorScheme.onSurface),
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: authState.passwordController,
                        obscureText: true,
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: Icon(
                            Icons.lock_outline,
                            color: colorScheme.onSurfaceVariant,
                          ),
                          hintText: 'Enter your password',
                          border: const OutlineInputBorder(),
                        ),
                        autofillHints: const [AutofillHints.password],
                        style: TextStyle(color: colorScheme.onSurface),
                      ),
                      const SizedBox(height: 32),
                      FilledButton(
                        onPressed: authState.isLoading 
                            ? null 
                            : () => authState.signIn(),
                        child: authState.isLoading
                            ? SizedBox(
                                height: 24,
                                width: 24,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: colorScheme.onPrimary,
                                ),
                              )
                            : const Text(
                                'SIGN IN',
                                style: TextStyle(fontSize: 16),
                              ),
                      ),
                      const SizedBox(height: 16),
                      TextButton(
                        onPressed: () {
                          final authState = Provider.of<AuthState>(
                            context,
                            listen: false,
                          );
                          authState.clearInputs();
                          Navigator.of(context).pushReplacementNamed('/register');
                        },
                        child: const Text('Need an Account? Sign up'),
                      ),
                      if (authState.message.isNotEmpty) ...[
                        const SizedBox(height: 24),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Text(
                            authState.message,
                            style: TextStyle(
                              color: authState.message.toLowerCase().contains('fail') ||
                                      authState.message.toLowerCase().contains('error')
                                  ? colorScheme.error
                                  : colorScheme.primary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}