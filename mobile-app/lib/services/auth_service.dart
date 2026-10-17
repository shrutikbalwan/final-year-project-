import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'session.dart';

class AuthenticationException implements Exception {
  const AuthenticationException(this.message);
  final String message;
  @override
  String toString() => message;
}

class AuthService {
  AuthService({
    required SessionRepository sessions,
    required http.Client client,
    String tokenUrl = AppConfig.authTokenUrl,
  }) : _sessions = sessions,
       _client = client,
       _tokenUrl = tokenUrl;

  final SessionRepository _sessions;
  final http.Client _client;
  final String _tokenUrl;

  Future<UserSession> signIn(String username, String password) async {
    if (username.trim().isEmpty || password.isEmpty) {
      throw const AuthenticationException('Enter both username and password.');
    }
    if (_tokenUrl.isEmpty) {
      throw const AuthenticationException(
        'Authentication is not configured for this backend.',
      );
    }
    final uri = Uri.tryParse(_tokenUrl);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      throw const AuthenticationException('The authentication URL is invalid.');
    }
    final localDevelopment =
        !kReleaseMode &&
        (uri.host == 'localhost' ||
            uri.host == '127.0.0.1' ||
            uri.host == '10.0.2.2');
    if (uri.scheme != 'https' && !localDevelopment) {
      throw const AuthenticationException(
        'Sign-in requires HTTPS outside local development.',
      );
    }
    try {
      final response = await _client
          .post(
            uri,
            headers: const {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
            },
            body: jsonEncode({'username': username, 'password': password}),
          )
          .timeout(const Duration(seconds: 12));
      if (response.statusCode == 401 || response.statusCode == 403) {
        throw const AuthenticationException(
          'The sign-in details were rejected.',
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw AuthenticationException(
          'The sign-in service returned ${response.statusCode}.',
        );
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) {
        throw const AuthenticationException(
          'The sign-in response was invalid.',
        );
      }
      final session = UserSession.fromJson(decoded);
      if (session.isExpired) {
        throw const AuthenticationException(
          'The sign-in token is already expired.',
        );
      }
      await _sessions.save(session);
      return session;
    } on AuthenticationException {
      rethrow;
    } on http.ClientException {
      throw const AuthenticationException('Cannot reach the sign-in service.');
    } on FormatException {
      throw const AuthenticationException('The sign-in response was invalid.');
    } on Exception {
      throw const AuthenticationException('Sign-in could not be completed.');
    }
  }

  Future<void> signOut() => _sessions.clear();
}
