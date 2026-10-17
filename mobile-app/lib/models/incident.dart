class Incident {
  const Incident({
    required this.schemaVersion,
    required this.incidentId,
    required this.deviceId,
    required this.workplaceId,
    required this.status,
    required this.severity,
    required this.riskScore,
    required this.openedAt,
    required this.updatedAt,
    required this.reason,
    required this.eventIds,
    required this.occurrenceCount,
    required this.history,
    required this.source,
    this.acknowledgedAt,
    this.acknowledgedBy,
  });

  final String schemaVersion;
  final String incidentId;
  final String deviceId;
  final String workplaceId;
  final String status;
  final String severity;
  final int riskScore;
  final DateTime openedAt;
  final DateTime updatedAt;
  final String reason;
  final List<String> eventIds;
  final int occurrenceCount;
  final DateTime? acknowledgedAt;
  final String? acknowledgedBy;
  final List<IncidentHistoryEntry> history;
  final IncidentSource source;

  bool get isActive => status == 'open' || status == 'acknowledged';

  factory Incident.fromJson(Map<String, dynamic> json) => Incident(
    schemaVersion: _string(json, 'schema_version'),
    incidentId: _string(json, 'incident_id'),
    deviceId: _string(json, 'device_id'),
    workplaceId: _string(json, 'workplace_id'),
    status: _oneOf(json, 'status', const [
      'open',
      'acknowledged',
      'resolved',
      'closed',
    ]),
    severity: _oneOf(json, 'severity', const [
      'Normal',
      'Advisory',
      'Warning',
      'Critical',
      'Unknown',
    ]),
    riskScore: _int(json, 'risk_score'),
    openedAt: _date(json, 'opened_at'),
    updatedAt: _date(json, 'updated_at'),
    reason: _string(json, 'reason'),
    eventIds: _strings(json, 'event_ids'),
    occurrenceCount: (json['occurrence_count'] as num?)?.toInt() ?? 1,
    acknowledgedAt: json['acknowledged_at'] == null
        ? null
        : _date(json, 'acknowledged_at'),
    acknowledgedBy: json['acknowledged_by'] as String?,
    history: (json['history'] as List<dynamic>? ?? const [])
        .map(
          (entry) =>
              IncidentHistoryEntry.fromJson(entry as Map<String, dynamic>),
        )
        .toList(growable: false),
    source: IncidentSource.fromJson(json['source'] as Map<String, dynamic>),
  ).._validate();

  void _validate() {
    if (schemaVersion != '1.0.0' ||
        riskScore < 0 ||
        occurrenceCount < 1 ||
        updatedAt.isBefore(openedAt)) {
      throw const FormatException(
        'Incident values are outside the shared contract',
      );
    }
    if (status == 'acknowledged' &&
        (acknowledgedAt == null || acknowledgedBy == null)) {
      throw const FormatException(
        'Acknowledged incidents require acknowledgement details',
      );
    }
    if (status == 'open' &&
        (acknowledgedAt != null || acknowledgedBy != null)) {
      throw const FormatException(
        'Open incidents cannot include acknowledgement details',
      );
    }
    if (history.isEmpty ||
        history
            .map((entry) => entry.timestamp)
            .toList()
            .any(
              (timestamp) =>
                  timestamp.isBefore(openedAt) || timestamp.isAfter(updatedAt),
            )) {
      throw const FormatException(
        'Incident history timestamps are out of range',
      );
    }
    final timestamps = history.map((entry) => entry.timestamp).toList();
    for (var index = 1; index < timestamps.length; index++) {
      if (timestamps[index].isBefore(timestamps[index - 1])) {
        throw const FormatException(
          'Incident history must be ordered by timestamp',
        );
      }
    }
  }
}

class IncidentSource {
  const IncidentSource({
    required this.telemetryEventId,
    required this.ruleIds,
    required this.readingIds,
  });
  final String telemetryEventId;
  final List<String> ruleIds;
  final List<String> readingIds;

  factory IncidentSource.fromJson(Map<String, dynamic> json) => IncidentSource(
    telemetryEventId: _string(json, 'telemetry_event_id'),
    ruleIds: _strings(json, 'rule_ids'),
    readingIds: _strings(json, 'reading_ids'),
  );
}

class IncidentHistoryEntry {
  const IncidentHistoryEntry({
    required this.action,
    required this.timestamp,
    this.actor,
    this.note,
  });

  final String action;
  final DateTime timestamp;
  final String? actor;
  final String? note;

  factory IncidentHistoryEntry.fromJson(Map<String, dynamic> json) =>
      IncidentHistoryEntry(
        action: _oneOf(json, 'action', const [
          'created',
          'repeated',
          'acknowledged',
          'escalated',
          'resolved',
          'closed',
        ]),
        timestamp: _date(json, 'timestamp'),
        actor: json['actor'] as String?,
        note: json['note'] as String?,
      );
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String) throw FormatException('Expected string field: $key');
  return value;
}

int _int(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! num) throw FormatException('Expected numeric field: $key');
  return value.toInt();
}

DateTime _date(Map<String, dynamic> json, String key) {
  final value = _string(json, key);
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

List<String> _strings(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! List<dynamic> || value.any((item) => item is! String)) {
    throw FormatException('Expected string list field: $key');
  }
  return value.cast<String>();
}
