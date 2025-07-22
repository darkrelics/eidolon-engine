// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:eidolon_incremental/main.dart';

void main() {
  testWidgets('Main game screen loads', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const EidolonIncrementalApp());

    // Verify that the main panels are present
    expect(find.text('Character'), findsOneWidget);
    expect(find.text('Current Action'), findsOneWidget);
    expect(find.text('Inventory'), findsOneWidget);

    // Verify placeholder content
    expect(find.text('Name: Hero'), findsOneWidget);
    expect(find.text('Class: Warrior'), findsOneWidget);
    expect(find.text('Level: 1'), findsOneWidget);
  });
}
