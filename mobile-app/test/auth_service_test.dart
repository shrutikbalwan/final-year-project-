import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smart_safety_helmet_mobile/services/auth_service.dart';
import 'package:smart_safety_helmet_mobile/services/session.dart';

void main() {
  test(
    'sends credentials to configured provider and persists its token only',
    () async {
      final vault = _MemoryVault();
      final service = AuthService(
        sessions: SessionRepository(vault),
        tokenUrl: 'https://identity.example.test/token',
        client: MockClient((request) async {
          expect(request.url.toString(), 'https://identity.example.test/token');
          expect(jsonDecode(request.body), {
            'username': 'supervisor',
            'password': 'temporary-password',
          });
          return http.Response(
            jsonEncode({
              'access_token': 'issued-token',
              'user_id': 'supervisor-01',
              'role': 'supervisor',
              'expires_at': '2027-01-01T00:00:00Z',
            }),
            200,
          );
        }),
      );

      final session = await service.signIn('supervisor', 'temporary-password');
      expect(session.accessToken, 'issued-token');
      expect(vault.value, contains('issued-token'));
      expect(vault.value, isNot(contains('temporary-password')));
    },
  );

  test('does not contact a provider when no endpoint is configured', () async {
    final service = AuthService(
      sessions: SessionRepository(_MemoryVault()),
      tokenUrl: '',
      client: MockClient((_) async => throw StateError('must not be called')),
    );
    await expectLater(
      service.signIn('x', 'y'),
      throwsA(isA<AuthenticationException>()),
    );
  });
}

class _MemoryVault implements SessionVault {
  String? value;
  @override
  Future<void> clear() async => value = null;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String sessionJson) async => value = sessionJson;
}
