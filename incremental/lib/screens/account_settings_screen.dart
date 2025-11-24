// Eidolon Engine
//
// Copyright 2024‑2025 Jason E. Robinson

import 'package:eidolon_incremental/constants/navigation_constants.dart';
import 'package:eidolon_incremental/controllers/account_settings_controller.dart';
import 'package:eidolon_incremental/providers/auth_provider.dart';
import 'package:eidolon_incremental/providers/theme_provider.dart';
import 'package:eidolon_incremental/screens/mfa_setup_screen.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
import 'package:eidolon_incremental/widgets/shared/keyboard_shortcuts.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class AccountSettingsScreen extends StatelessWidget {
  const AccountSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AccountSettingsController(authProvider: context.read<AuthProvider>()),
      child: const _AccountSettingsView(),
    );
  }
}

class _AccountSettingsView extends StatefulWidget {
  const _AccountSettingsView();

  @override
  State<_AccountSettingsView> createState() => _AccountSettingsViewState();
}

class _AccountSettingsViewState extends State<_AccountSettingsView> {
  Future<void> _handleSignOut() async {
    final controller = context.read<AccountSettingsController>();

    await controller.signOut(
      onSuccess: () {
        if (mounted) {
          Navigator.pushReplacementNamed(context, '/login');
        }
      },
      onError: (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(ErrorHandler.getUserFriendlyMessage(error, context: 'signOut')),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
    );
  }

  Future<void> _handleDeleteAccount() async {
    final confirmed = await _showDeleteConfirmationDialog();
    if (!confirmed || !mounted) return;

    final doubleConfirmed = await _showFinalDeleteConfirmationDialog();
    if (!doubleConfirmed || !mounted) return;

    if (!mounted) return;

    final controller = context.read<AccountSettingsController>();
    await controller.deleteAccount(
      onSuccess: () {
        if (mounted) {
          Navigator.pushReplacementNamed(
            context,
            '/login',
            arguments: {NavigationConstants.messageKey: 'Your account has been deleted'},
          );
        }
      },
      onError: (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(ErrorHandler.getUserFriendlyMessage(error, context: 'deleteAccount')),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      },
    );
  }

  Future<bool> _showDeleteConfirmationDialog() async {
    return await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (BuildContext context) {
            return AlertDialog(
              title: const Text('Delete Account?'),
              content: const Text(
                'Are you sure you want to delete your account? This action cannot be undone and all your data will be permanently lost.',
              ),
              actions: [
                TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  style: TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
                  child: const Text('Delete'),
                ),
              ],
            );
          },
        ) ??
        false;
  }

  Future<bool> _showFinalDeleteConfirmationDialog() async {
    return await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (BuildContext context) {
            return AlertDialog(
              title: const Text('Final Confirmation'),
              content: const Text(
                'This is your last chance. Your account and all associated data will be permanently deleted. Are you absolutely sure?',
              ),
              actions: [
                TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
                  child: const Text('Yes, Delete My Account'),
                ),
              ],
            );
          },
        ) ??
        false;
  }

  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    final controller = context.watch<AccountSettingsController>();
    final userEmail = authProvider.userEmail;
    final isLoading = controller.isLoading;

    return Scaffold(
      appBar: AppBar(title: const Text('Account Settings')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: ListTile(
                leading: const Icon(Icons.person),
                title: const Text('Email'),
                subtitle: Text(userEmail ?? 'Not available'),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.palette),
                    title: const Text('Appearance'),
                    subtitle: const Text('Customize the app appearance'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.brightness_6),
                    title: const Text('Theme'),
                    subtitle: const Text('Choose between light, dark, or system theme'),
                    trailing: const ThemeModeSelector(),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.help),
                    title: const Text('Help'),
                    subtitle: const Text('Get help with the app'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.keyboard),
                    title: const Text('Keyboard Shortcuts'),
                    subtitle: const Text('View available keyboard shortcuts'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => KeyboardShortcutHelp.show(context),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.security),
                    title: const Text('Security'),
                    subtitle: const Text('Manage your account security'),
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.security),
                    title: const Text('Multi-Factor Authentication'),
                    subtitle: const Text('Secure your account with 2FA'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {
                      Navigator.of(context).push(MaterialPageRoute(builder: (_) => const MfaSetupScreen()));
                    },
                  ),
                  const Divider(),
                  ListTile(
                    leading: const Icon(Icons.logout, color: Colors.red),
                    title: const Text('Change Password'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: isLoading
                        ? null
                        : () {
                            Navigator.pushNamed(context, '/forgot-password');
                          },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: Icon(Icons.warning, color: Theme.of(context).colorScheme.error),
                    title: const Text('Danger Zone'),
                    subtitle: const Text('Irreversible actions'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: Icon(Icons.delete_forever, color: Theme.of(context).colorScheme.error),
                    title: Text('Delete Account', style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    subtitle: const Text('Permanently delete your account and all data'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: isLoading ? null : _handleDeleteAccount,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),
            Center(
              child: OutlinedButton.icon(
                onPressed: isLoading ? null : _handleSignOut,
                icon: const Icon(Icons.logout),
                label: isLoading
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Sign Out'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
