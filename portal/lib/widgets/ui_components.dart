import 'package:flutter/material.dart';

class AppTextField extends StatelessWidget {
  final TextEditingController controller;
  final String labelText;
  final IconData prefixIcon;
  final String hintText;
  final bool obscureText;
  final TextInputType? keyboardType;
  final List<String>? autofillHints;
  final String? helperText;
  final int? helperMaxLines;

  const AppTextField({
    super.key,
    required this.controller,
    required this.labelText,
    required this.prefixIcon,
    required this.hintText,
    this.obscureText = false,
    this.keyboardType,
    this.autofillHints,
    this.helperText,
    this.helperMaxLines,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return TextField(
      controller: controller,
      obscureText: obscureText,
      decoration: InputDecoration(
        labelText: labelText,
        prefixIcon: Icon(
          prefixIcon,
          color: colorScheme.onSurfaceVariant,
        ),
        hintText: hintText,
        helperText: helperText,
        helperMaxLines: helperMaxLines,
        border: const OutlineInputBorder(),
      ),
      keyboardType: keyboardType,
      autofillHints: autofillHints,
      style: TextStyle(color: colorScheme.onSurface),
    );
  }
}

class LoadingButton extends StatelessWidget {
  final bool isLoading;
  final VoidCallback? onPressed;
  final String text;
  final double fontSize;

  const LoadingButton({
    super.key,
    required this.isLoading,
    required this.onPressed,
    required this.text,
    this.fontSize = 16,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return FilledButton(
      onPressed: isLoading ? null : onPressed,
      child: isLoading
          ? SizedBox(
              height: 24,
              width: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: colorScheme.onPrimary,
              ),
            )
          : Text(
              text,
              style: TextStyle(fontSize: fontSize),
            ),
    );
  }
}

class AuthAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final bool showBackButton;

  const AuthAppBar({
    super.key,
    required this.title,
    this.showBackButton = true,
  });

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: Text(title),
      leading: showBackButton
          ? IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: () => Navigator.of(context).pop(),
            )
          : null,
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);
}

class StatusMessage extends StatelessWidget {
  final String message;
  final bool isError;

  const StatusMessage({
    super.key,
    required this.message,
    this.isError = false,
  });

  @override
  Widget build(BuildContext context) {
    if (message.isEmpty) return const SizedBox.shrink();

    final colorScheme = Theme.of(context).colorScheme;
    final color = isError ? colorScheme.error : colorScheme.primary;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Text(
        message,
        style: TextStyle(color: color),
        textAlign: TextAlign.center,
      ),
    );
  }
}

class BackgroundContainer extends StatelessWidget {
  final Widget child;
  final double opacity;

  const BackgroundContainer({
    super.key,
    required this.child,
    this.opacity = 0.7,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        image: DecorationImage(
          image: const AssetImage('assets/background.jpg'),
          fit: BoxFit.cover,
          colorFilter: ColorFilter.mode(
            Theme.of(context).colorScheme.surface.withValues(alpha: opacity),
            BlendMode.dstATop,
          ),
        ),
      ),
      child: child,
    );
  }
}

class NavigationHelper {
  static void navigateToLogin(BuildContext context, {bool clearState = true}) {
    if (clearState) {
      // Add logic to clear auth state if needed
    }
    Navigator.of(context).pushReplacementNamed('/login');
  }

  static void navigateToRegister(BuildContext context, {bool clearState = true}) {
    if (clearState) {
      // Add logic to clear auth state if needed
    }
    Navigator.of(context).pushReplacementNamed('/register');
  }

  static void navigateToCharacterManagement(BuildContext context) {
    Navigator.of(context).pushReplacementNamed('/character-management');
  }

  static void handleAuthenticated(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      navigateToCharacterManagement(context);
    });
  }
}