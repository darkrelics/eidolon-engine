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
                          hintText: 'Create a password',
                          helperText:
                              'Password must be at least 8 characters with lowercase, uppercase, numbers and symbols',
                          helperMaxLines: 2,
                          obscureText: true,
                          autofillHints: const [AutofillHints.newPassword],
                          validator:
                              (value) => FieldValidators.password(
                                value,
                                checkComplexity: true,
                              ),
                          inputFormatters: [InputSanitizer.noXSSChars()],
                        ),
                        const SizedBox(height: 32),
                        LoadingButton(
                          isLoading: authState.isLoading,
                          onPressed: () async {
                            final formState = Form.of(context);
                            if (formState.validate()) {
                              await authState.signUp();
                            }
                          },
                          text: 'CREATE ACCOUNT',
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
                        AppTextField(
                          controller: authState.verificationCodeController,
                          labelText: 'Verification Code',
                          prefixIcon: Icons.verified_user_outlined,
                          hintText: 'Enter verification code',
                          validator: FieldValidators.verificationCode,
                          inputFormatters: [InputSanitizer.noXSSChars()],
                        ),
                        const SizedBox(height: 32),
                        LoadingButton(
                          isLoading: authState.isLoading,
                          onPressed: () async {
                            final formState = Form.of(context);
                            if (formState.validate()) {
                              await authState.confirmRegistration();
                              if (!authState.isVerificationMode &&
                                  context.mounted) {
                                authState.clearInputs();
                                Navigator.of(
                                  context,
                                ).pushReplacementNamed('/login');
                              }
                            }
                          },
                          text: 'VERIFY',
                        ),
                      ],
                      if (authState.message.isNotEmpty) ...[
                        const SizedBox(height: 24),
                        StatusMessage(
                          message: authState.message,
                          isError:
                              authState.message.toLowerCase().contains(
                                'fail',
                              ) ||
                              authState.message.toLowerCase().contains('error'),
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
