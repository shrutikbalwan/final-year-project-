import 'package:flutter_test/flutter_test.dart';
import 'package:smart_safety_helmet_mobile/models/helmet.dart';
import 'package:smart_safety_helmet_mobile/models/incident.dart';

void main() {
  group('shared sensor reading contract', () {
    test('retains explicit missing values as null', () {
      final reading = SensorReading.fromJson(
        _reading(value: null, status: 'missing'),
      );
      expect(reading.value, isNull);
      expect(reading.readingStatus, 'missing');
    });

    test('rejects a missing reading silently represented as zero', () {
      expect(
        () => SensorReading.fromJson(_reading(value: 0, status: 'missing')),
        throwsFormatException,
      );
    });

    test('rejects timestamps outside UTC', () {
      final json = _reading(value: 20, status: 'valid')
        ..['observed_at'] = '2026-10-17T10:00:00+05:30';
      expect(() => SensorReading.fromJson(json), throwsFormatException);
    });

    test('rejects unknown reading status', () {
      expect(
        () => SensorReading.fromJson(_reading(value: 20, status: 'unknown')),
        throwsFormatException,
      );
    });
  });

  test('incident model recognizes active and history states', () {
    final open = Incident.fromJson(_incident(status: 'open'));
    final resolved = Incident.fromJson(_incident(status: 'resolved'));
    expect(open.isActive, isTrue);
    expect(resolved.isActive, isFalse);
    expect(open.history.single.action, 'created');
  });
}

Map<String, dynamic> _reading({
  required Object? value,
  required String status,
}) => {
  'reading_id': 'reading-01',
  'sensor_id': 'sensor-01',
  'measurement_type': 'temperature',
  'unit_code': 'Cel',
  'value': value,
  'reading_status': status,
  'observed_at': '2026-10-17T10:00:00Z',
};

Map<String, dynamic> _incident({String status = 'open'}) => {
  'schema_version': '1.0.0',
  'incident_id': 'incident-01',
  'device_id': 'helmet-test',
  'workplace_id': 'workplace-test',
  'status': status,
  'severity': 'Warning',
  'risk_score': 4,
  'opened_at': '2026-10-17T10:00:00Z',
  'updated_at': '2026-10-17T10:01:00Z',
  'reason': 'Synthetic test alert',
  'source': {
    'telemetry_event_id': 'event-01',
    'rule_ids': [],
    'reading_ids': [],
  },
  'event_ids': ['event-01'],
  'occurrence_count': 1,
  'history': [
    {
      'entry_id': 'history-01',
      'action': 'created',
      'timestamp': '2026-10-17T10:00:00Z',
    },
  ],
};
