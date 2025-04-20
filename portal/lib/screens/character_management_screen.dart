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

class CharacterManagementScreen extends StatelessWidget {
  const CharacterManagementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final authState = Provider.of<AuthState>(context);
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    // Double-check authentication on build
    if (!authState.isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.of(context).pushReplacementNamed('/login');
      });
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Character Management'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              // Show confirmation dialog
              await CustomDialog.show(
                context,
                title: 'Sign Out',
                content: 'Are you sure you want to sign out?',
                confirmText: 'SIGN OUT',
                cancelText: 'CANCEL',
                onConfirm: () async {
                  Navigator.of(context).pop();
                  await authState.signOut();
                  if (context.mounted) {
                    Navigator.of(context).pushReplacementNamed('/');
                  }
                },
                isDestructive: true,
              );
            },
          ),
        ],
      ),
      body: BackgroundContainer(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Welcome, Adventurer',
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                Text(
                  'Character Management will be available soon.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: colorScheme.onSurface.withValues(alpha: 0.7),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                Card(
                  color: colorScheme.surface.withValues(alpha: 0.1),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                    side: BorderSide(
                      color: colorScheme.outline.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      children: [
                        Text(
                          'Character Creation Coming Soon',
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'This feature will connect to AWS Lambda functions to manage character creation, stats, inventory, and progression within the Eidolon Engine world.',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: colorScheme.onSurface.withValues(alpha: 0.7),
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 24),
                        FilledButton.tonal(
                          onPressed: () {
                            // Show coming soon message
                            NavigationHelper.showSnackBar(
                              context,
                              'Character creation coming soon!',
                            );
                          },
                          child: const Text('Create New Character'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 40),
                Center(
                  child: Text(
                    'Stay tuned for updates!',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontStyle: FontStyle.italic,
                      color: colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}