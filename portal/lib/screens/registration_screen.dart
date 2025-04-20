import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../utils/auth_state.dart';

class RegistrationScreen extends StatelessWidget {
  const RegistrationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Account'),
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
              if (authState.isAuthenticated) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  Navigator.of(
                    context,
                  ).pushReplacementNamed('/character-management');
                });
              }

              return Form(
                autovalidateMode: AutovalidateMode.onUserInteraction,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      const SizedBox(height: 24),
                      if (!authState.isVerificationMode) ...[
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
                            hintText: 'Create a password',
                            helperText:
                                'Password must be at least 8 characters with lowercase, uppercase, numbers and symbols',
                            helperMaxLines: 2,
                            border: const OutlineInputBorder(),
                          ),
                          autofillHints: const [AutofillHints.newPassword],
                          style: TextStyle(color: colorScheme.onSurface),
                        ),
                        const SizedBox(height: 32),
                        FilledButton(
                          onPressed:
                              authState.isLoading
                                  ? null
                                  : () => authState.signUp(),
                          child:
                              authState.isLoading
                                  ? SizedBox(
                                    height: 24,
                                    width: 24,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: colorScheme.onPrimary,
                                    ),
                                  )
                                  : const Text(
                                    'CREATE ACCOUNT',
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
                            Navigator.of(
                              context,
                            ).pushReplacementNamed('/login');
                          },
                          child: const Text('Already have an account? Sign in'),
                        ),
                      ] else ...[
                        Text(
                          'Verification Required',
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: colorScheme.onSurface,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'Please check your email for a verification code to complete your registration.',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: colorScheme.onSurfaceVariant,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 24),
                        TextField(
                          controller: authState.verificationCodeController,
                          decoration: InputDecoration(
                            labelText: 'Verification Code',
                            prefixIcon: Icon(
                              Icons.verified_user_outlined,
                              color: colorScheme.onSurfaceVariant,
                            ),
                            hintText: 'Enter verification code',
                            border: const OutlineInputBorder(),
                          ),
                          style: TextStyle(color: colorScheme.onSurface),
                        ),
                        const SizedBox(height: 32),
                        FilledButton(
                          onPressed:
                              authState.isLoading
                                  ? null
                                  : () async {
                                    await authState.confirmRegistration();
                                    if (!authState.isVerificationMode &&
                                        context.mounted) {
                                      authState.clearInputs();
                                      Navigator.of(
                                        context,
                                      ).pushReplacementNamed('/login');
                                    }
                                  },
                          child:
                              authState.isLoading
                                  ? SizedBox(
                                    height: 24,
                                    width: 24,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: colorScheme.onPrimary,
                                    ),
                                  )
                                  : const Text(
                                    'VERIFY',
                                    style: TextStyle(fontSize: 16),
                                  ),
                        ),
                      ],
                      if (authState.message.isNotEmpty) ...[
                        const SizedBox(height: 24),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Text(
                            authState.message,
                            style: TextStyle(
                              color:
                                  authState.message.toLowerCase().contains(
                                            'fail',
                                          ) ||
                                          authState.message
                                              .toLowerCase()
                                              .contains('error')
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
