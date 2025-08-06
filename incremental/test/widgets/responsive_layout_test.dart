import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/widgets/shared/responsive_layout.dart';

void main() {
  group('ResponsiveLayout Tests', () {
    Widget createTestWidget({
      required Widget mobile,
      required Widget tablet,
      required Widget desktop,
      double width = 800,
    }) {
      return MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(size: Size(width, 600)),
          child: ResponsiveLayout(
            mobile: mobile,
            tablet: tablet,
            desktop: desktop,
          ),
        ),
      );
    }

    testWidgets('shows mobile layout on small screens',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 400, // Mobile width
        ),
      );

      expect(find.text('Mobile'), findsOneWidget);
      expect(find.text('Tablet'), findsNothing);
      expect(find.text('Desktop'), findsNothing);
    });

    testWidgets('shows tablet layout on medium screens',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 900, // Tablet width
        ),
      );

      expect(find.text('Mobile'), findsNothing);
      expect(find.text('Tablet'), findsOneWidget);
      expect(find.text('Desktop'), findsNothing);
    });

    testWidgets('shows desktop layout on large screens',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 1400, // Desktop width
        ),
      );

      expect(find.text('Mobile'), findsNothing);
      expect(find.text('Tablet'), findsNothing);
      expect(find.text('Desktop'), findsOneWidget);
    });

    test('getDeviceType returns correct device type', () {
      // Test context with different screen widths
      expect(
        getDeviceTypeFromWidth(400),
        equals(DeviceType.mobile),
      );
      expect(
        getDeviceTypeFromWidth(767),
        equals(DeviceType.mobile),
      );
      expect(
        getDeviceTypeFromWidth(768),
        equals(DeviceType.tablet),
      );
      expect(
        getDeviceTypeFromWidth(1199),
        equals(DeviceType.tablet),
      );
      expect(
        getDeviceTypeFromWidth(1200),
        equals(DeviceType.desktop),
      );
      expect(
        getDeviceTypeFromWidth(1920),
        equals(DeviceType.desktop),
      );
    });

    testWidgets('responsive layout works with different builders',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(size: Size(800, 600)),
            child: Builder(
              builder: (context) {
                final deviceType = ResponsiveLayout.getDeviceType(context);
                switch (deviceType) {
                  case DeviceType.mobile:
                    return const Text('Mobile View');
                  case DeviceType.tablet:
                    return const Text('Tablet View');
                  case DeviceType.desktop:
                    return const Text('Desktop View');
                }
              },
            ),
          ),
        ),
      );

      expect(find.text('Tablet View'), findsOneWidget);
    });

    testWidgets('layout transitions smoothly between breakpoints',
        (WidgetTester tester) async {
      // Start with mobile
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 400,
        ),
      );
      expect(find.text('Mobile'), findsOneWidget);

      // Transition to tablet
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 800,
        ),
      );
      await tester.pump();
      expect(find.text('Tablet'), findsOneWidget);

      // Transition to desktop
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 1300,
        ),
      );
      await tester.pump();
      expect(find.text('Desktop'), findsOneWidget);
    });

    testWidgets('handles edge cases at breakpoints',
        (WidgetTester tester) async {
      // Test at exact breakpoint (768)
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 768,
        ),
      );
      expect(find.text('Tablet'), findsOneWidget);

      // Test at exact breakpoint (1200)
      await tester.pumpWidget(
        createTestWidget(
          mobile: const Text('Mobile'),
          tablet: const Text('Tablet'),
          desktop: const Text('Desktop'),
          width: 1200,
        ),
      );
      await tester.pump();
      expect(find.text('Desktop'), findsOneWidget);
    });
  });
}

// Helper function for testing
DeviceType getDeviceTypeFromWidth(double width) {
  if (width < Breakpoints.mobile) {
    return DeviceType.mobile;
  } else if (width < Breakpoints.tablet) {
    return DeviceType.tablet;
  } else {
    return DeviceType.desktop;
  }
}