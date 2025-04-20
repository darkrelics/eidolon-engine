import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:portal/utils/auth_state.dart';

class RegistrationScreen extends StatelessWidget {
  const RegistrationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Create Account',
          style: TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.black,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
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
                    const SizedBox(height: 20),
                    if (!authState.isVerificationMode) ...[
                      TextFormField(
                        controller: authState.emailController,
                        decoration: const InputDecoration(
                          labelText: 'Email',
                          prefixIcon: Icon(Icons.email, color: Colors.white70),
                        ),
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        style: const TextStyle(color: Colors.white),
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Please enter your email';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 16),
                      TextFormField(
                        controller: authState.passwordController,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Password',
                          prefixIcon: Icon(Icons.lock, color: Colors.white70),
                          helperText:
                              'Password must be at least 8 characters with lowercase, uppercase, numbers and symbols',
                          helperStyle: TextStyle(
                            color: Colors.white54,
                            fontSize: 12,
                          ),
                        ),
                        autofillHints: const [AutofillHints.newPassword],
                        style: const TextStyle(color: Colors.white),
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Please enter a password';
                          }
                          if (value.length < 8) {
                            return 'Password must be at least 8 characters';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 32),
                      ElevatedButton(
                        onPressed:
                            authState.isLoading
                                ? null
                                : () => authState.signUp(),
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                        child:
                            authState.isLoading
                                ? const SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.black,
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
                          Navigator.of(context).pushReplacementNamed('/login');
                        },
                        child: const Text('Already have an account? Sign in'),
                      ),
                    ] else ...[
                      const Text(
                        'Verification Required',
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'Please check your email for a verification code to complete your registration.',
                        style: TextStyle(color: Colors.white70),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      TextFormField(
                        controller: authState.verificationCodeController,
                        decoration: const InputDecoration(
                          labelText: 'Verification Code',
                          prefixIcon: Icon(
                            Icons.verified_user,
                            color: Colors.white70,
                          ),
                        ),
                        style: const TextStyle(color: Colors.white),
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Please enter verification code';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 32),
                      ElevatedButton(
                        onPressed:
                            authState.isLoading
                                ? null
                                : () async {
                                  await authState.confirmRegistration();
                                  if (!authState.isVerificationMode &&
                                      context.mounted) {
                                    authState
                                        .clearInputs(); // Clear inputs before navigation
                                    Navigator.of(
                                      context,
                                    ).pushReplacementNamed('/login');
                                  }
                                },
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                        child:
                            authState.isLoading
                                ? const SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.black,
                                  ),
                                )
                                : const Text(
                                  'VERIFY',
                                  style: TextStyle(fontSize: 16),
                                ),
                      ),
                    ],
                    if (authState.message.isNotEmpty) ...[
                      const SizedBox(height: 20),
                      Text(
                        authState.message,
                        style: TextStyle(
                          color:
                              authState.message.toLowerCase().contains(
                                        'fail',
                                      ) ||
                                      authState.message.toLowerCase().contains(
                                        'error',
                                      )
                                  ? Colors.red[400]
                                  : Colors.green[300],
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
