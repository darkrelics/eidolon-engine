import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Custom text field with validation support
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
  final String? Function(String?)? validator;
  final void Function(String)? onChanged;
  final void Function(String)? onSubmitted;
  final FocusNode? focusNode;
  final List<TextInputFormatter>? inputFormatters;
  final bool readOnly;

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
    this.validator,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.inputFormatters,
    this.readOnly = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      decoration: InputDecoration(
        labelText: labelText,
        prefixIcon: Icon(prefixIcon, color: colorScheme.onSurfaceVariant),
        hintText: hintText,
        helperText: helperText,
        helperMaxLines: helperMaxLines,
        border: const OutlineInputBorder(),
        errorMaxLines: 2,
      ),
      keyboardType: keyboardType,
      autofillHints: autofillHints,
      style: TextStyle(color: colorScheme.onSurface),
      validator: validator,
      onChanged: onChanged,
      onFieldSubmitted: onSubmitted,
      focusNode: focusNode,
      inputFormatters: inputFormatters,
      readOnly: readOnly,
      autovalidateMode: AutovalidateMode.onUserInteraction,
    );
  }
}

/// Custom loading button with animation support
class LoadingButton extends StatefulWidget {
  final bool isLoading;
  final VoidCallback? onPressed;
  final String text;
  final double fontSize;
  final Color? backgroundColor;
  final Color? foregroundColor;
  final Widget? icon;

  const LoadingButton({
    super.key,
    required this.isLoading,
    required this.onPressed,
    required this.text,
    this.fontSize = 16,
    this.backgroundColor,
    this.foregroundColor,
    this.icon,
  });

  @override
  State<LoadingButton> createState() => _LoadingButtonState();
}

class _LoadingButtonState extends State<LoadingButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
  }

  @override
  void didUpdateWidget(LoadingButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isLoading && !oldWidget.isLoading) {
      _animationController.repeat();
    } else if (!widget.isLoading && oldWidget.isLoading) {
      _animationController.stop();
    }
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return FilledButton(
      onPressed: widget.isLoading ? null : widget.onPressed,
      style: FilledButton.styleFrom(
        backgroundColor: widget.backgroundColor ?? colorScheme.primary,
        foregroundColor: widget.foregroundColor ?? colorScheme.onPrimary,
      ),
      child:
          widget.isLoading
              ? SizedBox(
                height: 24,
                width: 24,
                child: RotationTransition(
                  turns: _animationController,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: widget.foregroundColor ?? colorScheme.onPrimary,
                  ),
                ),
              )
              : Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (widget.icon != null) ...[
                    widget.icon!,
                    const SizedBox(width: 8),
                  ],
                  Text(
                    widget.text,
                    style: TextStyle(fontSize: widget.fontSize),
                  ),
                ],
              ),
    );
  }
}

/// Custom app bar with consistent styling
class AuthAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final bool showBackButton;
  final List<Widget>? actions;
  final double elevation;

  const AuthAppBar({
    super.key,
    required this.title,
    this.showBackButton = true,
    this.actions,
    this.elevation = 0,
  });

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: Text(title),
      leading:
          showBackButton
              ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () => Navigator.of(context).pop(),
              )
              : null,
      actions: actions,
      elevation: elevation,
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);
}

/// Status message display with animation
class StatusMessage extends StatelessWidget {
  final String message;
  final bool isError;
  final Duration duration;
  final VoidCallback? onTimeout;

  const StatusMessage({
    super.key,
    required this.message,
    this.isError = false,
    this.duration = const Duration(seconds: 5),
    this.onTimeout,
  });

