import 'package:flutter/material.dart';

import '../models/incident.dart';
import '../services/helmet_api.dart';
import '../widgets/status_badge.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.api});
  final HelmetApi api;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
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
          return _UpdatesMessage(
            title: 'Updates unavailable',
            message: snapshot.error.toString(),
            refresh: _refresh,
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final active = snapshot.data!
            .where((incident) => incident.isActive)
            .toList();
        return ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              color: const Color(0xFFEAF2EF),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.notifications_active_outlined),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Push delivery is not configured. This screen checks saved incidents when you refresh; no notification permission is requested.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Current incident updates',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            if (active.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(18),
                  child: Text('No active incident updates.'),
                ),
              )
            else
              ...active.map(
                (incident) => Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: const Icon(Icons.notification_important_outlined),
                    title: Text(incident.reason),
                    subtitle: Text('${incident.deviceId} · ${incident.status}'),
                    trailing: StatusBadge(label: incident.severity),
                  ),
                ),
              ),
          ],
        );
      },
    ),
  );
}

class _UpdatesMessage extends StatelessWidget {
  const _UpdatesMessage({
    required this.title,
    required this.message,
    required this.refresh,
  });
  final String title;
  final String message;
  final Future<void> Function() refresh;
  @override
  Widget build(BuildContext context) => ListView(
    physics: const AlwaysScrollableScrollPhysics(),
    padding: const EdgeInsets.all(24),
    children: [
      const SizedBox(height: 80),
      Text(
        title,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      Text(message, textAlign: TextAlign.center),
      Center(
        child: OutlinedButton(onPressed: refresh, child: const Text('Refresh')),
      ),
    ],
  );
}
