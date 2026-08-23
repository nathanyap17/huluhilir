import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../providers.dart';
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

  Future<Position?> _locate() async {
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return null;
    }
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.best),
    );
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

      final position = await _locate();
      if (position == null) {
        throw Exception('Akses lokasi diperlukan untuk mengesan stesen cuaca berdekatan.');
      }

      final hasBarometer = await ref.read(barometerAvailableProvider.future);

      final user = await api.createUser(
        displayName: _nameController.text.trim().isEmpty ? 'Petani' : _nameController.text.trim(),
        district: _districtController.text.trim(),
      );
      final farm = await api.createFarm(
        userId: user.userId,
        name: _farmNameController.text.trim(),
        lat: position.latitude,
        lon: position.longitude,
        barometerAvailable: hasBarometer,
      );

      final notifier = ref.read(sessionProvider.notifier);
      await notifier.setUser(user);
      await notifier.setFarm(farm);

      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const WalkScreen()),
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
      appBar: AppBar(title: const Text('HuluHilir')),
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