  @override
  Widget build(BuildContext context) {
    if (message.isEmpty) return const SizedBox.shrink();

    final colorScheme = Theme.of(context).colorScheme;
    final color = isError ? colorScheme.error : colorScheme.primary;

    // Schedule timeout callback if provided
    if (onTimeout != null) {
      Future.delayed(duration, () {
        if (context.mounted) {
          onTimeout?.call();
        }
      });
    }

    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.0, end: 1.0),
      duration: const Duration(milliseconds: 300),
      builder: (context, value, child) {
        return Opacity(
          opacity: value,
          child: Transform.translate(
            offset: Offset(0, 10 * (1 - value)),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                message,
                style: TextStyle(color: color),
                textAlign: TextAlign.center,
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Background container with optional blur effect
class BackgroundContainer extends StatelessWidget {
  final Widget child;
  final double opacity;
  final bool blurBackground;
  final double blurStrength;

  const BackgroundContainer({
    super.key,
    required this.child,
    this.opacity = 0.7,
    this.blurBackground = false,
    this.blurStrength = 5.0,
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
      child:
          blurBackground
              ? BackdropFilter(
                filter: ImageFilter.blur(
                  sigmaX: blurStrength,
                  sigmaY: blurStrength,
                ),
                child: child,
              )
              : child,
    );
  }
}

/// Navigation helper for consistent routing
class NavigationHelper {
  // Prevent instantiation
  NavigationHelper._();

  static void navigateToLogin(BuildContext context, {bool clearStack = false}) {
    if (clearStack) {
      Navigator.of(context).pushNamedAndRemoveUntil('/login', (route) => false);
    } else {
      Navigator.of(context).pushReplacementNamed('/login');
    }
  }

  static void navigateToRegister(
    BuildContext context, {
    bool clearStack = false,
  }) {
    if (clearStack) {
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil('/register', (route) => false);
    } else {
      Navigator.of(context).pushReplacementNamed('/register');
    }
  }

  static void navigateToCharacterManagement(BuildContext context) {
    Navigator.of(context).pushReplacementNamed('/character-management');
  }

  static void handleAuthenticated(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
      navigateToCharacterManagement(context);
    });
  }

  static void showSnackBar(
    BuildContext context,
    String message, {
    bool isError = false,
  }) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.all(16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}

/// Custom validators for form fields
class FieldValidators {
  // Prevent instantiation
  FieldValidators._();

  static String? email(String? value) {
    if (value == null || value.isEmpty) {
      return 'Email is required';
    }
    if (!RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(value)) {
      return 'Please enter a valid email address';
    }
    return null;
  }

  static String? password(String? value, {bool checkComplexity = false}) {
    if (value == null || value.isEmpty) {
      return 'Password is required';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters long';
    }
    if (checkComplexity) {
      if (!RegExp(r'^(?=.*[a-z])').hasMatch(value)) {
        return 'Password must contain at least one lowercase letter';
      }
      if (!RegExp(r'^(?=.*[A-Z])').hasMatch(value)) {
        return 'Password must contain at least one uppercase letter';
      }
      if (!RegExp(r'^(?=.*\d)').hasMatch(value)) {
        return 'Password must contain at least one number';
      }
      if (!RegExp(r'^(?=.*[@$!%*?&])').hasMatch(value)) {
        return 'Password must contain at least one special character';
      }
    }
    return null;
  }

  static String? confirmPassword(String? value, String? originalPassword) {
    if (value == null || value.isEmpty) {
      return 'Please confirm your password';
    }
    if (value != originalPassword) {
      return 'Passwords do not match';
    }
    return null;
  }

  static String? verificationCode(String? value) {
    if (value == null || value.isEmpty) {
      return 'Verification code is required';
    }
    if (value.length < 6) {
      return 'Verification code must be at least 6 characters';
    }
    return null;
  }
}

/// Custom dialog for consistent styling
class CustomDialog extends StatelessWidget {
  final String title;
  final String content;
  final String? confirmText;
  final String? cancelText;
  final VoidCallback? onConfirm;
  final VoidCallback? onCancel;
  final bool isDestructive;

  const CustomDialog({
    super.key,
    required this.title,
    required this.content,
    this.confirmText,
    this.cancelText,
    this.onConfirm,
    this.onCancel,
    this.isDestructive = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return AlertDialog(
      title: Text(title),
      content: Text(content),
      actions: [
        if (cancelText != null)
          TextButton(
            onPressed: onCancel ?? () => Navigator.of(context).pop(),
            child: Text(cancelText!),
          ),
        if (confirmText != null)
          FilledButton(
            onPressed: onConfirm,
            style:
                isDestructive
                    ? FilledButton.styleFrom(
                      backgroundColor: colorScheme.error,
                      foregroundColor: colorScheme.onError,
                    )
                    : null,
            child: Text(confirmText!),
          ),
      ],
    );
  }

  static Future<void> show(
    BuildContext context, {
    required String title,
    required String content,
    String? confirmText,
    String? cancelText,
    VoidCallback? onConfirm,
    bool isDestructive = false,
  }) {
    return showDialog(
      context: context,
      builder:
          (context) => CustomDialog(
            title: title,
            content: content,
            confirmText: confirmText,
            cancelText: cancelText,
            onConfirm: onConfirm,
            isDestructive: isDestructive,
          ),
    );
  }
}

/// Custom shimmer loading effect for placeholders
class ShimmerLoading extends StatefulWidget {
  final Widget child;
  final bool isLoading;

  const ShimmerLoading({
    super.key,
    required this.child,
    required this.isLoading,
  });

  @override
  State<ShimmerLoading> createState() => _ShimmerLoadingState();
}

class _ShimmerLoadingState extends State<ShimmerLoading>
    with SingleTickerProviderStateMixin {
  late AnimationController _shimmerController;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController.unbounded(vsync: this)
      ..repeat(min: -0.5, max: 1.5, period: const Duration(milliseconds: 1000));
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isLoading) return widget.child;

    return AnimatedBuilder(
      animation: _shimmerController,
      builder: (context, child) {
        return ShaderMask(
          blendMode: BlendMode.srcATop,
          shaderCallback: (bounds) {
            return LinearGradient(
              colors: [
                Colors.white.withValues(alpha: 0.3),
                Colors.white.withValues(alpha: 0.5),
                Colors.white.withValues(alpha: 0.3),
              ],
              stops: const [0.1, 0.3, 0.4],
              begin: const Alignment(-1.0 - 1.5, -0.3),
              end: const Alignment(1.0 + 1.5, 0.3),
              transform: _ShimmerTransform(_shimmerController.value),
            ).createShader(bounds);
          },
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

class _ShimmerTransform extends GradientTransform {
  final double translate;

  const _ShimmerTransform(this.translate);

  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) {
    return Matrix4.translationValues(bounds.width * translate, 0.0, 0.0);
  }
}

/// Custom utility for spacing
class SpacingUtils {
  // Prevent instantiation
  SpacingUtils._();

  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;
  static const double lg = 24.0;
  static const double xl = 32.0;
  static const double xxl = 48.0;

  static const SizedBox verticalXs = SizedBox(height: xs);
  static const SizedBox verticalSm = SizedBox(height: sm);
  static const SizedBox verticalMd = SizedBox(height: md);
  static const SizedBox verticalLg = SizedBox(height: lg);
  static const SizedBox verticalXl = SizedBox(height: xl);
  static const SizedBox verticalXxl = SizedBox(height: xxl);

  static const SizedBox horizontalXs = SizedBox(width: xs);
  static const SizedBox horizontalSm = SizedBox(width: sm);
  static const SizedBox horizontalMd = SizedBox(width: md);
  static const SizedBox horizontalLg = SizedBox(width: lg);
  static const SizedBox horizontalXl = SizedBox(width: xl);
  static const SizedBox horizontalXxl = SizedBox(width: xxl);
}

/// Responsive layout builder
class ResponsiveBuilder extends StatelessWidget {
  final Widget Function(BuildContext, BoxConstraints) mobileBuilder;
  final Widget Function(BuildContext, BoxConstraints)? tabletBuilder;
  final Widget Function(BuildContext, BoxConstraints)? desktopBuilder;

  const ResponsiveBuilder({
    super.key,
    required this.mobileBuilder,
    this.tabletBuilder,
    this.desktopBuilder,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 1024 && desktopBuilder != null) {
          return desktopBuilder!(context, constraints);
        } else if (constraints.maxWidth >= 768 && tabletBuilder != null) {
          return tabletBuilder!(context, constraints);
        } else {
          return mobileBuilder(context, constraints);
        }
      },
    );
  }
}

/// Device type helper
class DeviceType {
  // Prevent instantiation
  DeviceType._();

  static bool isMobile(BuildContext context) {
    return MediaQuery.of(context).size.width < 768;
  }

  static bool isTablet(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    return width >= 768 && width < 1024;
  }

  static bool isDesktop(BuildContext context) {
    return MediaQuery.of(context).size.width >= 1024;
  }
}

/// Keyboard dismisser for better UX
class KeyboardDismisser extends StatelessWidget {
  final Widget child;

  const KeyboardDismisser({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      behavior: HitTestBehavior.opaque,
      child: child,
    );
  }
}
