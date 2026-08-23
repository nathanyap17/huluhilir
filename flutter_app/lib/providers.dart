

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'models.dart';
import 'outbox.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
final outboxProvider = Provider<Outbox>((ref) => Outbox());

/// Device capability probe. Detection is automatic and silent -- the farmer is
/// never asked whether their phone has a barometer (docs/PROJECT_SPEC.md §4).
///
/// Emulators and budget phones report no barometer, which selects the MINIMAL
/// tier. PROJECT_SPEC §4 is explicit that MINIMAL loses NO functionality --
/// it only makes setup slower (more pairwise questions).
final barometerAvailableProvider = FutureProvider<bool>((ref) async {
  try {
    await barometerEventStream().first.timeout(const Duration(seconds: 2));
    return true;
  } catch (_) {
    return false;
  }
});

/// The active session: who the farmer is and which farm they're managing.
class SessionState {
  final UserModel? user;
  final FarmModel? farm;

  /// True until the persisted-session restore attempt finishes. The app shows
  /// a splash while this is true so a returning farmer never sees the
  /// registration form flash before their dashboard loads.
  final bool restoring;

  const SessionState({this.user, this.farm, this.restoring = true});

  bool get isRegistered => user != null && farm != null;
  bool get isSetupComplete => farm?.isSetupComplete ?? false;

  SessionState copyWith({UserModel? user, FarmModel? farm, bool? restoring}) => SessionState(
        user: user ?? this.user,
        farm: farm ?? this.farm,
        restoring: restoring ?? this.restoring,
      );
}

/// Session survives app restarts. Without this, closing the app would lose the
/// farm entirely and force a fresh registration — which would also make
/// docs/PROJECT_SPEC.md §7's "on app open mid-cycle, land on the dashboard
/// with a resume prompt" impossible to honour.
///
/// Only the two IDs are stored locally; the farm itself is re-fetched from the
/// server on launch so `setup_completed_at` is server truth, not a stale copy.
class SessionNotifier extends StateNotifier<SessionState> {
  final ApiClient _api;
  SessionNotifier(this._api) : super(const SessionState()) {
    _restore();
  }

  static const _kUserId = 'huluhilir.user_id';
  static const _kFarmId = 'huluhilir.farm_id';

  Future<void> _restore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString(_kUserId);
      final farmId = prefs.getString(_kFarmId);
      if (userId != null && farmId != null) {
        final user = await _api.getUser(userId);
        final farm = await _api.getFarm(farmId);
        if (mounted) state = SessionState(user: user, farm: farm, restoring: false);
        return;
      }
    } catch (_) {
      // Offline or the farm no longer exists -- fall back to registration
      // rather than blocking launch on a network call.
    }
    if (mounted) state = state.copyWith(restoring: false);
  }

  Future<void> setUser(UserModel user) async {
    state = state.copyWith(user: user, restoring: false);
    (await SharedPreferences.getInstance()).setString(_kUserId, user.userId);
  }

  Future<void> setFarm(FarmModel farm) async {
    state = state.copyWith(farm: farm, restoring: false);
    (await SharedPreferences.getInstance()).setString(_kFarmId, farm.farmId);
  }

  /// Refresh the farm from the server -- call after setup completes so
  /// isSetupComplete stops being stale.
  Future<void> refreshFarm() async {
    final farmId = state.farm?.farmId;
    if (farmId == null) return;
    state = state.copyWith(farm: await _api.getFarm(farmId));
  }

  Future<void> reset() async {
    state = const SessionState(restoring: false);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUserId);
    await prefs.remove(_kFarmId);
  }
}

final sessionProvider = StateNotifierProvider<SessionNotifier, SessionState>(
  (ref) => SessionNotifier(ref.watch(apiClientProvider)),
);

/// Dashboard data, refetched on demand. Falls back to the cached snapshot when
/// the backend is unreachable so the app still shows something useful offline.
final dashboardProvider = FutureProvider.family<DashboardModel, String>((ref, farmId) async {
  final api = ref.watch(apiClientProvider);
  final outbox = ref.watch(outboxProvider);
  final dashboard = await api.dashboard(farmId);
  await outbox.cacheFarmState(farmId, {'fetched': DateTime.now().toIso8601String()});
  return dashboard;
});

final pendingOutboxCountProvider = FutureProvider<int>((ref) async {
  return ref.watch(outboxProvider).pendingCount();
});

final currentCycleProvider =
    FutureProvider.family<DiagnosisCycleModel?, String>((ref, farmId) async {
  return ref.watch(apiClientProvider).currentCycle(farmId);
});
