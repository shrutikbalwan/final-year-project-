import 'package:flutter/material.dart';

import '../models/helmet.dart';
import '../services/helmet_api.dart';
import '../widgets/status_badge.dart';
import 'helmet_detail_screen.dart';

class FleetScreen extends StatefulWidget {
  const FleetScreen({super.key, required this.api});
  final HelmetApi api;

  @override
  State<FleetScreen> createState() => _FleetScreenState();
}

class _FleetScreenState extends State<FleetScreen> {
  late Future<List<HelmetSummary>> _helmets;

  @override
  void initState() {
    super.initState();
    _helmets = widget.api.helmets();
  }

  Future<void> _refresh() async {
    final request = widget.api.helmets();
    setState(() => _helmets = request);
    await request;
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _refresh,
    child: FutureBuilder<List<HelmetSummary>>(
      future: _helmets,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return _ScrollableMessage(
            icon: Icons.cloud_off_outlined,
            title: 'Could not load helmet data',
            message: snapshot.error.toString(),
            action: _refresh,
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final helmets = snapshot.data!;
        if (helmets.isEmpty) {
          return _ScrollableMessage(
            icon: Icons.sensors_off_outlined,
            title: 'No helmets registered',
            message:
                'Registered devices will appear here after the backend receives telemetry.',
            action: _refresh,
          );
        }
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              '${helmets.length} device${helmets.length == 1 ? '' : 's'} reporting',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            ...helmets.map(
              (helmet) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _HelmetCard(
                  helmet: helmet,
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => HelmetDetailScreen(
                        api: widget.api,
                        helmetId: helmet.helmetId,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _HelmetCard extends StatelessWidget {
  const _HelmetCard({required this.helmet, required this.onTap});
  final HelmetSummary helmet;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const CircleAvatar(child: Icon(Icons.engineering_outlined)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        helmet.helmetId,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        helmet.workplaceId,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                StatusBadge(label: helmet.connectivityStatus),
              ],
            ),
            const Divider(height: 24),
            Row(
              children: [
                Expanded(
                  child: _CompactMetric(
                    label: 'Battery',
                    value: readingValue(helmet.batteryReading),
                    icon: Icons.battery_5_bar,
                  ),
                ),
                Expanded(
                  child: _CompactMetric(
                    label: 'Last seen',
                    value: helmet.lastSeenAt == null
                        ? 'Unknown'
                        : '${relativeTime(helmet.lastSeenAt!)} · ${helmet.lastSeenStatus}',
                    icon: Icons.schedule,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

class _CompactMetric extends StatelessWidget {
  const _CompactMetric({
    required this.label,
    required this.value,
    required this.icon,
  });
  final String label;
  final String value;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, size: 18, color: const Color(0xFF176B5B)),
      const SizedBox(width: 7),
      Flexible(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.labelSmall),
            Text(
              value,
              style: Theme.of(context).textTheme.bodyMedium,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    ],
  );
}

class _ScrollableMessage extends StatelessWidget {
  const _ScrollableMessage({
    required this.icon,
    required this.title,
    required this.message,
    required this.action,
  });
  final IconData icon;
  final String title;
  final String message;
  final Future<void> Function() action;
  @override
  Widget build(BuildContext context) => ListView(
    physics: const AlwaysScrollableScrollPhysics(),
    padding: const EdgeInsets.all(30),
    children: [
      const SizedBox(height: 80),
      Icon(icon, size: 52, color: Colors.blueGrey),
      const SizedBox(height: 16),
      Text(
        title,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      Text(message, textAlign: TextAlign.center),
      const SizedBox(height: 16),
      Center(
        child: OutlinedButton.icon(
          onPressed: action,
          icon: const Icon(Icons.refresh),
          label: const Text('Refresh'),
        ),
      ),
    ],
  );
}

String readingValue(SensorReading reading) {
  if (reading.value == null) return '${reading.readingStatus} · no value';
  final value =
      '${reading.value!.toStringAsFixed(reading.value! % 1 == 0 ? 0 : 1)} ${reading.unitCode}';
  return reading.readingStatus == 'valid'
      ? value
      : '$value · ${reading.readingStatus}';
}

String relativeTime(DateTime date) {
  final delta = DateTime.now().toUtc().difference(date.toUtc());
  if (delta.isNegative || delta.inSeconds < 60) return 'just now';
  if (delta.inMinutes < 60) return '${delta.inMinutes} min ago';
  if (delta.inHours < 24) return '${delta.inHours} hr ago';
  return '${delta.inDays} d ago';
}
