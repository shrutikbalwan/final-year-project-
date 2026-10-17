import 'package:flutter/material.dart';

import '../models/helmet.dart';
import '../services/helmet_api.dart';
import '../widgets/status_badge.dart';
import 'fleet_screen.dart';

class HelmetDetailScreen extends StatefulWidget {
  const HelmetDetailScreen({
    super.key,
    required this.api,
    required this.helmetId,
  });
  final HelmetApi api;
  final String helmetId;

  @override
  State<HelmetDetailScreen> createState() => _HelmetDetailScreenState();
}

class _HelmetData {
  const _HelmetData(this.detail, this.risk, this.riskError);
  final HelmetDetail detail;
  final RiskEvaluation? risk;
  final String? riskError;
}

class _HelmetDetailScreenState extends State<HelmetDetailScreen> {
  late Future<_HelmetData> _request;

  @override
  void initState() {
    super.initState();
    _request = _load();
  }

  Future<_HelmetData> _load() async {
    final detail = await widget.api.helmet(widget.helmetId);
    try {
      return _HelmetData(detail, await widget.api.risk(widget.helmetId), null);
    } on ApiFailure catch (error) {
      return _HelmetData(detail, null, error.message);
    }
  }

  Future<void> _refresh() async {
    final request = _load();
    setState(() => _request = request);
    await request;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.helmetId)),
    body: FutureBuilder<_HelmetData>(
      future: _request,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_off, size: 44),
                  const SizedBox(height: 12),
                  const Text('Device details unavailable'),
                  Text(snapshot.error.toString(), textAlign: TextAlign.center),
                  OutlinedButton(
                    onPressed: _refresh,
                    child: const Text('Try again'),
                  ),
                ],
              ),
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final data = snapshot.data!;
        final helmet = data.detail;
        final health = helmet.latestTelemetry.health;
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              'Current risk',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                          StatusBadge(label: data.risk?.riskLevel ?? 'Unknown'),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        data.risk?.reasons.join('\n') ??
                            data.riskError ??
                            'The backend did not provide a risk evaluation.',
                      ),
                      if (data.risk != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Rule score ${data.risk!.score} · weighted rules, not machine learning',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Device health',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 8),
                      _ReadingLine(
                        label: 'Connectivity',
                        value: health.connectivityStatus,
                      ),
                      _ReadingLine(
                        label: 'Battery',
                        value: readingValue(health.batteryReading),
                      ),
                      _ReadingLine(
                        label: 'Battery status',
                        value: health.batteryReading.readingStatus,
                      ),
                      _ReadingLine(
                        label: 'Last seen',
                        value: health.lastSeenAt == null
                            ? 'Unknown'
                            : _format(health.lastSeenAt!),
                      ),
                      _ReadingLine(
                        label: 'Last-seen quality',
                        value: health.lastSeenStatus,
                      ),
                      _ReadingLine(
                        label: 'Telemetry time',
                        value: _format(helmet.latestTelemetry.observedAt),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Sensor readings',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              ...helmet.latestTelemetry.readings.map(
                (reading) => Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    title: Text(reading.measurementType.replaceAll('_', ' ')),
                    subtitle: Text(
                      '${reading.sensorId} · ${reading.readingStatus} · ${_format(reading.observedAt)}',
                    ),
                    trailing: Text(
                      reading.value == null
                          ? 'No value'
                          : '${reading.value} ${reading.unitCode}',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    ),
  );
}

class _ReadingLine extends StatelessWidget {
  const _ReadingLine({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      children: [
        Expanded(
          child: Text(label, style: Theme.of(context).textTheme.labelLarge),
        ),
        Flexible(child: Text(value, textAlign: TextAlign.end)),
      ],
    ),
  );
}

String _format(DateTime date) => date.toLocal().toString().split('.').first;
