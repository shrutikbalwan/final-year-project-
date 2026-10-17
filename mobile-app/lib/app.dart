import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'config/app_config.dart';
import 'screens/dashboard_shell.dart';
import 'screens/login_screen.dart';
import 'services/auth_service.dart';
import 'services/helmet_api.dart';
import 'services/session.dart';

class SmartSafetyHelmetApp extends StatefulWidget {
  const SmartSafetyHelmetApp({super.key});

  @override
  State<SmartSafetyHelmetApp> createState() => _SmartSafetyHelmetAppState();
}

class _SmartSafetyHelmetAppState extends State<SmartSafetyHelmetApp> {
  final _httpClient = http.Client();
  late final SessionRepository _sessions;
  late final AuthService _auth;
  late final HelmetApi _api;
  UserSession? _session;
  bool _loading = true;
  String? _restoreError;

  @override
  void initState() {
    super.initState();
    _sessions = SessionRepository(SecureSessionVault());
    _auth = AuthService(sessions: _sessions, client: _httpClient);
    _api = HelmetApi(
      baseUrl: AppConfig.apiBaseUrl,
      client: _httpClient,
      sessionProvider: () => _session,
      onUnauthorized: _expireSession,
    );
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    try {
      final restored = await _sessions.restore();
      if (mounted) {
        setState(() {
          _session = restored;
          _loading = false;
        });
      }
    } on Exception {
      if (mounted) {
        setState(() {
          _restoreError =
              'Secure session storage is unavailable on this device.';
          _loading = false;
        });
      }
    }
  }

  Future<void> _signIn(UserSession session) async {
    if (mounted) {
      setState(() {
        _session = session;
        _restoreError = null;
      });
    }
  }

  Future<void> _signOut() async {
    try {
      await _auth.signOut();
    } finally {
      if (mounted) setState(() => _session = null);
    }
  }

  void _expireSession() {
    if (mounted) setState(() => _session = null);
    _sessions.clear().catchError((_) {});
  }

  @override
  void dispose() {
    _httpClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Smart Safety Helmet',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF176B5B)),
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xFFF4F7F6),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: Colors.white,
      ),
    ),
    home: _loading
        ? const _StartupScreen()
        : _session == null
        ? LoginScreen(
            errorMessage: _restoreError,
            auth: _auth,
            onAuthenticated: _signIn,
          )
        : DashboardShell(api: _api, session: _session!, onSignOut: _signOut),
  );
}

class _StartupScreen extends StatelessWidget {
  const _StartupScreen();
  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
