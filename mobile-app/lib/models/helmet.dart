class SensorReading {
  const SensorReading({
    required this.readingId,
    required this.sensorId,
    required this.measurementType,
    required this.unitCode,
    required this.value,
    required this.readingStatus,
    required this.observedAt,
  });

  final String readingId;
  final String sensorId;
  final String measurementType;
  final String unitCode;
  final double? value;
  final String readingStatus;
  final DateTime observedAt;

  factory SensorReading.fromJson(Map<String, dynamic> json) => SensorReading(
    readingId: _string(json, 'reading_id'),
    sensorId: _string(json, 'sensor_id'),
    measurementType: _string(json, 'measurement_type'),
    unitCode: _string(json, 'unit_code'),
    value: json['value'] == null ? null : _number(json, 'value'),
    readingStatus: _oneOf(json, 'reading_status', const [
      'valid',
      'missing',
      'stale',
      'invalid',
    ]),
    observedAt: _date(json, 'observed_at'),
  ).._validateValue();

  void _validateValue() {
    if (readingStatus == 'missing' && value != null) {
      throw const FormatException('Missing readings must have a null value');
    }
    if (readingStatus != 'missing' && value == null) {
      throw const FormatException(
        'Only missing readings may have a null value',
      );
    }
  }
}

class DeviceHealth {
  const DeviceHealth({
    required this.schemaVersion,
    required this.deviceId,
    required this.workplaceId,
    required this.observedAt,
    required this.batteryReading,
    required this.connectivityStatus,
    required this.lastSeenAt,
    required this.lastSeenStatus,
  });

  final String schemaVersion;
  final String deviceId;
  final String workplaceId;
  final DateTime observedAt;
  final SensorReading batteryReading;
  final String connectivityStatus;
  final DateTime? lastSeenAt;
  final String lastSeenStatus;

  factory DeviceHealth.fromJson(Map<String, dynamic> json) => DeviceHealth(
    schemaVersion: _string(json, 'schema_version'),
    deviceId: _string(json, 'device_id'),
    workplaceId: _string(json, 'workplace_id'),
    observedAt: _date(json, 'observed_at'),
    batteryReading: SensorReading.fromJson(_map(json, 'battery_reading')),
    connectivityStatus: _oneOf(json, 'connectivity_status', const [
      'connected',
      'disconnected',
      'intermittent',
      'unknown',
    ]),
    lastSeenAt: json['last_seen_at'] == null
        ? null
        : _date(json, 'last_seen_at'),
    lastSeenStatus: _oneOf(json, 'last_seen_status', const [
      'valid',
      'missing',
      'stale',
    ]),
  ).._validate();

  void _validate() {
    if (schemaVersion != '1.0.0') {
      throw const FormatException('Unsupported device health schema version');
    }
    if (batteryReading.measurementType != 'battery_charge' ||
        batteryReading.unitCode != '%') {
      throw const FormatException(
        'Battery reading must use battery_charge and %',
      );
    }
    final value = batteryReading.value;
    if (value != null && (value < 0 || value > 100)) {
      throw const FormatException(
        'Battery percentage must be between 0 and 100',
      );
    }
    if ((lastSeenStatus == 'missing') != (lastSeenAt == null)) {
      throw const FormatException(
        'Last-seen timestamp does not match its status',
      );
    }
    if (lastSeenAt != null && lastSeenAt!.isAfter(observedAt)) {
      throw const FormatException(
        'Last-seen timestamp cannot be after the health snapshot',
      );
    }
  }
}

class DeviceTelemetry {
  const DeviceTelemetry({
    required this.schemaVersion,
    required this.eventId,
    required this.deviceId,
    required this.workplaceId,
    required this.observedAt,
    required this.readings,
    required this.health,
  });

  final String schemaVersion;
  final String eventId;
  final String deviceId;
  final String workplaceId;
  final DateTime observedAt;
  final List<SensorReading> readings;
  final DeviceHealth health;

  factory DeviceTelemetry.fromJson(Map<String, dynamic> json) =>
      DeviceTelemetry(
        schemaVersion: _string(json, 'schema_version'),
        eventId: _string(json, 'event_id'),
        deviceId: _string(json, 'device_id'),
        workplaceId: _string(json, 'workplace_id'),
        observedAt: _date(json, 'observed_at'),
        readings: _list(json, 'readings')
            .map((item) => SensorReading.fromJson(_asMap(item)))
            .toList(growable: false),
        health: DeviceHealth.fromJson(_map(json, 'health')),
      ).._validate();

  void _validate() {
    if (schemaVersion != '1.0.0' ||
        health.deviceId != deviceId ||
        health.workplaceId != workplaceId ||
        health.observedAt.isAfter(observedAt) ||
        readings.isEmpty ||
        readings.length > 256) {
      throw const FormatException(
        'Telemetry and embedded health identity or timestamps disagree',
      );
    }
  }
}

