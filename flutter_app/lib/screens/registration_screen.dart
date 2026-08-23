import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../brand.dart';
import '../providers.dart';
import 'dashboard_screen.dart';
import 'walk_screen.dart';

/// Steps ① - ③ of the setup flow (docs/PROJECT_SPEC.md §5): register, locate,
/// probe the device for a barometer. The barometer probe is silent -- the
/// farmer is never asked about it, and the resulting tier is shown only as
/// information, never as a choice.
class RegistrationScreen extends ConsumerStatefulWidget {
  const RegistrationScreen({super.key});

  @override
  ConsumerState<RegistrationScreen> createState() => _RegistrationScreenState();
}

class _RegistrationScreenState extends ConsumerState<RegistrationScreen> {
  final _nameController = TextEditingController();
  final _districtController = TextEditingController(text: 'Kuching');
  final _farmNameController = TextEditingController(text: 'Kebun Saya');

  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _districtController.dispose();
    _farmNameController.dispose();
    super.dispose();
  }

  /// District centroids, used only when the device will not give a fix.
  ///
  /// Coordinates here decide one thing: which weather station the farm is
  /// matched to. They are never treated as the farm's real position for
  /// anything else, and they record no boundary or ownership (huluhilir-rules
  /// §4) -- a district centroid is a public reference point, not a location.
  static const _districtCentroids = <String, ({double lat, double lon})>{
    'kuching': (lat: 1.5533, lon: 110.3592),
    'serian': (lat: 1.1667, lon: 110.5667),
    'bau': (lat: 1.4186, lon: 110.1567),
    'samarahan': (lat: 1.4589, lon: 110.4667),
    'sri aman': (lat: 1.2372, lon: 111.4622),
    'sarikei': (lat: 2.1281, lon: 111.5194),
    'sibu': (lat: 2.2874, lon: 111.8306),
    'bintulu': (lat: 3.1714, lon: 113.0417),
    'miri': (lat: 4.3995, lon: 113.9914),
  };

  Future<Position?> _locate() async {
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.best),
      );
    } catch (_) {
      // No fix available at all: browser with geolocation blocked, emulator
      // with no location set, device with location services off. Treated the
      // same as a refusal -- the caller falls back to the district centroid.
      return null;
    }
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      final api = ref.read(apiClientProvider);

      if (!await api.health()) {
        throw Exception('Tidak dapat sambung ke pelayan. Semak WiFi dan cuba lagi.');
      }

      // A refused or unavailable fix must not end setup. Location here only
      // selects the nearest weather station; the farm's structure comes from
      // the walk and from the farmer's own elevation answers, which override
      // sensors anyway (huluhilir-rules §3). Blocking registration on a
      // permission dialog would strand a farmer who tapped "deny" once, and
      // the app is committed to working in degraded conditions.
      final district = _districtController.text.trim();
      final position = await _locate();
      final fallback = _districtCentroids[district.toLowerCase()] ??
          _districtCentroids['kuching']!;
      final lat = position?.latitude ?? fallback.lat;
      final lon = position?.longitude ?? fallback.lon;
      final estimatedLocation = position == null;

      final hasBarometer = await ref.read(barometerAvailableProvider.future);

      final user = await api.createUser(
        displayName: _nameController.text.trim().isEmpty ? 'Petani' : _nameController.text.trim(),
        district: district,
      );
      final farm = await api.createFarm(
        userId: user.userId,
        name: _farmNameController.text.trim(),
        lat: lat,
        lon: lon,
        barometerAvailable: hasBarometer,
      );

      final notifier = ref.read(sessionProvider.notifier);
      await notifier.setUser(user);
      await notifier.setFarm(farm);

      if (!mounted) return;
      if (estimatedLocation) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Lokasi tepat tiada. Stesen cuaca dianggar dari daerah $district.'),
            duration: const Duration(seconds: 5),
          ),
        );
      }
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const WalkScreen()),
      );
    } catch (e) {
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Open the seeded demo farm without going through setup.
  ///
  /// The farm is found by name rather than by a hardcoded ID: IDs are ULIDs
  /// assigned at insert time, and the cloud database is reseeded whenever a
  /// new revision rolls, so any constant baked in here would go stale.
  Future<void> _openDemoFarm() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final farms = await api.listFarms();
      final demo = farms.firstWhere(
        (f) => (f['name'] as String).toLowerCase().contains('demo'),
        orElse: () => throw Exception('Ladang demo tiada pada pelayan.'),
      );

      final user = await api.getUser(demo['user_id'] as String);
      final farm = await api.getFarm(demo['farm_id'] as String);

      final notifier = ref.read(sessionProvider.notifier);
      await notifier.setUser(user);
      await notifier.setFarm(farm);

      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
    } catch (e) {
      setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final barometer = ref.watch(barometerAvailableProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('HuluHilir'), actions: const [BrandLogoAction()]),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('Dari hulu ke hilir — sebelum penyakit sampai.',
              style: TextStyle(fontSize: 16, fontStyle: FontStyle.italic)),
          const SizedBox(height: 24),
          TextField(
            controller: _nameController,
            decoration: const InputDecoration(labelText: 'Nama anda', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _districtController,
            decoration: const InputDecoration(labelText: 'Daerah', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _farmNameController,
            decoration:
                const InputDecoration(labelText: 'Nama ladang', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 20),
          barometer.when(
            data: (available) => _TierBanner(available: available),
            loading: () => const LinearProgressIndicator(),
            error: (_, __) => const _TierBanner(available: false),
          ),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(_error!, style: TextStyle(color: Colors.red.shade900)),
            ),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _busy ? null : _submit,
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
            child: _busy
                ? const SizedBox(
                    height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('MULA', style: TextStyle(fontSize: 18)),
          ),
          const SizedBox(height: 12),
          // Setup requires walking the farm with a GPS fix, which nobody
          // evaluating the app from a desk can do. Without this, the whole
          // dashboard -- rain pulse, advisor, the arbitration result, the
          // terrain model -- is unreachable to anyone who is not standing in
          // a pepper garden. Loads the seeded demo farm read-only instead.
          TextButton(
            onPressed: _busy ? null : _openDemoFarm,
            child: const Text('Lihat ladang demo'),
          ),
        ]),
      ),
    );
  }
}

class _TierBanner extends StatelessWidget {
  final bool available;
  const _TierBanner({required this.available});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Icon(available ? Icons.speed : Icons.phone_android, color: Colors.blue.shade700),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            available
                ? 'Telefon anda ada barometer — persediaan akan lebih pantas.'
                : 'Persediaan akan guna soalan arah air. Semua fungsi tetap berjalan.',
            style: const TextStyle(fontSize: 14),
          ),
        ),
      ]),
    );
  }
}
