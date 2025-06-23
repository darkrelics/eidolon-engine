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
import 'package:amazon_cognito_identity_dart_2/cognito.dart';

import '../services/auth_service.dart';
import '../widgets/ui_components.dart';
import '../utils/input_sanitizer.dart';
import '../utils/form_state_provider.dart';

class PasswordResetScreen extends StatefulWidget {
  const PasswordResetScreen({super.key});

  @override
  State<PasswordResetScreen> createState() => _PasswordResetScreenState();
}

class _PasswordResetScreenState extends State<PasswordResetScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  bool _isLoading = false;
  String _message = '';
  bool _isError = false;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _requestPasswordReset() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _message = '';
      _isError = false;
    });

    try {
      final authService = Provider.of<AuthService>(context, listen: false);
      await authService.forgotPassword(_emailController.text.trim());

      if (mounted) {
        setState(() {
          _message = 'Password reset code sent to your email';
          _isError = false;
        });

        Navigator.of(context).pushReplacementNamed(
          '/password-reset-confirm',
          arguments: _emailController.text.trim(),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isError = true;
          _message =
              e is CognitoClientException && e.message != null
                  ? e.message!
                  : 'An unexpected error occurred. Please try again.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const AuthAppBar(title: 'Reset Password'),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: FormStateProvider(
            formKey: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const SizedBox(height: 24),
                const Text(
                  'Enter your email address and we\'ll send you a code to reset your password.',
                  style: TextStyle(fontSize: 16),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                AppTextField(
                  controller: _emailController,
                  labelText: 'Email',
                  prefixIcon: Icons.email_outlined,
                  hintText: 'Enter your email',
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  validator: FieldValidators.email,
                  inputFormatters: [InputSanitizer.noXSSChars()],
                  onSubmitted: (_) => _requestPasswordReset(),
                ),
                const SizedBox(height: 32),
                LoadingButton(
                  isLoading: _isLoading,
                  onPressed: _requestPasswordReset,
                  text: 'SEND RESET CODE',
                ),
                const SizedBox(height: 16),
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                  child: const Text('Back to Sign In'),
                ),
                const SizedBox(height: 24),
                StatusMessage(
                  message: InputSanitizer.sanitizeDisplayText(_message),
                  isError: _isError,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
