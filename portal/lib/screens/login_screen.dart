import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../auth_state.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sign In', style: TextStyle(color: Colors.white)),
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
            // If authenticated, navigate to character management
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
                      ),
                      autofillHints: const [AutofillHints.password],
                      style: const TextStyle(color: Colors.white),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Please enter your password';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 32),
                    ElevatedButton(
                      onPressed:
                          authState.isLoading ? null : () => authState.signIn(),
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
                                'SIGN IN',
                                style: TextStyle(fontSize: 16),
                              ),
                    ),
                    const SizedBox(height: 16),
                    TextButton(
                      onPressed: () {
                        final authState = Provider.of<AuthState>(context, listen: false);
                        authState.clearInputs();
                        Navigator.of(context).pushReplacementNamed('/register');
                      },
                      child: const Text('Need an Account? Sign up'),
                    ),
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
