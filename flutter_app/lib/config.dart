/// Deployment target is configuration only -- no code branches on it
/// (huluhilir-rules skill §11). Build with:
///   LOCAL (phone on team hotspot): --dart-define=API_BASE_URL=http://<LAN_IP>:8000
///   LOCAL (android emulator):      --dart-define=API_BASE_URL=http://10.0.2.2:8000
///   CLOUD:                         --dart-define=API_BASE_URL=https://<cloud-run-url>
///
/// 10.0.2.2 is the Android emulator's alias for the host machine's loopback --
/// "localhost" inside the emulator is the emulator itself, not the laptop.
class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
}
