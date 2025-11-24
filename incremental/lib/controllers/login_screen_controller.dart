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
      if (context.mounted) {
        // Check for MFA requirement
        // Note: We check the string representation or specific error type if available
        // Since we rethrow CognitoClientException with code 'MFA_REQUIRED'
        final isMfaRequired = e.toString().contains('MFA_REQUIRED');

        if (isMfaRequired) {
          _isLoading = false;
          notifyListeners();
          await _showMfaDialog(context);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'signIn')),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _showMfaDialog(BuildContext context) async {
    final codeController = TextEditingController();

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
                final authProvider = context.read<AuthProvider>();
                await authProvider.respondToMfaChallenge(codeController.text);

                if (dialogContext.mounted) {
                  Navigator.of(dialogContext).pop(); // Close dialog
                  if (context.mounted) {
                    Navigator.of(context).pushNamedAndRemoveUntil('/', (route) => false);
                  }
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
