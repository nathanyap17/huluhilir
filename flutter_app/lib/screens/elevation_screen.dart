import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models.dart';
import '../providers.dart';
import 'dashboard_screen.dart';

/// Step ⑤ of setup: elevation resolution (docs/PROJECT_SPEC.md §5).
///
/// The question is deliberately phrased as **"which way does the water
/// flow?"**, not "which is higher" — farmers reason confidently about water
/// movement on their own land, and that is the signal the spread model
/// actually needs. Whatever they answer becomes authoritative; if a barometer
/// reading disagrees, the backend logs an elevation_conflicts row resolved in
/// the farmer's favour and never overrides them (huluhilir-rules skill §3).
class ElevationScreen extends ConsumerStatefulWidget {
  const ElevationScreen({super.key});

  @override
  ConsumerState<ElevationScreen> createState() => _ElevationScreenState();
}

class _ElevationScreenState extends ConsumerState<ElevationScreen> {
  List<ElevationQuestion> _questions = [];
  final Map<int, String> _answers = {};
  int _index = 0;
  bool _loading = true;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final farm = ref.read(sessionProvider).farm!;
      final questions = await ref.read(apiClientProvider).elevationQuestions(farm.farmId);
      setState(() {
        _questions = questions;
        _loading = false;
      });
      if (questions.isEmpty) await _submit();
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _answer(String choice) {
    _answers[_index] = choice;
    if (_index < _questions.length - 1) {
      setState(() => _index++);
    } else {
      _submit();
    }
  }

  Future<void> _submit() async {
    setState(() => _submitting = true);
    try {
      final farm = ref.read(sessionProvider).farm!;
      final payload = <Map<String, String>>[];
      for (var i = 0; i < _questions.length; i++) {
        payload.add({
          'block_a_id': _questions[i].blockAId,
          'block_b_id': _questions[i].blockBId,
          'answer': _answers[i] ?? 'a_higher',
        });
      }
      await ref.read(apiClientProvider).resolveElevation(farm.farmId, payload);
      // Setup just completed server-side; refresh so isSetupComplete is true
      // and a relaunch routes to the dashboard rather than back into the walk.
      await ref.read(sessionProvider.notifier).refreshFarm();

      if (!mounted) return;
      Navigator.of(context)
          .pushReplacement(MaterialPageRoute(builder: (_) => const DashboardScreen()));
    } catch (e) {
      setState(() {
        _error = e.toString();
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading || _submitting) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Ralat')),
        body: Padding(padding: const EdgeInsets.all(20), child: Text(_error!)),
      );
    }
    if (_questions.isEmpty) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final question = _questions[_index];
    final labelA = question.blockALabel ?? 'Blok A';
    final labelB = question.blockBLabel ?? 'Blok B';

    return Scaffold(
      appBar: AppBar(title: Text('Arah Air (${_index + 1}/${_questions.length})')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(children: [
          LinearProgressIndicator(value: (_index + 1) / _questions.length),
          const SizedBox(height: 32),
          const Icon(Icons.water_drop, size: 56, color: Color(0xFF1565C0)),
          const SizedBox(height: 20),
          const Text(
            'Jika hujan lebat, air mengalir dari blok mana ke blok mana?',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 36),
          _FlowChoice(
            from: labelA,
            to: labelB,
            onTap: () => _answer('a_higher'),
          ),
          const SizedBox(height: 16),
          _FlowChoice(
            from: labelB,
            to: labelA,
            onTap: () => _answer('b_higher'),
          ),
          const Spacer(),
          Text(
            'Jawapan anda adalah muktamad — sistem tidak akan menggantikannya.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
          ),
        ]),
      ),
    );
  }
}

class _FlowChoice extends StatelessWidget {
  final String from;
  final String to;
  final VoidCallback onTap;

  const _FlowChoice({required this.from, required this.to, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 16),
        decoration: BoxDecoration(
          border: Border.all(color: Colors.blue.shade200, width: 2),
          borderRadius: BorderRadius.circular(12),
          color: Colors.blue.shade50,
        ),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Flexible(
            child: Text(from,
                textAlign: TextAlign.end,
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Icon(Icons.arrow_forward, size: 28, color: Color(0xFF1565C0)),
          ),
          Flexible(
            child: Text(to, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
          ),
        ]),
      ),
    );
  }
}
