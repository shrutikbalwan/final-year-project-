# Mobile emulator verification — 2026-10-17

## Toolchain

- Windows 11
- Flutter 3.47.7 / Dart 3.13.5 (`D:\tools\flutter`)
- Android SDK platform 36 and build tools 36.0.0 (`D:\tools\android-sdk`)
- Android Emulator 37.2.12 and NDK 28.2.13676358
- Android 16 / API 36 x86_64 Google APIs ATD emulator (`HelmetSmoke`)
- Java 21

The Android SDK is external to the repository. Windows user environment values
point to the Flutter SDK, Android SDK and AVD directory. No Android Studio was
needed.

## Checks

- `flutter doctor -v`: Android toolchain recognized and Android licenses
  accepted.
- `flutter analyze`: no issues found.
- `flutter test`: 19 tests passed.
- `flutter build apk --debug --dart-define-from-file=config/development.example.json`:
  succeeded. The generated debug APK is ignored under
  `mobile-app/build/app/outputs/flutter-apk/app-debug.apk`.
- Installed and launched the APK on the API 36 emulator. Selected the clearly
  labeled read-only development access path.

## API smoke test

The API ran locally on port 8000 using an isolated SQLite database at
`D:\tools\smart-safety-mobile-emulator.sqlite3`. One synthetic telemetry
message was posted; no real worker or device data was used:

- Device: `helmet-emulator-synthetic-001`
- Workplace: `workplace-emulator-synthetic`
- API accepted telemetry with HTTP 201 and returned the device in the helmet
  list with HTTP 200.
- The mobile app displayed that device and read its detail and risk endpoints
  successfully (HTTP 200).
- The device detail showed temperature `28.5 Cel`, the gas value as `No value`
  with status `missing`, and risk `Unknown` because no workplace safety profile
  was configured. Missing data was not shown as zero or as a safe state.

Screenshot evidence: [mobile-emulator-screen-2026-10-17.png](mobile-emulator-screen-2026-10-17.png).

## Reproduce in PowerShell

Open a new PowerShell terminal after the Flutter and Android SDK user
environment variables have been set:

```powershell
flutter doctor -v
flutter emulators
emulator -avd HelmetSmoke -no-snapshot -no-audio

# In a second PowerShell terminal, from the repository root:
$env:HELMET_DB_PATH = "D:\tools\smart-safety-mobile-emulator.sqlite3"
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# In a third PowerShell terminal:
Set-Location .\mobile-app
flutter analyze
flutter test
flutter build apk --debug --dart-define-from-file=.\config\development.example.json
flutter run -d emulator-5554 --dart-define-from-file=.\config\development.example.json
```

The synthetic telemetry is not seeded by the app; post a valid telemetry
contract to `/api/v1/telemetry` before expecting a helmet card. The temporary
database can be removed after stopping the local API.
