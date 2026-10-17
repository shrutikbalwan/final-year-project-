import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smart_safety_helmet_mobile/screens/login_screen.dart';
import 'package:smart_safety_helmet_mobile/services/auth_service.dart';
import 'package:smart_safety_helmet_mobile/services/session.dart';
import 'package:smart_safety_helmet_mobile/widgets/status_badge.dart';

void main() {
  testWidgets('status badge displays Unknown without implying Normal', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: StatusBadge(label: 'Unknown')),
      ),
    );
    expect(find.text('Unknown'), findsOneWidget);
    expect(find.text('Normal'), findsNothing);
  });

  testWidgets('login presents the authenticated API sign-in form', (
    tester,
  ) async {
    final auth = AuthService(
      sessions: SessionRepository(_MemoryVault()),
      tokenUrl: '',
      client: MockClient((_) async => http.Response('{}', 200)),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: LoginScreen(auth: auth, onAuthenticated: (_) {}),
      ),
    );
    expect(find.text('Username'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });
}

class _MemoryVault implements SessionVault {
  @override
  Future<void> clear() async {}
  @override
  Future<String?> read() async => null;
  @override
  Future<void> write(String sessionJson) async {}
}
