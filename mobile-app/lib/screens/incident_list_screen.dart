import 'package:flutter/material.dart';

import '../models/incident.dart';
import '../services/helmet_api.dart';
import '../services/session.dart';
import '../widgets/status_badge.dart';
import 'incident_detail_screen.dart';

class IncidentListScreen extends StatefulWidget {
  const IncidentListScreen({
    super.key,
    required this.api,
    required this.session,
    required this.activeOnly,
  });
  final HelmetApi api;
  final UserSession session;
  final bool activeOnly;

  @override
  State<IncidentListScreen> createState() => _IncidentListScreenState();
}

class _IncidentListScreenState extends State<IncidentListScreen> {
  late Future<List<Incident>> _request;
  @override
  void initState() {
    super.initState();
    _request = widget.api.incidents();
  }

  Future<void> _refresh() async {
    final request = widget.api.incidents();
    setState(() => _request = request);
    await request;
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _refresh,
    child: FutureBuilder<List<Incident>>(
      future: _request,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return _IncidentMessage(
            icon: Icons.cloud_off_outlined,
            title: 'Incident data unavailable',
            message: snapshot.error.toString(),
            refresh: _refresh,
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final incidents = snapshot.data!
            .where(
              (incident) =>
                  widget.activeOnly ? incident.isActive : !incident.isActive,
            )
            .toList();
        if (incidents.isEmpty) {
          return _IncidentMessage(
            icon: widget.activeOnly
                ? Icons.check_circle_outline
                : Icons.history,
            title: widget.activeOnly
                ? 'No active incidents'
                : 'No incident history yet',
            message: widget.activeOnly
                ? 'New incidents will appear here when the backend records them.'
                : 'Resolved or closed incidents will appear here.',
            refresh: _refresh,
          );
        }
        return ListView.separated(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          itemCount: incidents.length,
          separatorBuilder: (_, _) => const SizedBox(height: 10),
          itemBuilder: (context, index) {
            final incident = incidents[index];
            return Card(
              child: ListTile(
                contentPadding: const EdgeInsets.all(14),
                leading: CircleAvatar(
                  backgroundColor: statusColor(
                    incident.severity,
                  ).withValues(alpha: 0.12),
                  child: Icon(
                    Icons.warning_amber,
                    color: statusColor(incident.severity),
                  ),
                ),
                title: Text(
                  incident.reason,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(incident.deviceId),
                      StatusBadge(label: incident.severity),
                      StatusBadge(label: incident.status),
                      Text(_dateTime(incident.updatedAt)),
                    ],
                  ),
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => IncidentDetailScreen(
                      api: widget.api,
                      session: widget.session,
                      incidentId: incident.incidentId,
                    ),
                  ),
                ),
              ),
            );
          },
        );
      },
    ),
  );
}

class _IncidentMessage extends StatelessWidget {
  const _IncidentMessage({
    required this.icon,
    required this.title,
    required this.message,
    required this.refresh,
  });
  final IconData icon;
  final String title;
  final String message;
  final Future<void> Function() refresh;
  @override
  Widget build(BuildContext context) => ListView(
    physics: const AlwaysScrollableScrollPhysics(),
    padding: const EdgeInsets.all(28),
    children: [
      const SizedBox(height: 70),
      Icon(icon, size: 48, color: Colors.blueGrey),
      const SizedBox(height: 12),
      Text(
        title,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      Text(message, textAlign: TextAlign.center),
      const SizedBox(height: 14),
      Center(
        child: OutlinedButton.icon(
          onPressed: refresh,
          icon: const Icon(Icons.refresh),
          label: const Text('Refresh'),
        ),
      ),
    ],
  );
}

String _dateTime(DateTime date) => date.toLocal().toString().split('.').first;
