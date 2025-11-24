import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:qr_flutter/qr_flutter.dart';

class MfaSetupScreen extends StatefulWidget {
  const MfaSetupScreen({super.key});

  @override
  State<MfaSetupScreen> createState() => _MfaSetupScreenState();
}

class _MfaSetupScreenState extends State<MfaSetupScreen> {
  final _codeController = TextEditingController();
  String? _secretKey;
  bool _isLoading = true;
  bool _isVerifying = false;

  @override
  void initState() {
    super.initState();
    _loadSecret();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _loadSecret() async {
    try {
      final secret = await context.read<AuthProvider>().setupMfa();
      if (mounted) {
        setState(() {
          _secretKey = secret;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'MFA Setup')),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Future<void> _verifyCode() async {
    if (_codeController.text.length < 6) return;

    setState(() {
      _isVerifying = true;
    });

    try {
      final success = await context.read<AuthProvider>().verifyMfaSetup(_codeController.text);
      if (mounted) {
        if (success) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('MFA Enabled Successfully')));
          Navigator.of(context).pop();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: const Text('Invalid code. Please try again.'), backgroundColor: Theme.of(context).colorScheme.error),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(ErrorHandler.getUserFriendlyMessage(e, context: 'MFA Verify')),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isVerifying = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Setup MFA')),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _secretKey == null
          ? const Center(child: Text('Failed to load MFA secret'))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Secure your account',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Scan the QR code below with your authenticator app (Google Authenticator, Authy, etc.) or enter the secret key manually.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Column(
                      children: [
                        if (_secretKey != null)
                          QrImageView(
                            data:
                                'otpauth://totp/EidolonEngine:${context.read<AuthProvider>().userEmail}?secret=$_secretKey&issuer=EidolonEngine',
                            version: QrVersions.auto,
                            size: 200.0,
                            backgroundColor: Colors.white,
                          ),
                        const SizedBox(height: 16),
                        const Text('Secret Key:', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        SelectableText(_secretKey!, style: const TextStyle(fontFamily: 'monospace', fontSize: 16)),
                        TextButton.icon(
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: _secretKey!));
                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Secret copied to clipboard')));
                          },
                          icon: const Icon(Icons.copy),
                          label: const Text('Copy Secret'),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _codeController,
                    decoration: const InputDecoration(
                      labelText: 'Verification Code',
                      hintText: 'Enter 6-digit code',
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _isVerifying ? null : _verifyCode,
                    child: _isVerifying
                        ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Verify and Enable'),
                  ),
                ],
              ),
            ),
    );
  }
}
