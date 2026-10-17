import 'package:flutter_test/flutter_test.dart';
import 'package:smart_safety_helmet_mobile/services/session.dart';

void main() {
  test('stores provider session in a serializable token record', () {
    final session = UserSession(
      userId: 'supervisor-01',
      role: UserRole.supervisor,
      expiresAt: DateTime.utc(2027),
      accessToken: 'test-token',
    );
    final restored = UserSession.fromJson(session.toJson());
    expect(restored.userId, 'supervisor-01');
    expect(restored.role, UserRole.supervisor);
    expect(restored.accessToken, 'test-token');
    expect(restored.isAuthenticated, isTrue);
  });

  test('rejects expired sessions', () {
    final session = UserSession(
      userId: 'viewer-01',
      role: UserRole.viewer,
      expiresAt: DateTime.utc(2020),
      accessToken: 'expired-token',
    );
    expect(session.isExpired, isTrue);
  });

  test('rejects malformed and unsupported session records', () {
    expect(
      () => UserSession.fromJson({'role': 'admin'}),
      throwsFormatException,
    );
    expect(
      () => UserSession.fromJson({
        'user_id': 'x',
        'role': 'admin',
        'expires_at': '2027-01-01T00:00:00Z',
        'access_token': 'token',
      }),
      throwsFormatException,
    );
  });

  test('clears an expired restored session', () async {
    final vault = _MemoryVault(
      '''{"user_id":"viewer-01","role":"viewer","expires_at":"2020-01-01T00:00:00Z","access_token":"expired"}''',
    );
    expect(await SessionRepository(vault).restore(), isNull);
    expect(vault.value, isNull);
  });
}

class _MemoryVault implements SessionVault {
  _MemoryVault([this.value]);
  String? value;
  @override
  Future<void> clear() async => value = null;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String sessionJson) async => value = sessionJson;
}
