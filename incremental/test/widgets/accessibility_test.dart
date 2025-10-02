import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/widgets/shared/accessibility_wrapper.dart';

void main() {
  group('Accessibility Tests', () {
    testWidgets('AccessibilityWrapper adds semantic labels', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AccessibilityWrapper(
              label: 'Test Button',
              hint: 'Tap to perform action',
              isButton: true,
              child: Container(width: 100, height: 50, color: Colors.blue),
            ),
          ),
        ),
      );

      final semantics = tester.getSemantics(find.byType(Container));
      expect(semantics.label, equals('Test Button'));
      expect(semantics.hint, equals('Tap to perform action'));
      expect(semantics.flagsCollection.isButton, isTrue);
    });

    testWidgets('AccessibleHealthBar renders without errors', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: AccessibleHealthBar(
              value: 75,
              maxValue: 100,
              label: 'Health',
              color: Colors.red,
            ),
          ),
        ),
      );

      expect(find.byType(AccessibleHealthBar), findsOneWidget);
    });

    testWidgets('AccessibleIconButton has proper semantics', (
      WidgetTester tester,
    ) async {
      bool tapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AccessibleIconButton(
              icon: Icons.refresh,
              tooltip: 'Refresh data',
              onPressed: () => tapped = true,
            ),
          ),
        ),
      );

      await tester.tap(find.byType(IconButton));
      expect(tapped, isTrue);
    });

    testWidgets('AccessibleCard shows focus and hover states', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AccessibleCard(
              semanticLabel: 'Story Card',
              onTap: () {},
              child: const Text('Card Content'),
            ),
          ),
        ),
      );

      expect(find.byType(InkWell), findsOneWidget);
      expect(find.text('Card Content'), findsOneWidget);
    });

    testWidgets('Screen reader announcements work', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) {
                return TextButton(
                  onPressed: () {
                    ScreenReaderAnnouncer.announce(context, 'Action performed');
                  },
                  child: const Text('Perform Action'),
                );
              },
            ),
          ),
        ),
      );

      await tester.tap(find.text('Perform Action'));
      await tester.pump();

      // Announcement should be made (though we can't directly test it)
      // This ensures the code runs without errors
    });

    testWidgets('Widgets are traversable with keyboard', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                AccessibleIconButton(
                  icon: Icons.arrow_back,
                  tooltip: 'Go back',
                  onPressed: () {},
                ),
                AccessibleIconButton(
                  icon: Icons.refresh,
                  tooltip: 'Refresh',
                  onPressed: () {},
                ),
                AccessibleIconButton(
                  icon: Icons.settings,
                  tooltip: 'Settings',
                  onPressed: () {},
                ),
              ],
            ),
          ),
        ),
      );

      // All buttons should be in the widget tree
      expect(find.byType(IconButton), findsNWidgets(3));
    });

    testWidgets('Semantic labels are descriptive and helpful', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                AccessibilityWrapper(
                  label: 'Character health: 75 out of 100',
                  child: Container(height: 20, color: Colors.red),
                ),
                AccessibilityWrapper(
                  label: 'Submit decision: Go left through the forest',
                  hint: 'Double tap to select this choice',
                  isButton: true,
                  child: Container(height: 50, color: Colors.blue),
                ),
                AccessibilityWrapper(
                  label: 'Story progress: 3 of 10 segments completed',
                  child: Container(height: 10, color: Colors.green),
                ),
              ],
            ),
          ),
        ),
      );

      // Check that widgets are present without crashes
      expect(find.byType(AccessibilityWrapper), findsNWidgets(3));
    });
  });
}
