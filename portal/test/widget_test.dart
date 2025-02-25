import 'package:flutter_test/flutter_test.dart';
import 'package:cognito_email_verification/main.dart';

void main() {
  testWidgets('Smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    expect(find.text('Email Verification'), findsOneWidget);
  });
}
