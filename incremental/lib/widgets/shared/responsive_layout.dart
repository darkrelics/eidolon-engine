import 'package:flutter/material.dart';

/// Breakpoint definitions for responsive design
class Breakpoints {
  static const double mobile = 768;
  static const double tablet = 1200;
}

/// Device type based on screen width
enum DeviceType { mobile, tablet, desktop }

/// Responsive layout widget that adapts to different screen sizes
class ResponsiveLayout extends StatelessWidget {
  final Widget mobile;
  final Widget? tablet;
  final Widget desktop;

  const ResponsiveLayout({
    super.key,
    required this.mobile,
    this.tablet,
    required this.desktop,
  });

  static DeviceType getDeviceType(BuildContext context) {
    final width = MediaQuery.of(context).size.width;

    if (width < Breakpoints.mobile) {
      return DeviceType.mobile;
    } else if (width < Breakpoints.tablet) {
      return DeviceType.tablet;
    } else {
      return DeviceType.desktop;
    }
  }

  static bool isMobile(BuildContext context) {
    return getDeviceType(context) == DeviceType.mobile;
  }

  static bool isTablet(BuildContext context) {
    return getDeviceType(context) == DeviceType.tablet;
  }

  static bool isDesktop(BuildContext context) {
    return getDeviceType(context) == DeviceType.desktop;
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= Breakpoints.tablet) {
          return desktop;
        } else if (constraints.maxWidth >= Breakpoints.mobile) {
          return tablet ?? desktop;
        } else {
          return mobile;
        }
      },
    );
  }
}

/// Helper widget for responsive padding
class ResponsivePadding extends StatelessWidget {
  final Widget child;
  final EdgeInsets? mobilePadding;
  final EdgeInsets? tabletPadding;
  final EdgeInsets? desktopPadding;

  const ResponsivePadding({
    super.key,
    required this.child,
    this.mobilePadding,
    this.tabletPadding,
    this.desktopPadding,
  });

  @override
  Widget build(BuildContext context) {
    EdgeInsets padding;

    switch (ResponsiveLayout.getDeviceType(context)) {
      case DeviceType.mobile:
        padding = mobilePadding ?? const EdgeInsets.all(8.0);
        break;
      case DeviceType.tablet:
        padding = tabletPadding ?? const EdgeInsets.all(16.0);
        break;
      case DeviceType.desktop:
        padding = desktopPadding ?? const EdgeInsets.all(24.0);
        break;
    }

    return Padding(padding: padding, child: child);
  }
}

/// Helper widget for responsive constraints
class ResponsiveConstraints extends StatelessWidget {
  final Widget child;
  final double? mobileMaxWidth;
  final double? tabletMaxWidth;
  final double? desktopMaxWidth;

  const ResponsiveConstraints({
    super.key,
    required this.child,
    this.mobileMaxWidth,
    this.tabletMaxWidth,
    this.desktopMaxWidth,
  });

  @override
  Widget build(BuildContext context) {
    double? maxWidth;

    switch (ResponsiveLayout.getDeviceType(context)) {
      case DeviceType.mobile:
        maxWidth = mobileMaxWidth;
        break;
      case DeviceType.tablet:
        maxWidth = tabletMaxWidth ?? 800;
        break;
      case DeviceType.desktop:
        maxWidth = desktopMaxWidth ?? 1400;
        break;
    }

    if (maxWidth != null) {
      return Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: child,
        ),
      );
    }

    return child;
  }
}

/// Responsive grid that adapts column count based on screen size
class ResponsiveGrid extends StatelessWidget {
  final List<Widget> children;
  final int mobileColumns;
  final int tabletColumns;
  final int desktopColumns;
  final double spacing;
  final double runSpacing;

  const ResponsiveGrid({
    super.key,
    required this.children,
    this.mobileColumns = 1,
    this.tabletColumns = 2,
    this.desktopColumns = 3,
    this.spacing = 16.0,
    this.runSpacing = 16.0,
  });

  @override
  Widget build(BuildContext context) {
    int columns;

    switch (ResponsiveLayout.getDeviceType(context)) {
      case DeviceType.mobile:
        columns = mobileColumns;
        break;
      case DeviceType.tablet:
        columns = tabletColumns;
        break;
      case DeviceType.desktop:
        columns = desktopColumns;
        break;
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        crossAxisSpacing: spacing,
        mainAxisSpacing: runSpacing,
        childAspectRatio: 1.0,
      ),
      itemCount: children.length,
      itemBuilder: (context, index) => children[index],
    );
  }
}
