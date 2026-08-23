import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:record/record.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../brand.dart';
import '../tier_banner.dart';
import '../walk_map.dart';
import 'package:latlong2/latlong.dart';
import '../models.dart';
import '../providers.dart';
import '../recording_io.dart';
import 'elevation_screen.dart';

/// Step ④ of setup: the walk loop (docs/PROJECT_SPEC.md §5).
/// PLAN.md lists this under "never cut".
///
/// Continuously buffers GPS (and pressure, on OPTIMISED devices) while the
/// farmer walks. Tapping "TANDA BLOK" freezes the last ±5 s of position
/// samples; their MEDIAN becomes the block centroid, which rejects the jitter
/// spikes a single reading would inherit.
class WalkScreen extends ConsumerStatefulWidget {
  const WalkScreen({super.key});

  @override
  ConsumerState<WalkScreen> createState() => _WalkScreenState();
}

class _WalkScreenState extends ConsumerState<WalkScreen> {
  StreamSubscription<Position>? _positionSub;
  StreamSubscription<BarometerEvent>? _barometerSub;
  Timer? _flushTimer;

  final List<_Sample> _recent = [];
  final List<_Sample> _unflushed = [];
  final List<BlockModel> _captured = [];

  String? _walkSessionId;
  int _flushedCount = 0;
  bool _offline = false;
  double? _baselinePressure;
  double? _latestPressure;
  Position? _latestPosition;
  bool _starting = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _startWalk();
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _barometerSub?.cancel();
    _flushTimer?.cancel();
    super.dispose();
  }

  /// Buffer locally, flush periodically. A farmer walking a hillside has no
  /// connectivity guarantee, so samples accumulate in memory (and survive a
  /// failed flush) rather than being lost — losing a walk because the API was
  /// briefly unreachable would be the worst failure this screen has.
  Future<void> _flushSamples() async {
    if (_walkSessionId == null || _unflushed.isEmpty) return;

    final batch = _unflushed
        .map((s) => {
              'walk_session_id': _walkSessionId,
              'lat': s.position.latitude,
              'lon': s.position.longitude,
              'gps_alt_m': s.position.altitude,
              'gps_accuracy_m': s.position.accuracy,
              'baro_alt_m': null,
              'pressure_hpa': s.pressure,
              'recorded_at': s.at.toIso8601String(),
            })
        .toList();

    try {
      await ref.read(apiClientProvider).flushWalkSamples(_walkSessionId!, batch);
      _flushedCount += batch.length;
      _unflushed.clear();
      if (mounted && _offline) setState(() => _offline = false);
    } catch (_) {
      // Keep them buffered and retry on the next tick.
      if (mounted && !_offline) setState(() => _offline = true);
    }
  }

  Future<void> _startWalk() async {
    try {
      final session = ref.read(sessionProvider);
      final api = ref.read(apiClientProvider);
      final farm = session.farm!;

      // Establish the pressure baseline BEFORE walking -- every later
      // baro_rel_m is relative to it (docs/DATA_MODEL.md §3).
      if (farm.barometerAvailable) {
        try {
          final event = await barometerEventStream().first.timeout(const Duration(seconds: 3));
          _baselinePressure = event.pressure;
        } catch (_) {
          _baselinePressure = null;
        }
      }

      _walkSessionId = await api.startWalkSession(
        farm.farmId,
        baselinePressureHpa: _baselinePressure,
      );

      _positionSub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.best, distanceFilter: 0),
      ).listen((position) {
        _latestPosition = position;
        final now = DateTime.now();
        final sample = _Sample(position, _latestPressure, now);
        _recent.add(sample);
        _unflushed.add(sample);
        // Keep a rolling 5 s window -- that's all the centroid needs. The
        // separate _unflushed list retains the FULL trace, which is evidence
        // the walk happened (docs/DATA_MODEL.md §4).
        _recent.removeWhere((s) => now.difference(s.at) > const Duration(seconds: 5));
        if (mounted) setState(() {});
      });

      if (farm.barometerAvailable) {
        _barometerSub = barometerEventStream().listen((e) => _latestPressure = e.pressure);
      }

      _flushTimer = Timer.periodic(const Duration(seconds: 10), (_) => _flushSamples());

      if (mounted) setState(() => _starting = false);
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _starting = false;
        });
      }
    }
  }

  double? get _baroRelM {
    if (_baselinePressure == null || _latestPressure == null) return null;
    // Barometric formula, simplified for small altitude deltas: ~8.43 m per hPa
    // near sea level. Relative only -- absolute altitude is never claimed.
    return (_baselinePressure! - _latestPressure!) * 8.43;
  }

  Future<void> _captureBlock() async {
    if (_recent.isEmpty) {
      _showError('Menunggu isyarat GPS...');
      return;
    }

    final samples = _recent.map((s) => [s.position.latitude, s.position.longitude]).toList();
    final baroRel = _baroRelM;

    final result = await showModalBottomSheet<_BlockDraft>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _BlockCaptureSheet(),
    );
    if (result == null) return;

    try {
      final api = ref.read(apiClientProvider);
      final farm = ref.read(sessionProvider).farm!;

      final photoUri = await api.uploadMedia(
        result.photoBytes,
        contentType: 'image/jpeg',
        filename: result.photoName,
      );
      String? voiceUri;
      if (result.voiceBytes != null) {
        voiceUri = await api.uploadMedia(
          result.voiceBytes!,
          contentType: 'audio/mp4',
          filename: 'voice_label.m4a',
        );
      }

      final block = await api.captureBlock(
        farmId: farm.farmId,
        label: result.label,
        photoUri: photoUri,
        voiceLabelUri: voiceUri,
        positionSamples: samples,
        baroRelM: baroRel,
        drainage: result.drainage,
      );

      setState(() => _captured.add(block));
    } catch (e) {
      _showError('Gagal simpan blok: $e');
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _finishWalk() async {
    if (_captured.length < 2) {
      _showError('Rekod sekurang-kurangnya 2 blok sebelum teruskan.');
      return;
    }
    await _positionSub?.cancel();
    await _barometerSub?.cancel();
    _flushTimer?.cancel();
    await _flushSamples(); // final flush before leaving the walk
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const ElevationScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_starting) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Ralat'), actions: const [BrandLogoAction()]),
        body: Padding(padding: const EdgeInsets.all(20), child: Text(_error!)),
      );
    }

    final accuracy = _latestPosition?.accuracy;
    // Tier comes from the farm record, which was set by the silent probe at
    // registration -- never re-asked and never a choice (PROJECT_SPEC §4).
    final hasBarometer = ref.watch(sessionProvider).farm?.barometerAvailable ?? false;

    return Scaffold(
      appBar: AppBar(title: const Text('Jalan Ladang'), actions: const [BrandLogoAction()]),
      body: Column(children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          color: Colors.green.shade50,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Jalan ke setiap blok lada anda.',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(
              accuracy == null
                  ? 'Menunggu GPS...'
                  : 'Ketepatan GPS: ${accuracy.toStringAsFixed(0)} m',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
            ),
            // Live relative altitude, so a farmer on an OPTIMISED phone can
            // see the sensor is actually tracking them uphill and downhill
            // rather than trusting that it is.
            if (hasBarometer) ...[
              const SizedBox(height: 4),
              AltitudeReadout(relativeM: _baroRelM),
            ],
            Text(
              _offline
                  ? 'Luar talian — ${_unflushed.length} sampel menunggu'
                  : 'Jejak: $_flushedCount sampel disimpan',
              style: TextStyle(
                fontSize: 12,
                color: _offline ? Colors.orange.shade800 : Colors.grey.shade600,
              ),
            ),
            const SizedBox(height: 12),
            // States the tier plainly, and on the minimal path says how many
            // comparison questions the walk will end with -- C(n,2) grows
            // fast and is better known before walking than discovered after.
            TierBanner(
              available: hasBarometer,
              blockCount: _captured.length,
              status: ref.watch(barometerStatusProvider).valueOrNull,
            ),
          ]),
        ),
        // Orientation while walking: the track so far plus what is already
        // marked. Additive only -- capture never depends on a tile loading.
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: WalkMap(
            track: [for (final s in _recent) LatLng(s.position.latitude, s.position.longitude)],
            blocks: _captured,
            current: _recent.isEmpty
                ? null
                : LatLng(_recent.last.position.latitude, _recent.last.position.longitude),
            height: 230,
          ),
        ),
        Expanded(
          child: _captured.isEmpty
              ? const Center(child: Text('Belum ada blok direkod'))
              : ListView.builder(
                  itemCount: _captured.length,
                  itemBuilder: (_, i) {
                    final block = _captured[i];
                    return ListTile(
                      leading: CircleAvatar(child: Text('${i + 1}')),
                      title: Text(block.label),
                      subtitle: Text(block.voiceLabelUri != null
                          ? 'Saliran: ${block.drainage} · ada rakaman suara'
                          : 'Saliran: ${block.drainage}'),
                    );
                  },
                ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              FilledButton.icon(
                onPressed: _captureBlock,
                icon: const Icon(Icons.add_location_alt),
                label: const Text('TANDA BLOK', style: TextStyle(fontSize: 18)),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(60)),
              ),
              const SizedBox(height: 10),
              OutlinedButton(
                onPressed: _finishWalk,
                style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                child: Text('SELESAI (${_captured.length} blok)'),
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Sample {
  final Position position;
  final double? pressure;
  final DateTime at;
  _Sample(this.position, this.pressure, this.at);
}

class _BlockDraft {
  final String label;
  // Bytes, not paths: dart:io's File is unavailable on web, and on web
  // XFile.path is an opaque blob URL that cannot be read from disk anyway.
  final Uint8List photoBytes;
  final String photoName;
  final Uint8List? voiceBytes;
  final String drainage;
  _BlockDraft(this.label, this.photoBytes, this.photoName, this.voiceBytes, this.drainage);
}

/// Photo + optional short label + optional voice recording.
///
/// The voice recording is an AUDIO STICKER: it is stored and replayed to the
/// farmer beside the block photo, and is never transcribed by anything
/// (huluhilir-rules skill §2). That is precisely why Iban works here despite
/// no Iban speech recognition existing.
class _BlockCaptureSheet extends StatefulWidget {
  const _BlockCaptureSheet();

  @override
  State<_BlockCaptureSheet> createState() => _BlockCaptureSheetState();
}

class _BlockCaptureSheetState extends State<_BlockCaptureSheet> {
  final _labelController = TextEditingController();
  final _recorder = AudioRecorder();

  Uint8List? _photoBytes;
  String _photoName = 'block.jpg';
  Uint8List? _voiceBytes;
  String _drainage = 'fair';
  bool _recording = false;

  @override
  void dispose() {
    _labelController.dispose();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _takePhoto() async {
    final picked = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 85);
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _photoBytes = bytes;
      _photoName = picked.name;
    });
  }

  Future<void> _toggleRecording() async {
    if (_recording) {
      // stop() returns a path on mobile and a blob URL on web; read it back
      // through the recorder's own stream instead of touching the filesystem,
      // so the voice label works on both without a dart:io dependency.
      final source = await _recorder.stop();
      Uint8List? bytes;
      if (source != null) {
        try {
          bytes = await readRecording(source);
        } catch (_) {
          // A lost voice label must never block capturing the block itself:
          // it is an optional audio sticker, not required data.
          bytes = null;
        }
      }
      if (!mounted) return;
      setState(() {
        _recording = false;
        _voiceBytes = bytes;
      });
    } else {
      if (!await _recorder.hasPermission()) return;
      await _recorder.start(const RecordConfig(), path: recordingTarget());
      setState(() => _recording = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('Rekod Blok', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: _takePhoto,
          icon: Icon(_photoBytes == null ? Icons.camera_alt : Icons.check_circle,
              color: _photoBytes == null ? null : Colors.green),
          label: Text(_photoBytes == null ? 'AMBIL GAMBAR' : 'Gambar diambil'),
          style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _labelController,
          decoration: const InputDecoration(
            labelText: 'Nama blok (pilihan)',
            hintText: 'cth. Kebun Tua',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: _toggleRecording,
          icon: Icon(_recording ? Icons.stop_circle : Icons.mic,
              color: _recording ? Colors.red : (_voiceBytes != null ? Colors.green : null)),
          label: Text(_recording
              ? 'BERHENTI RAKAM'
              : (_voiceBytes != null ? 'Rakaman disimpan' : 'RAKAM NAMA (pilihan)')),
          style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
        ),
        const SizedBox(height: 14),
        Align(alignment: Alignment.centerLeft, child: const Text('Keadaan saliran:')),
        const SizedBox(height: 6),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'good', label: Text('Baik')),
            ButtonSegment(value: 'fair', label: Text('Sederhana')),
            ButtonSegment(value: 'poor', label: Text('Lemah')),
          ],
          selected: {_drainage},
          onSelectionChanged: (s) => setState(() => _drainage = s.first),
        ),
        const SizedBox(height: 18),
        FilledButton(
          onPressed: _photoBytes == null
              ? null
              : () => Navigator.pop(
                    context,
                    _BlockDraft(
                      _labelController.text.trim().isEmpty
                          ? 'Blok'
                          : _labelController.text.trim(),
                      _photoBytes!,
                      _photoName,
                      _voiceBytes,
                      _drainage,
                    ),
                  ),
          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
          child: const Text('SIMPAN BLOK', style: TextStyle(fontSize: 17)),
        ),
      ]),
    );
  }
}
