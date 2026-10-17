import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../services/auth_service.dart';
import '../services/session.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.onAuthenticated,
    required this.auth,
    this.errorMessage,
  });
  final ValueChanged<UserSession> onAuthenticated;
  final AuthService auth;
  final String? errorMessage;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _working = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    setState(() {
      _working = true;
      _error = null;
    });
    try {
      final session = await widget.auth.signIn(
        _username.text.trim(),
        _password.text,
      );
      _password.clear();
      widget.onAuthenticated(session);
    } on AuthenticationException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(
                    Icons.health_and_safety,
                    size: 54,
                    color: Color(0xFF176B5B),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Smart Safety Helmet',
                    style: Theme.of(context).textTheme.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Supervisor and assigned-device monitoring',
                    style: Theme.of(context).textTheme.bodyLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 28),
                  if (widget.errorMessage != null || _error != null)
                    _MessageCard(
                      message: _error ?? widget.errorMessage!,
                      error: true,
                    ),
                  ...[
                    TextField(
                      controller: _username,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(
                        labelText: 'Username',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _password,
                      obscureText: true,
                      autofillHints: const [AutofillHints.password],
                      onSubmitted: (_) {
                        if (!_working) _signIn();
                      },
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: _working ? null : _signIn,
                      child: _working
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Sign in'),
                    ),
                    const SizedBox(height: 12),
                    const _MessageCard(
                      message:
                          'Credentials are sent to the configured API login endpoint. The signed token is stored in secure device storage.',
                    ),
                  ],
                  const SizedBox(height: 16),
                  Text(
                    'API: ${AppConfig.apiBaseUrl}',
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Keeps the login widget independent of an HTTP client singleton while
/// ensuring its client is closed immediately after the provider request.
class _MessageCard extends StatelessWidget {
  const _MessageCard({required this.message, this.error = false});
  final String message;
  final bool error;
  @override
  Widget build(BuildContext context) => Card(
    color: error
        ? Theme.of(context).colorScheme.errorContainer
        : const Color(0xFFEAF2EF),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
    ),
  );
}
