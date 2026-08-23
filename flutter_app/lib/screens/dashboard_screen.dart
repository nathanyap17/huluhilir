import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models.dart';
import '../providers.dart';
import '../terrain_canvas.dart';
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
      appBar: AppBar(
        title: Text(farm.name),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(dashboardProvider(farm.farmId)),
          ),
        ],
      ),
      body: dashboard.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _ErrorPane(
          message: '$e',
          onRetry: () => ref.invalidate(dashboardProvider(farm.farmId)),
        ),
        data: (data) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(dashboardProvider(farm.farmId)),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Resume prompt: on app open mid-cycle we land here, never drop
              // straight into capture (docs/PROJECT_SPEC.md §7).
              cycle.maybeWhen(
                data: (c) => c == null
                    ? const SizedBox.shrink()
                    : _ResumeCard(cycle: c, farmId: farm.farmId),
                orElse: () => const SizedBox.shrink(),
              ),
              _RainPulseCard(pulse: data.rainPulse),
              const SizedBox(height: 12),
              if (data.advisor != null) ...[
                _AdvisorCard(advisor: data.advisor!, farmId: farm.farmId),
                const SizedBox(height: 12),
              ],
              if (data.topAction != null) ...[
                _PriorityActionCard(action: data.topAction!, blocks: data.blocks),
                const SizedBox(height: 12),
              ],
              _TerrainCard(data: data),
              const SizedBox(height: 12),
              if (data.pendingNeighbourAlerts > 0)
                _NeighbourConsentCard(count: data.pendingNeighbourAlerts),
              const SizedBox(height: 80),
            ],
          ),
        ),
      ),
      floatingActionButton: _FabMenu(farmId: farm.farmId),
    );
  }
}

class _RainPulseCard extends StatelessWidget {
  final RainPulse pulse;
  const _RainPulseCard({required this.pulse});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFFE3F2FD),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(children: [
          const Icon(Icons.umbrella, size: 34, color: Color(0xFF1565C0)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('DENYUT HUJAN',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 1)),
              const SizedBox(height: 4),
              Text(
                '${pulse.dayLabel} · ${pulse.rainfallMm.toStringAsFixed(0)} mm · '
                '${pulse.daysAway == 0 ? "hari ini" : "${pulse.daysAway} hari lagi"}',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
              ),
            ]),
          ),
          // Speech playback hook: every user-facing string carries a
          // speech_template_id (huluhilir-rules skill §8). Wired to audio in
          // Block E; the affordance exists here so the contract is visible.
          IconButton(
            icon: const Icon(Icons.volume_up),
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('Suara: ${pulse.speechTemplateId ?? "-"} (Block E)')),
            ),
          ),
        ]),
      ),
    );
  }
}

class _AdvisorCard extends ConsumerWidget {
  final AdvisorVerdict advisor;
  final String farmId;
  const _AdvisorCard({required this.advisor, required this.farmId});

  Color get _tint {
    switch (advisor.urgency) {
      case 'high':
        return const Color(0xFFFFF3E0);
      case 'medium':
        return const Color(0xFFFFFDE7);
      default:
        return const Color(0xFFF1F8E9);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 'low'/'none' is the evidence-backed "no action needed" case -- an AI
    // that tells you NOT to work today (docs/DATA_MODEL.md §18).
    final isCall = advisor.urgency == 'high' || advisor.urgency == 'medium';

    return Card(
      color: _tint,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(isCall ? Icons.warning_amber : Icons.check_circle_outline,
                color: isCall ? Colors.orange.shade800 : Colors.green.shade700),
            const SizedBox(width: 10),
            const Text('PENASIHAT',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 1)),
          ]),
          const SizedBox(height: 8),
          Text(advisor.reasonMs, style: const TextStyle(fontSize: 16)),
          if (isCall) ...[
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
              ),
              child: const Text('MULA DIAGNOSIS'),
            ),
          ],
        ]),
      ),
    );
  }
}

