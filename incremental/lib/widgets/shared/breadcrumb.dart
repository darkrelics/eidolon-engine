import 'package:flutter/material.dart';

/// A single breadcrumb item
class BreadcrumbItem {
  final String label;
  final VoidCallback? onTap;
  final IconData? icon;

  BreadcrumbItem({
    required this.label,
    this.onTap,
    this.icon,
  });
}

/// A breadcrumb navigation widget
class Breadcrumb extends StatelessWidget {
  final List<BreadcrumbItem> items;
  final Color? activeColor;
  final Color? inactiveColor;
  final double spacing;
  final Widget? separator;

  const Breadcrumb({
    super.key,
    required this.items,
    this.activeColor,
    this.inactiveColor,
    this.spacing = 8.0,
    this.separator,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final defaultActiveColor = activeColor ?? theme.colorScheme.primary;
    final defaultInactiveColor = inactiveColor ?? theme.colorScheme.onSurfaceVariant;
    final defaultSeparator = separator ?? Icon(
      Icons.chevron_right,
      size: 16,
      color: defaultInactiveColor,
    );

    return Row(
      children: [
        for (int i = 0; i < items.length; i++) ...[
          _BreadcrumbItemWidget(
            item: items[i],
            isActive: i == items.length - 1,
            activeColor: defaultActiveColor,
            inactiveColor: defaultInactiveColor,
          ),
          if (i < items.length - 1) ...[
            SizedBox(width: spacing),
            defaultSeparator,
            SizedBox(width: spacing),
          ],
        ],
      ],
    );
  }
}

/// Individual breadcrumb item widget
class _BreadcrumbItemWidget extends StatelessWidget {
  final BreadcrumbItem item;
  final bool isActive;
  final Color activeColor;
  final Color inactiveColor;

  const _BreadcrumbItemWidget({
    required this.item,
    required this.isActive,
    required this.activeColor,
    required this.inactiveColor,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isActive ? activeColor : inactiveColor;
    
    Widget content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (item.icon != null) ...[
          Icon(
            item.icon,
            size: 16,
            color: color,
          ),
          const SizedBox(width: 4),
        ],
        Text(
          item.label,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: color,
            fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ],
    );

    if (!isActive && item.onTap != null) {
      return InkWell(
        onTap: item.onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
          child: content,
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      child: content,
    );
  }
}

/// A responsive breadcrumb that collapses on mobile
class ResponsiveBreadcrumb extends StatelessWidget {
  final List<BreadcrumbItem> items;
  final Color? activeColor;
  final Color? inactiveColor;

  const ResponsiveBreadcrumb({
    super.key,
    required this.items,
    this.activeColor,
    this.inactiveColor,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isMobile = MediaQuery.of(context).size.width < 600;

    if (isMobile && items.length > 2) {
      // On mobile, show only first and last item with ellipsis
      return Row(
        children: [
          _BreadcrumbItemWidget(
            item: items.first,
            isActive: false,
            activeColor: activeColor ?? theme.colorScheme.primary,
            inactiveColor: inactiveColor ?? theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 8),
          Icon(
            Icons.more_horiz,
            size: 16,
            color: inactiveColor ?? theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(width: 8),
          _BreadcrumbItemWidget(
            item: items.last,
            isActive: true,
            activeColor: activeColor ?? theme.colorScheme.primary,
            inactiveColor: inactiveColor ?? theme.colorScheme.onSurfaceVariant,
          ),
        ],
      );
    }

    return Breadcrumb(
      items: items,
      activeColor: activeColor,
      inactiveColor: inactiveColor,
    );
  }
}