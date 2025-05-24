import 'package:flutter_test/flutter_test.dart';
import 'package:portal/main.dart';

void main() {
  testWidgets('Smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    expect(find.text('Email Verification'), findsOneWidget);
  });
}
