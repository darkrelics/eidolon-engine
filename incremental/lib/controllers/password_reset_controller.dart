import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class PasswordResetController extends ChangeNotifier {
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  final TextEditingController emailController = TextEditingController();
  final TextEditingController codeController = TextEditingController();
  final TextEditingController passwordController = TextEditingController();
  final TextEditingController confirmPasswordController = TextEditingController();

  bool _isPasswordVisible = false;
  bool _isConfirmPasswordVisible = false;
  bool _isLoading = false;
  String? _email;

  bool get isPasswordVisible => _isPasswordVisible;
  bool get isConfirmPasswordVisible => _isConfirmPasswordVisible;
  bool get isLoading => _isLoading;
  String? get email => _email;

  void initialize(String? email) {
    _email = email;
    if (email != null) {
      emailController.text = email;
    }
    notifyListeners();
  }

  void togglePasswordVisibility() {
    _isPasswordVisible = !_isPasswordVisible;
    notifyListeners();
  }

  void toggleConfirmPasswordVisibility() {
    _isConfirmPasswordVisible = !_isConfirmPasswordVisible;
    notifyListeners();
  }

  @override
  void dispose() {
    emailController.dispose();
    codeController.dispose();
    passwordController.dispose();
    confirmPasswordController.dispose();
    super.dispose();
  }

  String? validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter a password';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters';
    }
    if (!RegExp(r'(?=.*[a-z])').hasMatch(value)) {
      return 'Password must contain a lowercase letter';
    }
    if (!RegExp(r'(?=.*[A-Z])').hasMatch(value)) {
      return 'Password must contain an uppercase letter';
    }
    if (!RegExp(r'(?=.*\d)').hasMatch(value)) {
      return 'Password must contain a number';
    }
    if (!RegExp(r'(?=.*[@$!%*?&])').hasMatch(value)) {
      return 'Password must contain a special character (@\$!%*?&)';
    }
    return null;
  }

  Future<void> handlePasswordResetRequest(BuildContext context) async {
    if (!formKey.currentState!.validate()) return;

    _isLoading = true;
    notifyListeners();

    try {
      final authProvider = context.read<AuthProvider>();
      await authProvider.forgotPassword(emailController.text.trim());

      if (context.mounted) {
        Navigator.pushNamed(context, '/password-reset-confirm', arguments: emailController.text.trim());

        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Reset code sent to your email'), backgroundColor: Colors.green));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'forgotPassword')),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> handlePasswordResetConfirm(BuildContext context) async {
    if (!formKey.currentState!.validate()) return;
    if (_email == null) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Email not found. Please start over.'), backgroundColor: Colors.red));
        Navigator.pushReplacementNamed(context, '/forgot-password');
      }
      return;
    }

    _isLoading = true;
    notifyListeners();

    try {
      final authProvider = context.read<AuthProvider>();
      await authProvider.confirmPassword(_email!, codeController.text.trim(), passwordController.text);

      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Password reset successfully! Please sign in.'), backgroundColor: Colors.green),
        );
        Navigator.pushReplacementNamed(context, '/login');
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'confirmPassword')),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> resendCode(BuildContext context) async {
    if (_email == null) return;

    _isLoading = true;
    notifyListeners();

    try {
      final authProvider = context.read<AuthProvider>();
      await authProvider.forgotPassword(_email!);

      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('New reset code sent'), backgroundColor: Colors.green));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'confirmPassword')),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
