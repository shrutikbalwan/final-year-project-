# Smart Safety Helmet mobile app

Flutter client for the existing version 1 FastAPI endpoints and shared contract.
The app does not seed dashboard data: helmet, risk and incident details come
from the API.

## Authentication and access

The local FastAPI server provides username/password login backed by Argon2
password hashes and signed, expiring bearer tokens. Configure bootstrap users
as documented in [authentication and authorization](../docs/authentication-and-authorization.md)
before starting the API. There is no development bypass. The mobile app sends
credentials only to `AUTH_TOKEN_URL` (by default the local API login endpoint),
stores the returned token with platform secure storage, and attaches it to API
requests. It clears an expired/invalid session after HTTP 401.

The API enforces roles: viewers can read; supervisors can read and acknowledge;
administrators can also ingest data and change workplace profiles. The
acknowledgement control requires a verified supervisor/admin session and the
`SERVER_ENFORCES_AUTHORIZATION=true` client setting; the backend remains the
actual enforcement point. Push notifications are not configured.

Do not distribute this preview as an authenticated safety product. Use HTTPS
for a deployed API and identity provider. Local HTTP is enabled only in the
Android debug manifest.

## Prerequisites

- Flutter stable (Dart 3.10 or newer), Git for Windows, and VS Code with the
  Flutter and Dart extensions.
- Android SDK command-line tools, platform tools, and an Android emulator, or
  a USB-connected Android device with developer options enabled. Android
  Studio is optional.
- Java 17 or newer for Android Gradle builds.
- The Smart Safety Helmet API running on the development computer.

On this development machine, Flutter 3.47.7 is installed at
`D:\tools\flutter`; the Android SDK is at `D:\tools\android-sdk`, and the
emulator profiles are at `D:\tools\android-avd`. Flutter and the Android SDK
tools have been added to the Windows user `PATH`, with `ANDROID_HOME`,
`ANDROID_SDK_ROOT` and `ANDROID_AVD_HOME` configured. Open a new PowerShell
terminal or restart VS Code to read those settings:

```powershell
$env:Path = "D:\tools\flutter\bin;$env:Path"
flutter --version
flutter doctor -v
flutter devices
```

The local test profile is `HelmetSmoke` (Android 16 / API 36, x86_64). Start it
from PowerShell with:

```powershell
emulator -avd HelmetSmoke -no-snapshot -no-audio
```

On another machine, install Flutter stable and add its `bin` directory to
`PATH` using the [official Windows setup instructions](https://docs.flutter.dev/install/manual).

## Configure and run on Windows PowerShell

From the repository root, start the local API on all interfaces so an emulator
can reach it:

```powershell
.\.venv\Scripts\Activate.ps1
$env:HELMET_DB_PATH = ".\data\smart_safety_helmet.sqlite3"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal:

```powershell
Set-Location .\mobile-app
Copy-Item .\config\development.example.json .\config\development.json
flutter pub get
flutter devices
flutter run --dart-define-from-file=config/development.json `
  --dart-define=SERVER_ENFORCES_AUTHORIZATION=true
```

The example uses Android Emulator's host alias `10.0.2.2` and signs in to the
local API. For a physical phone, configure a trusted HTTPS endpoint with a
matching `AUTH_TOKEN_URL`; the app rejects HTTP credentials to non-local hosts.
Never expose the development HTTP API to the public internet.

For a compatible external identity provider, set `AUTH_TOKEN_URL` to its HTTPS
token endpoint. The provider must return `access_token`, `user_id`, `role`
(`viewer`, `supervisor`, or `administrator`) and UTC `expires_at`. The API must
also validate that provider's tokens before enabling acknowledgements:

```powershell
flutter run --dart-define-from-file=config/development.json `
  --dart-define=AUTH_TOKEN_URL=http://10.0.2.2:8000/api/v1/auth/login `
  --dart-define=SERVER_ENFORCES_AUTHORIZATION=true
```

Do not put passwords, client secrets, private keys, or AWS credentials in the
define file. Its local copy is ignored by Git.

## Checks and Android debug build

```powershell
Set-Location .\mobile-app
flutter pub get
flutter analyze
flutter test
flutter build apk --debug --dart-define-from-file=config/development.json
```

The debug APK is written to
`build\app\outputs\flutter-apk\app-debug.apk`.

The Windows 11 setup and Android emulator smoke test were verified on
2026-10-17. The analyzer reported no issues, all 19 Flutter tests passed, and a
debug APK was installed and launched in the emulator. The app read a clearly
synthetic helmet from the local API; the verification details are in
[`docs/debugging/mobile-emulator-session-2026-10-17.md`](../docs/debugging/mobile-emulator-session-2026-10-17.md).

For a Flutter compile check without the Android SDK:

```powershell
flutter build web --release --dart-define-from-file=config/development.example.json
```

The web build is only a compile check. `flutter_secure_storage` documents its
web storage implementation as experimental; this app is intended for native
mobile use and should not be deployed as a browser authentication client.

## API fields used

- `GET /api/v1/helmets` and `/api/v1/helmets/{helmet_id}` for device/workplace
  identity, current readings, connectivity and last-seen state.
- `GET /api/v1/helmets/{helmet_id}/risk` for the separately computed,
  explainable rule-based risk level and reasons. A failed/unknown evaluation is
  displayed as `Unknown`; it never becomes `Normal` because a value is missing.
- `GET /api/v1/incidents`, `/api/v1/incidents/{incident_id}` and
  `/api/v1/incidents/{incident_id}/history` for active incident details/history.
- `POST /api/v1/incidents/{incident_id}/acknowledge` only when server-side
  authorization is configured.

Sensor units and nullable values are carried from contract v1. A missing value
is rendered as “No value” along with its missing/stale/invalid quality state.
