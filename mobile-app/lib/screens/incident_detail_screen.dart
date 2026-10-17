import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/incident.dart';
import '../services/access_policy.dart';
import '../services/helmet_api.dart';
import '../services/session.dart';
import '../widgets/status_badge.dart';

class IncidentDetailScreen extends StatefulWidget {
  const IncidentDetailScreen({
    super.key,
    required this.api,
    required this.session,
    required this.incidentId,
  });
  final HelmetApi api;
  final UserSession session;
  final String incidentId;

  @override
  State<IncidentDetailScreen> createState() => _IncidentDetailScreenState();
}

class _IncidentDetailScreenState extends State<IncidentDetailScreen> {
  late Future<Incident> _request;
  bool _acknowledging = false;
  String? _actionError;

  bool get _mayAcknowledge => canAcknowledgeIncident(
    session: widget.session,
    serverEnforcesAuthorization: AppConfig.serverEnforcesAuthorization,
  );

  @override
  void initState() {
    super.initState();
    _request = widget.api.incident(widget.incidentId);
  }

  Future<void> _refresh() async {
    final request = widget.api.incident(widget.incidentId);
    setState(() {
      _request = request;
      _actionError = null;
    });
    await request;
  }

  Future<void> _acknowledge() async {
    setState(() {
      _acknowledging = true;
      _actionError = null;
    });
    try {
      final updated = await widget.api.acknowledge(
        widget.incidentId,
        widget.session.userId,
      );
      if (mounted) setState(() => _request = Future.value(updated));
    } on ApiFailure catch (error) {
      if (mounted) setState(() => _actionError = error.message);
    } finally {
      if (mounted) setState(() => _acknowledging = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Incident details')),
    body: FutureBuilder<Incident>(
      future: _request,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return _FailureState(
            message: snapshot.error.toString(),
            retry: _refresh,
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final incident = snapshot.data!;
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
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          StatusBadge(label: incident.severity),
                          StatusBadge(label: incident.status),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Text(
                        incident.reason,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 16),
                      _DetailRow(label: 'Helmet', value: incident.deviceId),
                      _DetailRow(
                        label: 'Workplace',
                        value: incident.workplaceId,
                      ),
                      _DetailRow(
                        label: 'Incident ID',
                        value: incident.incidentId,
                      ),
                      _DetailRow(
                        label: 'Opened',
                        value: _format(incident.openedAt),
                      ),
                      _DetailRow(
                        label: 'Last updated',
                        value: _format(incident.updatedAt),
                      ),
                      _DetailRow(
                        label: 'Occurrences',
                        value: '${incident.occurrenceCount}',
                      ),
                      _DetailRow(
                        label: 'Rule score',
                        value: '${incident.riskScore}',
                      ),
                      _DetailRow(
                        label: 'Telemetry event',
                        value: incident.source.telemetryEventId,
                      ),
                      if (incident.source.ruleIds.isNotEmpty)
                        _DetailRow(
                          label: 'Matched rules',
                          value: incident.source.ruleIds.join(', '),
                        ),
                      if (incident.eventIds.isNotEmpty)
                        _DetailRow(
                          label: 'Related events',
                          value: incident.eventIds.join(', '),
                        ),
                      if (incident.acknowledgedBy != null)
                        _DetailRow(
                          label: 'Acknowledged by',
                          value: incident.acknowledgedBy!,
                        ),
                    ],
                  ),
                ),
              ),
              if (incident.status == 'open') ...[
                const SizedBox(height: 12),
                if (_mayAcknowledge)
                  FilledButton.icon(
                    onPressed: _acknowledging ? null : _acknowledge,
                    icon: const Icon(Icons.task_alt),
                    label: Text(
                      _acknowledging
                          ? 'Acknowledging…'
                          : 'Acknowledge incident',
                    ),
                  )
                else
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(14),
                      child: Text(
                        'Acknowledgement is disabled. A verified supervisor session and server-side role enforcement are required.',
                      ),
                    ),
                  ),
              ],
              if (_actionError != null) ...[
                const SizedBox(height: 8),
                Card(
                  color: Theme.of(context).colorScheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Text(_actionError!),
                  ),
                ),
              ],
              const SizedBox(height: 18),
              Text(
                'Incident history',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 10),
              if (incident.history.isEmpty)
                const Text('No history entries were recorded.')
              else
                ...incident.history.map(
                  (entry) => Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: const Icon(Icons.history),
                      title: Text(entry.action.replaceAll('_', ' ')),
                      subtitle: Text(
                        [
                          _format(entry.timestamp),
                          if (entry.actor != null) 'by ${entry.actor}',
                          if (entry.note != null) entry.note!,
                        ].join(' · '),
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

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 116,
          child: Text(label, style: Theme.of(context).textTheme.labelLarge),
        ),
        Expanded(child: Text(value)),
      ],
    ),
  );
}

class _FailureState extends StatelessWidget {
  const _FailureState({required this.message, required this.retry});
  final String message;
  final Future<void> Function() retry;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off, size: 44),
          const SizedBox(height: 12),
          const Text('Incident details unavailable'),
          const SizedBox(height: 8),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: retry, child: const Text('Try again')),
        ],
      ),
    ),
  );
}

String _format(DateTime date) => date.toLocal().toString().split('.').first;
