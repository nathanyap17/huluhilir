import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models.dart';
import '../providers.dart';
import '../terrain_3d_view.dart';
import '../terrain_canvas.dart' show TerrainCanvas; // stateColour/stateLabelMs, and a safe 2D fallback
import '../theme.dart';
import 'diagnosis_screen.dart';

/// docs/PROJECT_SPEC.md §7. Section order is deliberate and matches the spec:
/// rain pulse (always) → advisor (conditional) → priority action (the
/// arbitration result) → terrain canvas → neighbour consent gate.
///
/// Every section renders on a farm with zero photographs ever taken
/// (huluhilir-rules skill §6) — nothing here is gated behind a diagnosis.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final farm = session.farm;

    if (farm == null) {
      return const Scaffold(body: Center(child: Text('Tiada ladang')));
    }

    final dashboard = ref.watch(dashboardProvider(farm.farmId));
    final cycle = ref.watch(currentCycleProvider(farm.farmId));

    return Scaffold(
      backgroundColor: AppColors.cream,
      body: SafeArea(
        child: Column(children: [
          _Header(
            farmName: farm.name,
            onRefresh: () => ref.invalidate(dashboardProvider(farm.farmId)),
            onResetLongPress: () => ref.read(sessionProvider.notifier).reset(),
          ),
          Expanded(
            child: dashboard.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _ErrorPane(
                message: '$e',
                onRetry: () => ref.invalidate(dashboardProvider(farm.farmId)),
              ),
              data: (data) => RefreshIndicator(
                onRefresh: () async => ref.invalidate(dashboardProvider(farm.farmId)),
                child: ListView(
                  // Disabled while a pointer is down over the 3D terrain, so
                  // OrbitControls' drag-to-rotate and tap-to-select work
                  // instead of the page scrolling out from under the touch.
                  // See terrainInteractingProvider's doc comment.
                  physics: ref.watch(terrainInteractingProvider)
                      ? const NeverScrollableScrollPhysics()
                      : const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.all(24),
                  children: [
                    cycle.maybeWhen(
                      data: (c) =>
                          c == null ? const SizedBox.shrink() : _ResumeCard(cycle: c, farmId: farm.farmId),
                      orElse: () => const SizedBox.shrink(),
                    ),
                    _RainPulseCard(pulse: data.rainPulse),
                    const SizedBox(height: 24),
                    if (data.advisor != null) ...[
                      _AdvisorCard(advisor: data.advisor!, farmId: farm.farmId),
                      const SizedBox(height: 24),
                    ],
                    if (data.topAction != null) ...[
                      _MainActionCard(action: data.topAction!, blocks: data.blocks),
                      const SizedBox(height: 24),
                    ],
                    _TerrainCard(data: data),
                    const SizedBox(height: 24),
                    if (data.pendingNeighbourAlerts > 0) _NeighbourConsentCard(count: data.pendingNeighbourAlerts),
                    const SizedBox(height: 100),
                  ],
                ),
              ),
            ),
          ),
        ]),
      ),
      floatingActionButton: _FabColumn(farmId: farm.farmId),
    );
  }
}

class _Header extends StatelessWidget {
  final String farmName;
  final VoidCallback onRefresh;
  final VoidCallback onResetLongPress;
  const _Header({required this.farmName, required this.onRefresh, required this.onResetLongPress});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
      decoration: const BoxDecoration(
        color: AppColors.cream,
        border: Border(bottom: BorderSide(color: AppColors.hairline, width: 1)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('HuluHilir',
                style: AppText.serif(size: 34, weight: FontWeight.bold, color: AppColors.olive)),
            const SizedBox(height: 4),
            Text('Dari hulu ke hilir — sebelum penyakit sampai.',
                style: AppText.sans(size: 13, weight: FontWeight.w500, color: AppColors.oliveLight)
                    .copyWith(fontStyle: FontStyle.italic)),
            const SizedBox(height: 2),
            Text(farmName, style: AppText.sans(size: 12, color: AppColors.charcoal)),
          ]),
        ),
        IconButton(onPressed: onRefresh, icon: const Icon(Icons.refresh, color: AppColors.olive)),
        // Tetapan (settings). Long-press resets the farm -- deliberately
        // hidden behind a long-press so a stray tap can never wipe a farm
        // (docs/PROJECT_SPEC.md §7 "hide reset").
        GestureDetector(
          onLongPress: onResetLongPress,
          child: IconButton(
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Tetapan — tekan lama untuk tetapkan semula ladang')),
            ),
            icon: const Icon(Icons.settings_outlined, color: AppColors.olive),
          ),
        ),
      ]),
    );
  }
}

