import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../utils/auth_state.dart';
import '../widgets/ui_components.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AuthAppBar(title: 'Sign In'),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Consumer<AuthState>(
            builder: (context, authState, child) {
              // If authenticated, navigate to character management
              if (authState.isAuthenticated) {
                NavigationHelper.handleAuthenticated(context);
              }

              return Form(
                autovalidateMode: AutovalidateMode.onUserInteraction,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      const SizedBox(height: 24),
                      AppTextField(
                        controller: authState.emailController,
                        labelText: 'Email',
                        prefixIcon: Icons.email_outlined,
                        hintText: 'Enter your email',
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                      ),
                      const SizedBox(height: 16),
                      AppTextField(
                        controller: authState.passwordController,
                        labelText: 'Password',
                        prefixIcon: Icons.lock_outline,
                        hintText: 'Enter your password',
                        obscureText: true,
                        autofillHints: const [AutofillHints.password],
                      ),
                      const SizedBox(height: 32),
                      LoadingButton(
                        isLoading: authState.isLoading,
                        onPressed: () => authState.signIn(),
                        text: 'SIGN IN',
                      ),
                      const SizedBox(height: 16),
                      TextButton(
                        onPressed: () {
                          final authState = Provider.of<AuthState>(
                            context,
                            listen: false,
                          );
                          authState.clearInputs();
                          NavigationHelper.navigateToRegister(context);
                        },
                        child: const Text('Need an Account? Sign up'),
                      ),
                      const SizedBox(height: 24),
                      StatusMessage(
                        message: authState.message,
                        isError:
                            authState.message.toLowerCase().contains('fail') ||
                            authState.message.toLowerCase().contains('error'),
                      ),
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
