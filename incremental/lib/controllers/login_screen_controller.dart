import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class LoginScreenController extends ChangeNotifier {
  final GlobalKey<FormState> formKey = GlobalKey<FormState>();
  final TextEditingController emailController = TextEditingController();
  final TextEditingController passwordController = TextEditingController();

  bool _isPasswordVisible = false;
  bool _isLoading = false;

  bool get isPasswordVisible => _isPasswordVisible;
  bool get isLoading => _isLoading;

  void togglePasswordVisibility() {
    _isPasswordVisible = !_isPasswordVisible;
    notifyListeners();
  }

  @override
  void dispose() {
    emailController.dispose();
    passwordController.dispose();
    super.dispose();
  }

  Future<void> signIn(BuildContext context) async {
    if (!formKey.currentState!.validate()) return;

    _isLoading = true;
    notifyListeners();

    try {
      final authProvider = context.read<AuthProvider>();
      await authProvider.signIn(emailController.text.trim(), passwordController.text);

      if (context.mounted) {
        Navigator.of(context).pushNamedAndRemoveUntil('/', (route) => false);
      }
    } catch (e) {
      debugPrint('LoginScreenController: Sign in error caught: ${e.runtimeType}');
      debugPrint('LoginScreenController: Error message: $e');

      if (context.mounted) {
        final isMfaRequired = e is CognitoClientException && e.code == 'MFA_REQUIRED';

        if (isMfaRequired) {
          _isLoading = false;
          notifyListeners();
          await _showMfaDialog(context);
        } else {
          final errorMessage = ErrorHandler.getUserFriendlyMessage(e, context: 'signIn');
          debugPrint('LoginScreenController: Showing error SnackBar: $errorMessage');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(errorMessage),
              backgroundColor: Theme.of(context).colorScheme.error,
              duration: const Duration(seconds: 4),
            ),
          );
        }
      } else {
        debugPrint('LoginScreenController: Context not mounted, cannot show error');
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _showMfaDialog(BuildContext context) async {
    final codeController = TextEditingController();
    // Capture providers and navigator before showing dialog to avoid stale context issues
    final authProvider = context.read<AuthProvider>();
    final navigator = Navigator.of(context);

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: const Text('MFA Verification'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Please enter the code from your authenticator app.'),
            const SizedBox(height: 16),
            TextField(
              controller: codeController,
              decoration: const InputDecoration(labelText: 'Code', border: OutlineInputBorder()),
              keyboardType: TextInputType.number,
              maxLength: 6,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () async {
              if (codeController.text.length < 6) return;

              try {
                await authProvider.respondToMfaChallenge(codeController.text);

                if (dialogContext.mounted) {
                  Navigator.of(dialogContext).pop(); // Close dialog
                  navigator.pushNamedAndRemoveUntil('/', (route) => false);
                }
              } catch (e) {
                if (dialogContext.mounted) {
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    SnackBar(
                      content: Text('Invalid code: ${e.toString()}'),
                      backgroundColor: Theme.of(dialogContext).colorScheme.error,
                    ),
                  );
                }
              }
            },
            child: const Text('Verify'),
          ),
        ],
      ),
    );
  }
}
