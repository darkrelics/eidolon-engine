// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../utils/auth_state.dart';
import '../widgets/ui_components.dart';
import '../utils/input_sanitizer.dart';

class LoginScreen extends StatelessWidget {
  final String? redirectRoute;
  final Object? redirectArgs;

  const LoginScreen({super.key, this.redirectRoute, this.redirectArgs});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AuthAppBar(title: 'Sign In'),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Consumer<AuthState>(
            builder: (context, authState, child) {
              // If authenticated, navigate to appropriate route
              if (authState.isAuthenticated) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  _handleNavigation(context, redirectRoute, redirectArgs);
                });
                return const Center(child: CircularProgressIndicator());
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
                        validator: FieldValidators.email,
                        inputFormatters: [InputSanitizer.noXSSChars()],
                      ),
                      const SizedBox(height: 16),
                      AppTextField(
                        controller: authState.passwordController,
                        labelText: 'Password',
                        prefixIcon: Icons.lock_outline,
                        hintText: 'Enter your password',
                        obscureText: true,
                        autofillHints: const [AutofillHints.password],
                        validator: FieldValidators.password,
                        inputFormatters: [InputSanitizer.noXSSChars()],
                      ),
                      const SizedBox(height: 32),
                      LoadingButton(
                        isLoading: authState.isLoading,
                        onPressed: () async {
                          final formState = Form.of(context);
                          if (formState != null && formState.validate()) {
                            await authState.signIn();
                            if (authState.isAuthenticated && context.mounted) {
                              _handleNavigation(
                                context,
                                redirectRoute,
                                redirectArgs,
                              );
                            }
                          }
                        },
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
                        message: InputSanitizer.sanitizeDisplayText(
                          authState.message,
                        ),
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

  void _handleNavigation(
    BuildContext context,
    String? redirectRoute,
    Object? redirectArgs,
  ) {
    if (redirectRoute != null) {
      Navigator.of(
        context,
      ).pushReplacementNamed(redirectRoute, arguments: redirectArgs);
    } else {
      Navigator.of(context).pushReplacementNamed('/character-management');
    }
  }
}
