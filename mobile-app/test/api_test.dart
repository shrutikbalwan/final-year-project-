import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smart_safety_helmet_mobile/services/helmet_api.dart';
import 'package:smart_safety_helmet_mobile/services/session.dart';

void main() {
  test('loads helmets from the actual paginated API response shape', () async {
    final api = HelmetApi(
      baseUrl: 'http://localhost:8000',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/helmets');
        expect(request.url.queryParameters['limit'], '200');
        return http.Response(
          jsonEncode({
            'items': [_helmet()],
            'limit': 200,
            'offset': 0,
            'total': 1,
          }),
          200,
        );
      }),
    );

    final helmets = await api.helmets();
    expect(helmets.single.helmetId, 'helmet-test');
    expect(helmets.single.batteryReading.value, 74);
  });

  test('adds bearer session token and escapes device identifier', () async {
    late http.Request captured;
    final session = UserSession(
      userId: 'supervisor-1',
      role: UserRole.supervisor,
      expiresAt: DateTime.utc(2027),
      accessToken: 'session-token',
    );
    final api = HelmetApi(
      baseUrl: 'https://api.example.test',
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_helmetDetail()), 200);
      }),
      sessionProvider: () => session,
    );
    await api.helmet('helmet / test');
    expect(captured.headers['authorization'], 'Bearer session-token');
    expect(captured.url.path, '/api/v1/helmets/helmet%20%2F%20test');
  });

  test(
    'reports server and network failures without hiding them as empty data',
    () async {
      final serverError = HelmetApi(
        baseUrl: 'http://local',
        client: MockClient((_) async => http.Response('unavailable', 503)),
      );
      await expectLater(
        serverError.helmets(),
        throwsA(
          isA<ApiFailure>().having(
            (failure) => failure.kind,
            'failure kind',
            ApiFailureKind.server,
          ),
        ),
      );

      final networkError = HelmetApi(
        baseUrl: 'http://local',
        client: MockClient((_) async => throw http.ClientException('offline')),
      );
      await expectLater(
        networkError.helmets(),
        throwsA(
          isA<ApiFailure>().having(
            (failure) => failure.kind,
            'failure kind',
            ApiFailureKind.network,
          ),
        ),
      );
    },
  );

  test('invalidates a local session when the API returns 401', () async {
    var expired = false;
    final api = HelmetApi(
      baseUrl: 'https://api.example.test',
      client: MockClient((_) async => http.Response('{}', 401)),
      onUnauthorized: () => expired = true,
    );
    await expectLater(
      api.helmets(),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.kind,
          'failure kind',
          ApiFailureKind.unauthorized,
        ),
      ),
    );
    expect(expired, isTrue);
  });

  test('rejects invalid response shapes', () async {
    final api = HelmetApi(
      baseUrl: 'http://local',
      client: MockClient(
        (_) async => http.Response('{"items":[{"wrong":true}]}', 200),
      ),
    );
    await expectLater(
      api.helmets(),
      throwsA(
        isA<ApiFailure>().having(
          (failure) => failure.kind,
          'failure kind',
          ApiFailureKind.invalid,
        ),
      ),
    );
  });
}

Map<String, dynamic> _helmet() => {
  'helmet_id': 'helmet-test',
  'workplace_id': 'workplace-test',
  'last_telemetry_at': '2026-10-17T10:00:00Z',
  'connectivity_status': 'connected',
  'battery_reading': _reading(type: 'battery_charge', unit: '%', value: 74),
  'last_seen_at': '2026-10-17T10:00:00Z',
  'last_seen_status': 'valid',
};

Map<String, dynamic> _helmetDetail() => {
  ..._helmet(),
  'latest_telemetry': {
    'schema_version': '1.0.0',
    'event_id': 'event-test',
    'device_id': 'helmet-test',
    'workplace_id': 'workplace-test',
    'observed_at': '2026-10-17T10:00:00Z',
    'readings': [_reading(type: 'temperature', unit: 'Cel', value: 23)],
    'health': {
      'schema_version': '1.0.0',
      'device_id': 'helmet-test',
      'workplace_id': 'workplace-test',
      'observed_at': '2026-10-17T10:00:00Z',
      'battery_reading': _reading(type: 'battery_charge', unit: '%', value: 74),
      'connectivity_status': 'connected',
      'last_seen_at': '2026-10-17T10:00:00Z',
      'last_seen_status': 'valid',
    },
  },
};

Map<String, dynamic> _reading({
  required String type,
  required String unit,
  required num value,
}) => {
  'reading_id': 'reading-01',
  'sensor_id': 'sensor-01',
  'measurement_type': type,
  'unit_code': unit,
  'value': value,
  'reading_status': 'valid',
  'observed_at': '2026-10-17T10:00:00Z',
};
