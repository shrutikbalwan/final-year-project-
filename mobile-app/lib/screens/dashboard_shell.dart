import 'package:flutter/material.dart';

import '../services/helmet_api.dart';
import '../services/session.dart';
import 'fleet_screen.dart';
import 'incident_list_screen.dart';
import 'notifications_screen.dart';

class DashboardShell extends StatefulWidget {
  const DashboardShell({
    super.key,
    required this.api,
    required this.session,
    required this.onSignOut,
  });
  final HelmetApi api;
  final UserSession session;
  final VoidCallback onSignOut;

  @override
  State<DashboardShell> createState() => _DashboardShellState();
}

class _DashboardShellState extends State<DashboardShell> {
  int _index = 0;
  late final _pages = [
    FleetScreen(api: widget.api),
    IncidentListScreen(
      api: widget.api,
      session: widget.session,
      activeOnly: true,
    ),
    IncidentListScreen(
      api: widget.api,
      session: widget.session,
      activeOnly: false,
    ),
    NotificationsScreen(api: widget.api),
  ];
  static const _titles = [
    'Helmet status',
    'Active incidents',
    'Incident history',
    'Updates',
  ];

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(_titles[_index]),
      actions: [
        TextButton.icon(
          onPressed: widget.onSignOut,
          icon: const Icon(Icons.logout),
          label: const Text('Sign out'),
        ),
      ],
    ),
    body: Column(
      children: [
        if (widget.session.development) const _DevelopmentBanner(),
        Expanded(
          child: IndexedStack(index: _index, children: _pages),
        ),
      ],
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _index,
      onDestinationSelected: (index) => setState(() => _index = index),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.sensors_outlined),
          selectedIcon: Icon(Icons.sensors),
          label: 'Helmets',
        ),
        NavigationDestination(
          icon: Icon(Icons.warning_amber_outlined),
          selectedIcon: Icon(Icons.warning_amber),
          label: 'Active',
        ),
        NavigationDestination(icon: Icon(Icons.history), label: 'History'),
        NavigationDestination(
          icon: Icon(Icons.notifications_none),
          selectedIcon: Icon(Icons.notifications),
          label: 'Updates',
        ),
      ],
    ),
  );
}

class _DevelopmentBanner extends StatelessWidget {
  const _DevelopmentBanner();
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: const Color(0xFFFFF1D6),
    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
    child: Text(
      'READ-ONLY DEVELOPMENT ACCESS · user assignments and server authorization are not configured',
      style: Theme.of(
        context,
      ).textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w700),
      textAlign: TextAlign.center,
    ),
  );
}
