import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

enum UserRole { administrator, viewer, supervisor }

class UserSession {
  const UserSession({
    required this.userId,
    required this.role,
    required this.expiresAt,
    this.accessToken,
    this.development = false,
  });

  final String userId;
  final UserRole role;
  final DateTime expiresAt;
  final String? accessToken;
  final bool development;

  bool get isExpired =>
      !development && !expiresAt.isAfter(DateTime.now().toUtc());
  bool get isAuthenticated =>
      !development && (accessToken?.isNotEmpty ?? false);

  Map<String, Object?> toJson() => {
    'user_id': userId,
    'role': role.name,
    'expires_at': expiresAt.toUtc().toIso8601String(),
    'access_token': accessToken,
  };

  factory UserSession.fromJson(Map<String, dynamic> json) {
    final role = UserRole.values.where((item) => item.name == json['role']);
    if (role.isEmpty) throw const FormatException('Unsupported session role');
    final token = json['access_token'];
    if (token is! String || token.isEmpty) {
      throw const FormatException('Session is missing an access token');
    }
    final userId = json['user_id'];
    if (userId is! String || userId.isEmpty) {
      throw const FormatException('Session is missing a user ID');
    }
    final expiresAt = json['expires_at'];
    if (expiresAt is! String) {
      throw const FormatException('Session is missing an expiration timestamp');
    }
    if (!RegExp(r'(?:Z|\+00:00)$').hasMatch(expiresAt)) {
      throw const FormatException('Session expiration must be a UTC timestamp');
    }
    return UserSession(
      userId: userId,
      role: role.first,
      expiresAt: DateTime.parse(expiresAt).toUtc(),
      accessToken: token,
    );
  }

  String encode() => jsonEncode(toJson());
}

abstract interface class SessionVault {
  Future<String?> read();
  Future<void> write(String sessionJson);
  Future<void> clear();
}

class SecureSessionVault implements SessionVault {
  SecureSessionVault([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'smart_safety_helmet.session.v1';
  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String sessionJson) =>
      _storage.write(key: _key, value: sessionJson);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

class SessionRepository {
  SessionRepository(this._vault);
  final SessionVault _vault;

  Future<UserSession?> restore() async {
    final raw = await _vault.read();
    if (raw == null) return null;
    try {
      final value = jsonDecode(raw);
      if (value is! Map<String, dynamic>) throw const FormatException();
      final session = UserSession.fromJson(value);
      if (session.isExpired) {
        await _vault.clear();
        return null;
      }
      return session;
    } on FormatException {
      await _vault.clear();
      return null;
    }
  }

  Future<void> save(UserSession session) => _vault.write(session.encode());
  Future<void> clear() => _vault.clear();
}
