// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:eidolon_incremental/main.dart';

void main() {
  testWidgets('App loads authentication screen', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const EidolonIncrementalApp());

    // Verify that the auth screen is shown
    expect(find.text('Eidolon Engine'), findsOneWidget);
    expect(find.text('Incremental'), findsOneWidget);
    
    // Verify auth buttons are present
    expect(find.text('Sign In'), findsOneWidget);
    expect(find.text('Create Account'), findsOneWidget);
  });
}