class _RainPulseCard extends StatelessWidget {
  final RainPulse pulse;
  const _RainPulseCard({required this.pulse});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.hairline),
        boxShadow: softShadow(),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.water_drop, size: 16, color: AppColors.oliveLight),
          const SizedBox(width: 8),
          Text('DENYUT HUJAN', style: AppText.eyebrow()),
          const Spacer(),
          // Speech playback hook: every user-facing string carries a
          // speech_template_id (huluhilir-rules skill §8). Wired to audio in
          // Block E; the affordance exists here so the contract is visible.
          IconButton(
            icon: const Icon(Icons.volume_up, color: AppColors.oliveLight),
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('Suara: ${pulse.speechTemplateId ?? "-"} (Block E)')),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(pulse.rainfallMm.toStringAsFixed(0), style: AppText.serif(size: 48, weight: FontWeight.bold)),
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 8),
            child: Text('mm', style: AppText.sans(size: 20, color: AppColors.charcoal)),
          ),
          const SizedBox(width: 16),
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(
              '${pulse.dayLabel} · ${pulse.daysAway == 0 ? "hari ini" : "${pulse.daysAway} hari lagi"}',
              style: AppText.sans(weight: FontWeight.w600, color: AppColors.olive),
            ),
          ),
        ]),
      ]),
    );
  }
}

class _AdvisorCard extends ConsumerWidget {
  final AdvisorVerdict advisor;
  final String farmId;
  const _AdvisorCard({required this.advisor, required this.farmId});

  bool get _isCall => advisor.urgency == 'high' || advisor.urgency == 'medium';

  String get _badge {
    switch (advisor.urgency) {
      case 'high':
      case 'medium':
        return 'AKTIF';
      case 'low':
        return 'STABIL';
      default:
        return 'OK';
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.olive,
        borderRadius: BorderRadius.circular(AppRadius.card),
        boxShadow: softShadow(tint: AppColors.olive.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(_isCall ? Icons.warning_amber_rounded : Icons.check_circle_outline,
              size: 16, color: Colors.white.withValues(alpha: 0.8)),
          const SizedBox(width: 8),
          Text('ADVISOR', style: AppText.eyebrow(color: Colors.white.withValues(alpha: 0.8))),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(AppRadius.chip),
            ),
            child: Text(_badge, style: AppText.sans(size: 10, weight: FontWeight.w700, color: Colors.white)),
          ),
        ]),
        SizedBox(height: _isCall ? 16 : 8),
        Text(
          advisor.reasonMs,
          style: AppText.serif(size: 18, color: Colors.white, height: 1.25),
        ),
        if (_isCall) ...[
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.button)),
                elevation: 0,
              ),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text('MULA DIAGNOSIS',
                    style: AppText.sans(weight: FontWeight.w700, color: AppColors.olive)),
                const SizedBox(width: 8),
                const Icon(Icons.arrow_forward, size: 16, color: AppColors.olive),
              ]),
            ),
          ),
        ],
      ]),
    );
  }
}

class _MainActionCard extends StatelessWidget {
  final RecommendationModel action;
  final List<BlockModel> blocks;
  const _MainActionCard({required this.action, required this.blocks});

  String get _blockLabel => blocks
      .firstWhere(
        (b) => b.blockId == action.blockId,
        orElse: () => BlockModel(
          blockId: action.blockId,
          label: 'Blok',
          photoUri: '',
          lat: 0,
          lon: 0,
          elevationRank: 0,
          drainage: 'fair',
          currentState: 'protected',
          isExternal: false,
        ),
      )
      .label;

