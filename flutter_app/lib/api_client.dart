import 'dart:io';

import 'package:dio/dio.dart';

import 'config.dart';
import 'models.dart';

/// Thin typed wrapper over the backend. Every method maps 1:1 to an endpoint
/// in backend/app/routers/ -- keep them in the same order for easy diffing.
class ApiClient {
  final Dio _dio;

  ApiClient([Dio? dio])
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: AppConfig.apiBaseUrl,
              // Generous: the agent turn runs a local 14B model over several
              // sequential tool calls and legitimately takes minutes.
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(minutes: 5),
            ));

  Future<bool> health() async {
    try {
      final r = await _dio.get('/health');
      return r.data['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  // ---- setup ---------------------------------------------------------------

  Future<UserModel> createUser({
    required String displayName,
    required String district,
    String languagePref = 'ms',
  }) async {
    final r = await _dio.post('/users', data: {
      'display_name': displayName,
      'district': district,
      'language_pref': languagePref,
    });
    return UserModel.fromJson(r.data);
  }

  Future<FarmModel> createFarm({
    required String userId,
    required String name,
    required double lat,
    required double lon,
    required bool barometerAvailable,
  }) async {
    final r = await _dio.post('/farms', data: {
      'user_id': userId,
      'name': name,
      'centroid_lat': lat,
      'centroid_lon': lon,
      'barometer_available': barometerAvailable,
    });
    return FarmModel.fromJson(r.data);
  }

  Future<String> startWalkSession(String farmId, {double? baselinePressureHpa}) async {
    final r = await _dio.post(
      '/farms/$farmId/walk-sessions',
      queryParameters: {
        if (baselinePressureHpa != null) 'baseline_pressure_hpa': baselinePressureHpa,
      },
    );
    return r.data['walk_session_id'];
  }

  Future<void> flushWalkSamples(String walkSessionId, List<Map<String, dynamic>> samples) async {
    if (samples.isEmpty) return;
    await _dio.post('/walk-sessions/$walkSessionId/samples', data: {'samples': samples});
  }

  Future<BlockModel> captureBlock({
    required String farmId,
    required String label,
    required String photoUri,
    String? voiceLabelUri,
    required List<List<double>> positionSamples,
    double? baroRelM,
    String drainage = 'fair',
    int? vineCount,
  }) async {
    final r = await _dio.post('/farms/$farmId/blocks', data: {
      'label': label,
      'photo_uri': photoUri,
      'voice_label_uri': voiceLabelUri,
      'position_samples': positionSamples,
      'baro_rel_m': baroRelM,
      'drainage': drainage,
      'vine_count': vineCount,
    });
    return BlockModel.fromJson(r.data);
  }

  Future<List<ElevationQuestion>> elevationQuestions(String farmId) async {
    final r = await _dio.get('/farms/$farmId/elevation-questions');
    return (r.data['questions'] as List).map((e) => ElevationQuestion.fromJson(e)).toList();
  }

  Future<Map<String, dynamic>> resolveElevation(
      String farmId, List<Map<String, String>> answers) async {
    final r = await _dio.post('/farms/$farmId/resolve-elevation', data: {'answers': answers});
    return Map<String, dynamic>.from(r.data);
  }

  // ---- media ---------------------------------------------------------------

  Future<String> uploadMedia(File file, {required String contentType}) async {
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(
        file.path,
        contentType: DioMediaType.parse(contentType),
      ),
    });
    final r = await _dio.post('/media', data: form);
    return r.data['uri'];
  }

  // ---- diagnosis -----------------------------------------------------------

  Future<DiagnosisCycleModel> startDiagnosisCycle(String farmId,
      {String triggerReason = 'user_initiated'}) async {
    final r = await _dio.post('/farms/$farmId/diagnosis-cycles',
        data: {'trigger_reason': triggerReason});
    return DiagnosisCycleModel.fromJson(r.data);
  }

  Future<DiagnosisCycleModel?> currentCycle(String farmId) async {
    final r = await _dio.get('/farms/$farmId/diagnosis-cycles/current');
    if (r.data == null) return null;
    return DiagnosisCycleModel.fromJson(r.data);
  }

  Future<DiagnosisResult> submitObservation({
    required String blockId,
    required String userId,
    required String imageUri,
    required String imageHash,
    required String captureTarget,
    String? cycleId,
  }) async {
    final r = await _dio.post('/observations', data: {
      'block_id': blockId,
      'user_id': userId,
      'image_uri': imageUri,
      'image_hash': imageHash,
      'capture_target': captureTarget,
      'cycle_id': cycleId,
      'captured_at': DateTime.now().toIso8601String(),
    });
    return DiagnosisResult.fromJson(r.data);
  }

  /// Re-fetch a farm by id. Used to rehydrate a persisted session on launch,
  /// so setup_completed_at reflects server truth rather than whatever was
  /// cached when the app was last closed.
  Future<FarmModel> getFarm(String farmId) async {
    final r = await _dio.get('/farms/$farmId');
    return FarmModel.fromJson(r.data);
  }

  Future<UserModel> getUser(String userId) async {
    final r = await _dio.get('/users/$userId');
    return UserModel.fromJson(r.data);
  }

  // ---- dashboard / agent ---------------------------------------------------

  Future<DashboardModel> dashboard(String farmId) async {
    final r = await _dio.get('/farms/$farmId/dashboard');
    return DashboardModel.fromJson(r.data);
  }

  Future<Map<String, dynamic>> runAgent({
    required String farmId,
    required String message,
    String? cycleId,
  }) async {
    final r = await _dio.post('/agent/run', data: {
      'farm_id': farmId,
      'message': message,
      'cycle_id': cycleId,
    });
    return Map<String, dynamic>.from(r.data);
  }

  String mediaUrl(String uri) => '${AppConfig.apiBaseUrl}$uri';
}
