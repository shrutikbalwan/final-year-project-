import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/helmet.dart';
import '../models/incident.dart';
import 'session.dart';

enum ApiFailureKind {
  network,
  unauthorized,
  forbidden,
  notFound,
  server,
  invalid,
}

class ApiFailure implements Exception {
  const ApiFailure(this.kind, this.message, {this.statusCode});
  final ApiFailureKind kind;
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class HelmetApi {
  HelmetApi({
    required this.baseUrl,
    required http.Client client,
    UserSession? Function()? sessionProvider,
    void Function()? onUnauthorized,
  }) : _client = client,
       _sessionProvider = sessionProvider ?? (() => null),
       _onUnauthorized = onUnauthorized;

  final String baseUrl;
  final http.Client _client;
  final UserSession? Function() _sessionProvider;
  final void Function()? _onUnauthorized;

  Map<String, String> get _headers {
    final token = _sessionProvider()?.accessToken;
    return {
      'Accept': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> _getObject(
    String path, {
    String? method,
    Object? body,
  }) async {
    final payload = await _request(path, method: method, body: body);
    if (payload is Map<String, dynamic>) return payload;
    throw const ApiFailure(
      ApiFailureKind.invalid,
      'The API returned an invalid object.',
    );
  }

  Future<dynamic> _request(String path, {String? method, Object? body}) async {
    final session = _sessionProvider();
    if (session != null && session.isExpired) {
      _onUnauthorized?.call();
      throw const ApiFailure(
        ApiFailureKind.unauthorized,
        'Your session expired. Sign in again.',
      );
    }
    try {
      final uri = Uri.parse(baseUrl).resolve(path);
      final response = method == 'POST'
          ? await _client
                .post(
                  uri,
                  headers: {..._headers, 'Content-Type': 'application/json'},
                  body: jsonEncode(body),
                )
                .timeout(const Duration(seconds: 12))
          : await _client
                .get(uri, headers: _headers)
                .timeout(const Duration(seconds: 12));
      if (response.statusCode == 401) {
        _onUnauthorized?.call();
        throw const ApiFailure(
          ApiFailureKind.unauthorized,
          'Your session expired. Sign in again.',
          statusCode: 401,
        );
      }
      if (response.statusCode == 403) {
        throw const ApiFailure(
          ApiFailureKind.forbidden,
          'Your account is not permitted to do that.',
          statusCode: 403,
        );
      }
      if (response.statusCode == 404) {
        throw const ApiFailure(
          ApiFailureKind.notFound,
          'The requested record was not found.',
          statusCode: 404,
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiFailure(
          ApiFailureKind.server,
          'The server returned ${response.statusCode}.',
          statusCode: response.statusCode,
        );
      }
      try {
        return jsonDecode(response.body);
      } on FormatException {
        throw const ApiFailure(
          ApiFailureKind.invalid,
          'The server returned invalid JSON.',
        );
      }
    } on ApiFailure {
      rethrow;
    } on http.ClientException {
      throw const ApiFailure(
        ApiFailureKind.network,
        'Cannot reach the server. Check connectivity and try again.',
      );
    } on FormatException {
      throw const ApiFailure(ApiFailureKind.invalid, 'The API URL is invalid.');
    } on Exception {
      throw const ApiFailure(
        ApiFailureKind.network,
        'The request did not complete. Check connectivity and try again.',
      );
    }
  }

  Future<List<HelmetSummary>> helmets() async {
    final json = await _getObject('/api/v1/helmets?limit=200');
    return _parse(
      () => _items(json).map((item) => HelmetSummary.fromJson(item)).toList(),
    );
  }

  Future<HelmetDetail> helmet(String id) async {
    final json = await _getObject('/api/v1/helmets/${Uri.encodeComponent(id)}');
    return _parse(() => HelmetDetail.fromJson(json));
  }

  Future<RiskEvaluation> risk(String id) async {
    final json = await _getObject(
      '/api/v1/helmets/${Uri.encodeComponent(id)}/risk',
    );
    return _parse(() => RiskEvaluation.fromJson(json));
  }

  Future<List<Incident>> incidents() async {
    final json = await _getObject('/api/v1/incidents?limit=200');
    return _parse(
      () => _items(json).map((item) => Incident.fromJson(item)).toList(),
    );
  }

  Future<Incident> incident(String id) async {
    final json = await _getObject(
      '/api/v1/incidents/${Uri.encodeComponent(id)}',
    );
    return _parse(() => Incident.fromJson(json));
  }

  Future<List<IncidentHistoryEntry>> incidentHistory(String id) async {
    final payload = await _request(
      '/api/v1/incidents/${Uri.encodeComponent(id)}/history',
    );
    if (payload is! List<dynamic>) {
      throw const ApiFailure(
        ApiFailureKind.invalid,
        'The incident history response was invalid.',
      );
    }
    return _parse(
      () => payload.map((item) {
        if (item is! Map<String, dynamic>) throw const FormatException();
        return IncidentHistoryEntry.fromJson(item);
      }).toList(),
    );
  }

  Future<Incident> acknowledge(String id, String acknowledgedBy) async {
    final json = await _getObject(
      '/api/v1/incidents/${Uri.encodeComponent(id)}/acknowledge',
      method: 'POST',
      body: {'acknowledged_by': acknowledgedBy},
    );
    return _parse(() => Incident.fromJson(json));
  }

  List<Map<String, dynamic>> _items(Map<String, dynamic> json) {
    final items = json['items'];
    if (items is! List<dynamic> ||
        items.any((item) => item is! Map<String, dynamic>)) {
      throw const ApiFailure(
        ApiFailureKind.invalid,
        'The server response did not match the expected contract.',
      );
    }
    for (final key in const ['limit', 'offset', 'total']) {
      if (json[key] is! num) {
        throw const ApiFailure(
          ApiFailureKind.invalid,
          'The server response did not match the expected contract.',
        );
      }
    }
    return items.cast<Map<String, dynamic>>();
  }

  T _parse<T>(T Function() decode) {
    try {
      return decode();
    } on ApiFailure {
      rethrow;
    } catch (_) {
      throw const ApiFailure(
        ApiFailureKind.invalid,
        'The server response did not match the expected contract.',
      );
    }
  }
}