class HelmetSummary {
  const HelmetSummary({
    required this.helmetId,
    required this.workplaceId,
    required this.lastTelemetryAt,
    required this.connectivityStatus,
    required this.batteryReading,
    required this.lastSeenAt,
    required this.lastSeenStatus,
  });

  final String helmetId;
  final String workplaceId;
  final DateTime lastTelemetryAt;
  final String connectivityStatus;
  final SensorReading batteryReading;
  final DateTime? lastSeenAt;
  final String lastSeenStatus;

  factory HelmetSummary.fromJson(Map<String, dynamic> json) => HelmetSummary(
    helmetId: _string(json, 'helmet_id'),
    workplaceId: _string(json, 'workplace_id'),
    lastTelemetryAt: _date(json, 'last_telemetry_at'),
    connectivityStatus: _oneOf(json, 'connectivity_status', const [
      'connected',
      'disconnected',
      'intermittent',
      'unknown',
    ]),
    batteryReading: SensorReading.fromJson(_map(json, 'battery_reading')),
    lastSeenAt: json['last_seen_at'] == null
        ? null
        : _date(json, 'last_seen_at'),
    lastSeenStatus: _oneOf(json, 'last_seen_status', const [
      'valid',
      'missing',
      'stale',
    ]),
  ).._validate();

  void _validate() {
    if (batteryReading.measurementType != 'battery_charge' ||
        batteryReading.unitCode != '%') {
      throw const FormatException(
        'Battery reading must use battery_charge and %',
      );
    }
    final value = batteryReading.value;
    if (value != null && (value < 0 || value > 100)) {
      throw const FormatException(
        'Battery percentage must be between 0 and 100',
      );
    }
    if ((lastSeenStatus == 'missing') != (lastSeenAt == null)) {
      throw const FormatException(
        'Last-seen timestamp does not match its status',
      );
    }
  }
}

class HelmetDetail extends HelmetSummary {
  const HelmetDetail({
    required super.helmetId,
    required super.workplaceId,
    required super.lastTelemetryAt,
    required super.connectivityStatus,
    required super.batteryReading,
    required super.lastSeenAt,
    required super.lastSeenStatus,
    required this.latestTelemetry,
  });

  final DeviceTelemetry latestTelemetry;

  factory HelmetDetail.fromJson(Map<String, dynamic> json) {
    final summary = HelmetSummary.fromJson(json);
    final detail = HelmetDetail(
      helmetId: summary.helmetId,
      workplaceId: summary.workplaceId,
      lastTelemetryAt: summary.lastTelemetryAt,
      connectivityStatus: summary.connectivityStatus,
      batteryReading: summary.batteryReading,
      lastSeenAt: summary.lastSeenAt,
      lastSeenStatus: summary.lastSeenStatus,
      latestTelemetry: DeviceTelemetry.fromJson(_map(json, 'latest_telemetry')),
    );
    if (detail.latestTelemetry.deviceId != detail.helmetId ||
        detail.latestTelemetry.workplaceId != detail.workplaceId) {
      throw const FormatException(
        'Helmet summary and latest telemetry identities disagree',
      );
    }
    return detail;
  }
}

class RiskEvaluation {
  const RiskEvaluation({
    required this.riskLevel,
    required this.score,
    required this.reasons,
    required this.evaluatedAt,
  });

  final String riskLevel;
  final int score;
  final List<String> reasons;
  final DateTime evaluatedAt;

  factory RiskEvaluation.fromJson(Map<String, dynamic> json) => RiskEvaluation(
    riskLevel: _oneOf(json, 'risk_level', const [
      'Normal',
      'Advisory',
      'Warning',
      'Critical',
      'Unknown',
    ]),
    score: _number(json, 'score').toInt(),
    reasons: _list(json, 'reasons').map((value) => value as String).toList(),
    evaluatedAt: _date(json, 'evaluated_at'),
  );
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) throw FormatException('Expected string field: $key');
  return value;
}

double _number(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! num || !value.isFinite) {
    throw FormatException('Expected finite number field: $key');
  }
  return value.toDouble();
}

DateTime _date(Map<String, dynamic> json, String key) =>
    _parseUtc(_string(json, key), key);

DateTime _parseUtc(String value, String key) {
  if (!RegExp(r'(?:Z|\+00:00)$').hasMatch(value)) {
    throw FormatException('Expected a UTC timestamp field: $key');
  }
  return DateTime.parse(value).toUtc();
}

String _oneOf(Map<String, dynamic> json, String key, List<String> allowed) {
  final value = _string(json, key);
  if (!allowed.contains(value)) {
    throw FormatException('Unsupported value for $key');
  }
  return value;
}

Map<String, dynamic> _map(Map<String, dynamic> json, String key) =>
    _asMap(json[key]);

Map<String, dynamic> _asMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  throw const FormatException('Expected a JSON object');
}

List<dynamic> _list(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is List<dynamic>) return value;
  throw FormatException('Expected list field: $key');
}
