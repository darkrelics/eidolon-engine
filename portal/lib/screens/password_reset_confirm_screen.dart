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

class PasswordResetConfirmScreen extends StatefulWidget {
  final String email;

  const PasswordResetConfirmScreen({super.key, required this.email});

  @override
  State<PasswordResetConfirmScreen> createState() =>
      _PasswordResetConfirmScreenState();
}

class _PasswordResetConfirmScreenState
    extends State<PasswordResetConfirmScreen> {
  final _formKey = GlobalKey<FormState>();
  final _codeController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _isLoading = false;
  String _message = '';
  bool _isError = false;

  @override
  void dispose() {
    _codeController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _confirmPasswordReset() async {
    if (!_formKey.currentState!.validate()) return;

    if (_passwordController.text != _confirmPasswordController.text) {
      setState(() {
        _message = 'Passwords do not match';
        _isError = true;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _message = '';
      _isError = false;
    });

    try {
      final authService = Provider.of<AuthService>(context, listen: false);
      await authService.confirmPassword(
        widget.email,
        _codeController.text.trim(),
        _passwordController.text,
      );

      if (mounted) {
        setState(() {
          _message = 'Password reset successfully';
          _isError = false;
        });

        Navigator.of(
          context,
        ).pushNamedAndRemoveUntil('/login', (route) => false);
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

  Future<void> _resendCode() async {
    setState(() {
      _isLoading = true;
      _message = '';
      _isError = false;
    });

    try {
      final authService = Provider.of<AuthService>(context, listen: false);
      await authService.forgotPassword(widget.email);

      if (mounted) {
        setState(() {
          _message = 'New reset code sent to your email';
          _isError = false;
        });
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
      appBar: const AuthAppBar(title: 'Confirm Reset'),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: FormStateProvider(
            formKey: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const SizedBox(height: 24),
                Text(
                  'Enter the verification code sent to ${widget.email} and your new password.',
                  style: const TextStyle(fontSize: 16),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                AppTextField(
                  controller: _codeController,
                  labelText: 'Verification Code',
                  prefixIcon: Icons.verified_user_outlined,
                  hintText: 'Enter verification code',
                  keyboardType: TextInputType.number,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please enter the verification code';
                    }
                    return null;
                  },
                  inputFormatters: [InputSanitizer.noXSSChars()],
                ),
                const SizedBox(height: 16),
                AppTextField(
                  controller: _passwordController,
                  labelText: 'New Password',
                  prefixIcon: Icons.lock_outline,
                  hintText: 'Enter new password',
                  obscureText: true,
                  validator: FieldValidators.password,
                  inputFormatters: [InputSanitizer.noXSSChars()],
                ),
                const SizedBox(height: 16),
                AppTextField(
                  controller: _confirmPasswordController,
                  labelText: 'Confirm New Password',
                  prefixIcon: Icons.lock_outline,
                  hintText: 'Confirm new password',
                  obscureText: true,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please confirm your password';
                    }
                    return null;
                  },
                  inputFormatters: [InputSanitizer.noXSSChars()],
                ),
                const SizedBox(height: 32),
                LoadingButton(
                  isLoading: _isLoading,
                  onPressed: _confirmPasswordReset,
                  text: 'RESET PASSWORD',
                ),
                const SizedBox(height: 16),
                TextButton(
                  onPressed: _isLoading ? null : _resendCode,
                  child: const Text('Resend Code'),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: () {
                    Navigator.of(
                      context,
                    ).pushNamedAndRemoveUntil('/login', (route) => false);
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
