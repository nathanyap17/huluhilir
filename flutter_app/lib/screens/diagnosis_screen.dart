

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../brand.dart';
import '../models.dart';
import '../i18n.dart';
import '../providers.dart';
import '../theme.dart';

/// The diagnosis cycle (docs/PROJECT_SPEC.md §6): an EVENT covering all
/// blocks, not a per-photo action, and resumable across app restarts.
///
/// A photo whose predicted body part contradicts what the farmer said they
/// were photographing triggers a RETAKE and does NOT count as a completed
/// check (huluhilir-rules skill §9) — the whole reason `healthy` was split
/// into `healthy_leaf`/`healthy_collar`.
class DiagnosisScreen extends ConsumerStatefulWidget {
  final String farmId;
  const DiagnosisScreen({super.key, required this.farmId});

  @override
  ConsumerState<DiagnosisScreen> createState() => _DiagnosisScreenState();
}

class _DiagnosisScreenState extends ConsumerState<DiagnosisScreen> {
  DiagnosisCycleModel? _cycle;
  List<BlockModel> _blocks = [];
  final Set<String> _done = {};

  /// Blocks whose last photo was rejected. Tracked so the list can offer a
  /// way forward rather than leaving the farmer to guess why nothing happens.
  final Set<String> _stuck = {};
  String _captureTarget = 'collar';
  bool _loading = true;
  bool _busy = false;
  String? _status;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final api = ref.read(apiClientProvider);
      final cycle = await api.startDiagnosisCycle(widget.farmId);
      final dashboard = await api.dashboard(widget.farmId);
      setState(() {
        _cycle = cycle;
        _blocks = dashboard.blocks.where((b) => !b.isExternal).toList()
          ..sort((a, b) => a.elevationRank.compareTo(b.elevationRank));
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _status = 'Ralat: $e';
        _loading = false;
      });
    }
  }

  Future<void> _capture(BlockModel block, {bool forceAccept = false}) async {
    final picked = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 85);
    if (picked == null) return;

    setState(() {
      _busy = true;
      _status = null;
    });

    try {
      final api = ref.read(apiClientProvider);
      final session = ref.read(sessionProvider);
      // XFile.readAsBytes() rather than File(picked.path): dart:io's File
      // throws `Unsupported operation: _Namespace` on web, and the bytes are
      // needed for the content hash regardless.
      final bytes = await picked.readAsBytes();
      final hash = sha256.convert(bytes).toString();

      final imageUri = await api.uploadMedia(
        bytes,
        contentType: 'image/jpeg',
        filename: picked.name,
      );
      final result = await api.submitObservation(
        blockId: block.blockId,
        userId: session.user!.userId,
        imageUri: imageUri,
        imageHash: hash,
        captureTarget: _captureTarget,
        cycleId: _cycle?.cycleId,
        forceAccept: forceAccept,
      );

      setState(() {
        if (result.countsAsCheck) {
          _done.add(block.blockId);
          _status = '${block.label}: ${_classLabelMs(result.predictedClass)}'
              '${result.belowThreshold ? " (keyakinan rendah — periksa sendiri)" : ""}'
              '${result.acceptedDespiteMismatch ? " · diterima selepas beberapa cubaan" : ""}';
          _stuck.remove(block.blockId);
        } else {
          // A retake PROMPT, not a dead end. The block is remembered as
          // needing an override so the list can offer one -- the old code
          // simply refused the photo, which left a cycle permanently stuck
          // on any block the classifier kept misreading.
          _stuck.add(block.blockId);
          final left = result.retakesRemaining;
          _status = '${result.retakePrompt ?? "Sila ambil semula."}'
              '${left > 0 ? " (cubaan ${result.attempt} — $left lagi)" : ""}';
        }
      });

      if (mounted) {
        final refreshed = await api.currentCycle(widget.farmId);
        setState(() => _cycle = refreshed ?? _cycle);
      }
    } catch (e) {
      setState(() => _status = 'Gagal hantar: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _classLabelMs(String cls) {
    switch (cls) {
      case 'healthy_leaf':
        return 'SIHAT (DAUN)';
      case 'healthy_collar':
        return 'SIHAT (PANGKAL)';
      case 'collar_lesion':
        return 'LESI PANGKAL';
      case 'foliar_yellowing':
        return 'DAUN MENGUNING';
      case 'defoliation_wilt':
        return 'GUGUR DAUN / LAYU';
      default:
        return 'TIADA KAITAN';
    }
  }

  Future<void> _runAgent() async {
    setState(() {
      _busy = true;
      _status = 'Ejen sedang menilai... (mungkin ambil beberapa minit)';
    });
    try {
      await ref.read(apiClientProvider).runAgent(
            farmId: widget.farmId,
            message: 'farm_id=${widget.farmId}. Diagnosis cycle complete. '
                'Run the standard sequence and arbitrate one recommendation per affected block.',
            cycleId: _cycle?.cycleId,
          );
      ref.invalidate(dashboardProvider(widget.farmId));
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      setState(() => _status = 'Ejen gagal: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final captured = _cycle?.blocksCaptured ?? _done.length;
    final total = _cycle?.blocksTotal ?? _blocks.length;
    final allDone = captured >= total && total > 0;

    // Arbitration is NOT gated on capturing every block. The product works
    // with zero photographs at all (huluhilir-rules §6), so demanding 100%
    // before it will reason is inconsistent -- and in practice it stranded
    // farmers: one block the classifier kept rejecting meant the run could
    // never start, no matter how many other blocks were checked.
    //
    // One accepted photo is enough to have something to arbitrate over. The
    // button says how complete the picture is so the farmer chooses knowingly
    // rather than being blocked.
    final canArbitrate = captured > 0 && !_busy;

    return Scaffold(
      appBar: AppBar(title: Text('Diagnosis ($captured/$total)'), actions: const [BrandLogoAction()]),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(tr(ref, 'diag.part'),
                  style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'collar', label: Text(tr(ref, 'diag.collar'))),
                ButtonSegment(value: 'leaf', label: Text(tr(ref, 'diag.leaf'))),
              ],
              selected: {_captureTarget},
              onSelectionChanged: (s) => setState(() => _captureTarget = s.first),
            ),
          ]),
        ),
        if (_status != null)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _status!.startsWith('RETAKE') || _status!.startsWith('Sila')
                  ? Colors.orange.shade50
                  : Colors.green.shade50,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(_status!),
          ),
        Expanded(
          child: ListView.builder(
            itemCount: _blocks.length,
            itemBuilder: (_, i) {
              final block = _blocks[i];
              final done = _done.contains(block.blockId);
              final stuck = _stuck.contains(block.blockId);
              return ListTile(
                leading: Icon(
                  done
                      ? Icons.check_circle
                      : stuck
                          ? Icons.error_outline
                          : Icons.radio_button_unchecked,
                  color: done
                      ? Colors.green
                      : stuck
                          ? AppColors.terracotta
                          : Colors.grey,
                ),
                title: Text(block.label),
                subtitle: Text(stuck
                    ? '#${block.elevationRank} · ${tr(ref, 'diag.rejected')}'
                    : '#${block.elevationRank}'),
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  // The escape hatch. Offered only once a photo has actually
                  // been rejected, so it never invites overriding a check
                  // that was working -- but once offered, the farmer standing
                  // in front of the vine can always proceed.
                  if (stuck && !done)
                    TextButton(
                      onPressed: _busy ? null : () => _capture(block, forceAccept: true),
                      child: Text(tr(ref, 'diag.useAnyway')),
                    ),
                  FilledButton.tonal(
                    onPressed: _busy ? null : () => _capture(block),
                    child: Text(done ? tr(ref, 'diag.add') : tr(ref, 'diag.take')),
                  ),
                ]),
              );
            },
          ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: FilledButton(
              onPressed: canArbitrate ? _runAgent : null,
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
              child: _busy
                  ? const SizedBox(
                      height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(
                      allDone
                          ? tr(ref, 'diag.runAgent')
                          : '${tr(ref, 'diag.runAgent')} ($captured/$total)',
                      style: const TextStyle(fontSize: 17),
                    ),
            ),
          ),
        ),
      ]),
    );
  }
}