class _PriorityActionCard extends StatelessWidget {
  final RecommendationModel action;
  final List<BlockModel> blocks;
  const _PriorityActionCard({required this.action, required this.blocks});

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
    return Card(
      color: const Color(0xFFE8F5E9),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('TINDAKAN UTAMA',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 1)),
          const SizedBox(height: 8),
          Text('$_actionMs — $_blockLabel',
              style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Text(action.reasonMs, style: const TextStyle(fontSize: 15)),
          // The arbitration record made visible: this is the evidence the agent
          // chose between conflicting model outputs (docs/DATA_MODEL.md §16).
          if (action.deferCause != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.orange.shade100,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text('↳ ditangguh: ${action.deferCause}',
                  style: TextStyle(fontSize: 13, color: Colors.orange.shade900)),
            ),
          ],
        ]),
      ),
    );
  }
}

class _TerrainCard extends StatelessWidget {
  final DashboardModel data;
  const _TerrainCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final labels = {for (final b in data.blocks) b.blockId: b.label};

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 4),
            child: Text('MODEL RISIKO TERRAIN',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 1)),
          ),
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 8),
            child: Text('Anggaran sahaja — bukan ukuran lapangan.',
                style: TextStyle(fontSize: 11, fontStyle: FontStyle.italic, color: Colors.grey)),
          ),
          TerrainCanvas(
            nodes: data.terrainNodes,
            edges: data.terrainEdges,
            labels: labels,
            onTapBlock: (blockId) => _showBlockSheet(context, blockId, data),
          ),
        ]),
      ),
    );
  }

  void _showBlockSheet(BuildContext context, String blockId, DashboardModel data) {
    final block = data.blocks.firstWhere((b) => b.blockId == blockId);
    showModalBottomSheet(
      context: context,
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(block.label, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Chip(
            label: Text(TerrainCanvas.stateLabelMs(block.currentState)),
            backgroundColor: TerrainCanvas.stateColour(block.currentState).withValues(alpha: 0.15),
          ),
          const SizedBox(height: 12),
          Text('Kedudukan hulu-hilir: #${block.elevationRank}'),
          Text('Saliran: ${block.drainage}'),
          if (block.vineCount != null) Text('Bilangan pokok: ${block.vineCount}'),
          if (block.voiceLabelUri != null)
            TextButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.play_arrow),
              label: const Text('Main rakaman suara'),
            ),
        ]),
      ),
    );
  }
}

class _NeighbourConsentCard extends StatelessWidget {
  final int count;
  const _NeighbourConsentCard({required this.count});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFFF3E5F5),
      child: ListTile(
        leading: const Icon(Icons.mail_outline),
        title: Text('$count pesanan jiran menunggu'),
        // Alerts are DRAFTED, never auto-sent: dispatch requires explicit
        // farmer approval (huluhilir-rules skill §5).
        subtitle: const Text('Perlu kelulusan anda sebelum dihantar'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () {},
      ),
    );
  }
}

class _ResumeCard extends StatelessWidget {
  final DiagnosisCycleModel cycle;
  final String farmId;
  const _ResumeCard({required this.cycle, required this.farmId});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFFFFF8E1),
      child: ListTile(
        leading: const Icon(Icons.play_circle_outline),
        title: Text('Sambung diagnosis (${cycle.blocksCaptured}/${cycle.blocksTotal} blok)'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
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
          const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
          const SizedBox(height: 12),
          const Text('Tidak dapat sambung ke pelayan',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(message,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 16),
          FilledButton(onPressed: onRetry, child: const Text('CUBA LAGI')),
        ]),
      ),
    );
  }
}

/// FAB: Diagnosis · Tanya · Tetapan.
/// Reset is deliberately NOT here — it lives behind a long-press on Tetapan so
/// a farmer cannot wipe their farm by mis-tapping (docs/PROJECT_SPEC.md §7).
class _FabMenu extends ConsumerWidget {
  final String farmId;
  const _FabMenu({required this.farmId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return FloatingActionButton(
      onPressed: () => showModalBottomSheet(
        context: context,
        builder: (sheetContext) => SafeArea(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('Diagnosis'),
              onTap: () {
                Navigator.pop(sheetContext);
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => DiagnosisScreen(farmId: farmId)),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.chat_bubble_outline),
              title: const Text('Tanya'),
              onTap: () => Navigator.pop(sheetContext),
            ),
            ListTile(
              leading: const Icon(Icons.settings),
              title: const Text('Tetapan'),
              onLongPress: () {
                Navigator.pop(sheetContext);
                ref.read(sessionProvider.notifier).reset();
              },
              onTap: () => Navigator.pop(sheetContext),
            ),
          ]),
        ),
      ),
      child: const Icon(Icons.auto_awesome),
    );
  }
}
