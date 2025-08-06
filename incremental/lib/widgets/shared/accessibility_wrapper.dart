import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

/// Wrapper widget that adds accessibility features
class AccessibilityWrapper extends StatelessWidget {
  final Widget child;
  final String? label;
  final String? hint;
  final bool isButton;
  final bool isHeader;
  final VoidCallback? onTap;
  final bool excludeSemantics;

  const AccessibilityWrapper({
    super.key,
    required this.child,
    this.label,
    this.hint,
    this.isButton = false,
    this.isHeader = false,
    this.onTap,
    this.excludeSemantics = false,
  });

  @override
  Widget build(BuildContext context) {
    if (excludeSemantics) {
      return ExcludeSemantics(
        child: child,
      );
    }

    return Semantics(
      label: label,
      hint: hint,
      button: isButton,
      header: isHeader,
      onTap: onTap,
      child: child,
    );
  }
}

/// Health bar with accessibility
class AccessibleHealthBar extends StatelessWidget {
  final double value;
  final double maxValue;
  final String label;
  final Color? color;
  final Color? backgroundColor;

  const AccessibleHealthBar({
    super.key,
    required this.value,
    required this.maxValue,
    required this.label,
    this.color,
    this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    final percentage = (value / maxValue * 100).clamp(0, 100).toInt();
    final theme = Theme.of(context);

    return Semantics(
      label: '$label: $value of $maxValue',
      value: '$percentage%',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: theme.textTheme.bodySmall,
              ),
              Text(
                '${value.toInt()} / ${maxValue.toInt()}',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value / maxValue,
              backgroundColor: backgroundColor ?? 
                  theme.colorScheme.surfaceContainerHighest,
              valueColor: AlwaysStoppedAnimation<Color>(
                color ?? theme.colorScheme.primary,
              ),
              minHeight: 8,
            ),
          ),
        ],
      ),
    );
  }
}

/// Accessible icon button
class AccessibleIconButton extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final Color? color;
  final double? size;

  const AccessibleIconButton({
    super.key,
    required this.icon,
    required this.tooltip,
    this.onPressed,
    this.color,
    this.size,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: tooltip,
      enabled: onPressed != null,
      child: IconButton(
        icon: Icon(icon, color: color, size: size),
        onPressed: onPressed,
        tooltip: tooltip,
      ),
    );
  }
}

/// Accessible card with focus indicators
class AccessibleCard extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final String? semanticLabel;
  final EdgeInsetsGeometry? margin;
  final EdgeInsetsGeometry? padding;
  final bool selected;

  const AccessibleCard({
    super.key,
    required this.child,
    this.onTap,
    this.semanticLabel,
    this.margin,
    this.padding,
    this.selected = false,
  });

  @override
  State<AccessibleCard> createState() => _AccessibleCardState();
}

class _AccessibleCardState extends State<AccessibleCard> {
  bool _focused = false;
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return Semantics(
      label: widget.semanticLabel,
      button: widget.onTap != null,
      selected: widget.selected,
      child: Container(
        margin: widget.margin,
        child: InkWell(
          onTap: widget.onTap,
          onFocusChange: (focused) {
            setState(() {
              _focused = focused;
            });
          },
          onHover: (hovered) {
            setState(() {
              _hovered = hovered;
            });
          },
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: widget.padding ?? const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: widget.selected
                  ? theme.colorScheme.primaryContainer
                  : theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: _focused
                    ? theme.colorScheme.primary
                    : _hovered
                        ? theme.colorScheme.primary.withValues(alpha: 0.5)
                        : widget.selected
                            ? theme.colorScheme.primary
                            : theme.colorScheme.outline.withValues(alpha: 0.3),
                width: _focused ? 2 : 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: theme.colorScheme.shadow.withValues(alpha: 0.1),
                  blurRadius: _hovered ? 8 : 4,
                  offset: Offset(0, _hovered ? 4 : 2),
                ),
              ],
            ),
            child: widget.child,
          ),
        ),
      ),
    );
  }
}

/// Screen reader announcements
class ScreenReaderAnnouncer {
  static void announce(BuildContext context, String message) {
    SemanticsService.announce(message, TextDirection.ltr);
  }

  static void announceSuccess(BuildContext context, String message) {
    SemanticsService.announce('Success: $message', TextDirection.ltr);
  }

  static void announceError(BuildContext context, String message) {
    SemanticsService.announce('Error: $message', TextDirection.ltr);
  }

  static void announceLoading(BuildContext context, String message) {
    SemanticsService.announce('Loading: $message', TextDirection.ltr);
  }
}

/// High contrast mode detector
class HighContrastDetector extends StatelessWidget {
  final Widget child;
  final Widget? highContrastChild;

  const HighContrastDetector({
    super.key,
    required this.child,
    this.highContrastChild,
  });

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final isHighContrast = mediaQuery.highContrast;

    if (isHighContrast && highContrastChild != null) {
      return highContrastChild!;
    }

    return child;
  }
}

/// Focus trap for modal dialogs
class FocusTrap extends StatefulWidget {
  final Widget child;
  final bool enabled;

  const FocusTrap({
    super.key,
    required this.child,
    this.enabled = true,
  });

  @override
  State<FocusTrap> createState() => _FocusTrapState();
}

class _FocusTrapState extends State<FocusTrap> {
  final FocusScopeNode _focusScopeNode = FocusScopeNode();

  @override
  void dispose() {
    _focusScopeNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return widget.child;
    }

    return FocusScope(
      node: _focusScopeNode,
      child: widget.child,
    );
  }
}