  String get _actionMs {
    switch (action.actionType) {
      case 'clear_drain':
        return 'Buka parit';
      case 'spray':
        return 'Sembur';
      case 'drench':
        return 'Rendam';
      case 'remove_vine':
        return 'Cabut pokok';
      case 'isolate_vine':
        return 'Asingkan pokok';
      case 'inspect':
        return 'Periksa';
      default:
        return 'Tiada tindakan';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.cardOffWhite,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.olive, width: 2),
        boxShadow: softShadow(),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('TINDAKAN UTAMA', style: AppText.eyebrow(color: AppColors.olive)),
        const SizedBox(height: 12),
        Text('$_actionMs — $_blockLabel${_terminal(action.reasonMs)}',
            style: AppText.serif(size: 20, weight: FontWeight.bold)),
        if (action.deferCause != null) ...[
          const SizedBox(height: 8),
          Row(children: [
            const Icon(Icons.arrow_forward, size: 16, color: AppColors.terracotta),
            const SizedBox(width: 6),
            Expanded(
              child: Text('ditangguh: ${action.deferCause}',
                  style: AppText.sans(size: 14, weight: FontWeight.w600, color: AppColors.terracotta)),
            ),
          ]),
        ],
      ]),
    );
  }

  String _terminal(String reason) => reason.isEmpty ? '.' : '. $reason';
}

class _TerrainCard extends StatelessWidget {
  final DashboardModel data;
  const _TerrainCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final labels = {for (final b in data.blocks) b.blockId: b.label};

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.hairline),
        boxShadow: softShadow(),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('TERRAIN RISK MODEL', style: AppText.eyebrow()),
        const SizedBox(height: 4),
        Text('Anggaran sahaja — bukan ukuran lapangan.',
            style: AppText.sans(size: 11, color: AppColors.oliveLight)
                .copyWith(fontStyle: FontStyle.italic)),
        const SizedBox(height: 20),
        // webview_flutter has no web implementation, so the 3D scene cannot
        // run in a browser build. TerrainCanvas -- the 2D flow diagram kept
        // deliberately as a fallback when the 3D view replaced it -- takes
        // an identical set of arguments, so this is a straight swap rather
        // than a second implementation to maintain. Android is unaffected:
        // kIsWeb is a compile-time constant there, so the APK still gets the
        // 3D view and this branch is tree-shaken out entirely.
        if (kIsWeb)
          TerrainCanvas(
            nodes: data.terrainNodes,
            edges: data.terrainEdges,
            labels: labels,
            profileBuilder: (blockId) => _BlockProfile(
              block: data.blocks.firstWhere((b) => b.blockId == blockId),
              action: data.topAction?.blockId == blockId ? data.topAction : null,
            ),
          )
        else
          Terrain3DView(
            nodes: data.terrainNodes,
            edges: data.terrainEdges,
            labels: labels,
            profileBuilder: (blockId) => _BlockProfile(
              block: data.blocks.firstWhere((b) => b.blockId == blockId),
              action: data.topAction?.blockId == blockId ? data.topAction : null,
            ),
          ),
      ]),
    );
  }
}

/// The "profile overlay" content shown when a terrain chip is tapped: a
/// header identifying the block/state, and whatever recommendation history
/// is on hand. A full diagnosis timeline (docs/PROJECT_SPEC.md §7's "diagnosis
/// history" list) needs a history endpoint that doesn't exist yet -- this
/// shows the current state and, if there is one, the live top action for this
/// block, rather than fabricating a longer history.
class _BlockProfile extends StatelessWidget {
  final BlockModel block;
  final RecommendationModel? action;
  const _BlockProfile({required this.block, this.action});

