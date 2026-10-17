class AppConfig {
  const AppConfig._();

  /// Android emulator default. Use --dart-define=API_BASE_URL=... for other targets.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Override only when using a compatible identity provider or API base URL.
  static const authTokenUrl = String.fromEnvironment(
    'AUTH_TOKEN_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1/auth/login',
  );

  /// Keep acknowledgement UI gated to an API that enforces token role claims.
  static const serverEnforcesAuthorization = bool.fromEnvironment(
    'SERVER_ENFORCES_AUTHORIZATION',
    defaultValue: false,
  );
}