  @override
  Widget build(BuildContext context) {
    final colour = TerrainCanvas.stateColour(block.currentState);
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Container(
        height: 90,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [colour.withValues(alpha: 0.55), colour],
          ),
        ),
        child: Align(
          alignment: Alignment.bottomLeft,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(block.label,
                style: AppText.sans(size: 16, weight: FontWeight.w700, color: Colors.white)),
            Text('#${block.elevationRank} · ${TerrainCanvas.stateLabelMs(block.currentState)}',
                style: AppText.sans(size: 12, color: Colors.white.withValues(alpha: 0.9))),
          ]),
        ),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Text('Saliran: ${block.drainage}', style: AppText.sans(size: 12)),
          if (block.vineCount != null)
            Text('Bilangan pokok: ${block.vineCount}', style: AppText.sans(size: 12)),
          if (action != null) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.cardOffWhite,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('TINDAKAN DISYORKAN',
                    style: AppText.sans(size: 9, weight: FontWeight.w700, color: AppColors.olive)),
                const SizedBox(height: 4),
                Text(action!.reasonMs, style: AppText.sans(size: 12)),
              ]),
            ),
          ],
        ]),
      ),
    ]);
  }
}

class _NeighbourConsentCard extends StatelessWidget {
  final int count;
  const _NeighbourConsentCard({required this.count});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Row(children: [
        const Icon(Icons.mail_outline, color: AppColors.terracotta),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$count pesanan jiran menunggu', style: AppText.sans(weight: FontWeight.w600)),
            // Alerts are DRAFTED, never auto-sent: dispatch requires explicit
            // farmer approval (huluhilir-rules skill §5).
            Text('Perlu kelulusan anda sebelum dihantar',
                style: AppText.sans(size: 12, color: AppColors.oliveLight)),
          ]),
        ),
        const Icon(Icons.chevron_right, color: AppColors.oliveLight),
      ]),
    );
  }
}

class _ResumeCard extends StatelessWidget {
  final DiagnosisCycleModel cycle;
  final String farmId;
  const _ResumeCard({required this.cycle, required this.farmId});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(color: AppColors.terracotta, width: 1.5),
        ),
        child: InkWell(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
          ),
          child: Row(children: [
            const Icon(Icons.play_circle_outline, color: AppColors.terracotta),
            const SizedBox(width: 14),
            Expanded(
              child: Text('Sambung diagnosis (${cycle.blocksCaptured}/${cycle.blocksTotal} blok)',
                  style: AppText.sans(weight: FontWeight.w600)),
            ),
            const Icon(Icons.chevron_right, color: AppColors.oliveLight),
          ]),
        ),
      ),
    );
  }
}

class _ErrorPane extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorPane({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.cloud_off, size: 48, color: AppColors.oliveLight),
          const SizedBox(height: 12),
          Text('Tidak dapat sambung ke pelayan',
              style: AppText.sans(size: 17, weight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(message, textAlign: TextAlign.center, style: AppText.sans(size: 12, color: AppColors.oliveLight)),
          const SizedBox(height: 16),
          FilledButton(onPressed: onRetry, child: const Text('CUBA LAGI')),
        ]),
      ),
    );
  }
}

/// Two stacked circular FABs: a small "Tanya" chat button above a large
/// camera/diagnosis button, matching the design spec's FAB column.
///
/// Reset lives behind a long-press on the header's settings icon instead of
/// here -- overloading a FAB's long-press with an unrelated destructive
/// action would be confusing, and a farmer cannot wipe their farm by
/// mis-tapping either way (docs/PROJECT_SPEC.md §7 "hide reset").
class _FabColumn extends ConsumerWidget {
  final String farmId;
  const _FabColumn({required this.farmId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: Colors.white,
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.hairline),
          boxShadow: softShadow(),
        ),
        child: IconButton(
          icon: const Icon(Icons.chat_bubble_outline, color: AppColors.olive, size: 20),
          onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Tanya (RAG) — datang tidak lama lagi')),
          ),
        ),
      ),
      const SizedBox(height: 16),
      Container(
        width: 56,
        height: 56,
        decoration: BoxDecoration(
          color: AppColors.olive,
          shape: BoxShape.circle,
          boxShadow: softShadow(tint: AppColors.olive.withValues(alpha: 0.35)),
        ),
        child: IconButton(
          icon: const Icon(Icons.camera_alt_outlined, color: Colors.white),
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
          ),
        ),
      ),
    ]);
  }
}
