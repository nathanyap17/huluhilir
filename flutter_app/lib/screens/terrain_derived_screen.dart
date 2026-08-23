/// Shown after the walk when the slope was worked out **without asking the
/// farmer anything**.
///
/// On an OPTIMISED-tier phone the barometer separates every block, so
/// `pairs_needing_farmer_input` returns nothing and the app used to silently
/// submit and jump to the dashboard. The farmer saw a spinner. The single
/// most impressive thing the system does — reconstructing an entire slope
/// from sensor readings taken while they walked — was invisible to the
/// person it was done for.
///
/// This does not ask for confirmation and has no "correct this" control.
/// That is deliberate: the ordering came from the sensor, and the farmer
/// overriding it belongs in the elevation questions (which is exactly what
/// the MINIMAL path is), not in a screen that would invite second-guessing
/// a measurement they were never asked to make. huluhilir-rules §3 still
/// holds — a farmer's answer beats the sensor — but the place to give that
/// answer is the question flow, not here.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../brand.dart';
import '../theme.dart';
import 'dashboard_screen.dart';

class TerrainDerivedScreen extends ConsumerWidget {
  /// The `blocks` array from /resolve-elevation, already ordered hulu → hilir.
  final List<Map<String, dynamic>> blocks;
  final int edgesCreated;

  const TerrainDerivedScreen({
    super.key,
    required this.blocks,
    required this.edgesCreated,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final totalFall = _totalFall();

    return Scaffold(
      backgroundColor: AppColors.cream,
      appBar: AppBar(
        title: const Text('Peta Ladang Siap'),
        actions: const [BrandLogoAction()],
        automaticallyImplyLeading: false,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('AUTOMATIK', style: AppText.eyebrow()),
          const SizedBox(height: 8),
          Text(
            'Kami sudah tahu arah air ladang anda.',
            style: AppText.serif(size: 27, weight: FontWeight.w600, color: AppColors.olive),
          ),
          const SizedBox(height: 12),
          Text(
            'Barometer telefon anda merekod ketinggian sepanjang anda berjalan. '
            'Susunan blok dari hulu ke hilir dikira sendiri — anda tidak perlu '
            'menjawab satu soalan pun.',
            style: AppText.sans(size: 14, color: AppColors.charcoal),
          ),
          const SizedBox(height: 20),

          Row(children: [
            _Stat(value: '${blocks.length}', label: 'blok'),
            const SizedBox(width: 12),
            _Stat(
              value: totalFall == null ? '—' : '${totalFall.toStringAsFixed(1)} m',
              label: 'beza tinggi',
            ),
            const SizedBox(width: 12),
            _Stat(value: '$edgesCreated', label: 'laluan air'),
          ]),

          const SizedBox(height: 24),
          Text('HULU → HILIR', style: AppText.eyebrow()),
          const SizedBox(height: 10),

          for (var i = 0; i < blocks.length; i++) _Step(row: blocks[i], isFirst: i == 0),

          const SizedBox(height: 12),
          Text(
            'Anggaran sahaja — bukan ukuran lapangan.',
            style: AppText.sans(size: 11, color: AppColors.oliveLight)
                .copyWith(fontStyle: FontStyle.italic),
          ),
          const SizedBox(height: 28),
          FilledButton(
            onPressed: () => Navigator.of(context).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const DashboardScreen()),
              (route) => false,
            ),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
            child: const Text('TERUSKAN', style: TextStyle(fontSize: 17)),
          ),
        ],
      ),
    );
  }

  /// Fall from the highest block to the lowest, when the sensor gave a
  /// reading for both ends.
  double? _totalFall() {
    final values = blocks
        .map((b) => b['baro_rel_m'])
        .whereType<num>()
        .map((n) => n.toDouble())
        .toList();
    if (values.length < 2) return null;
    return values.reduce((a, b) => a > b ? a : b) - values.reduce((a, b) => a < b ? a : b);
  }
}

class _Stat extends StatelessWidget {
  final String value;
  final String label;
  const _Stat({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.hairline),
        ),
        child: Column(children: [
          Text(value,
              style: AppText.serif(size: 22, weight: FontWeight.bold, color: AppColors.terracotta)),
          const SizedBox(height: 2),
          Text(label, style: AppText.sans(size: 11, color: AppColors.oliveLight)),
        ]),
      ),
    );
  }
}

class _Step extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool isFirst;
  const _Step({required this.row, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    final drop = row['drop_from_above_m'] as num?;
    final baro = row['baro_rel_m'] as num?;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (!isFirst)
        Padding(
          padding: const EdgeInsets.only(left: 17),
          child: Row(children: [
            Container(width: 2, height: 26, color: AppColors.hairline),
            const SizedBox(width: 10),
            Icon(Icons.south, size: 13, color: AppColors.oliveLight),
            const SizedBox(width: 4),
            Text(
              drop == null ? 'ke bawah' : 'turun ${drop.abs().toStringAsFixed(1)} m',
              style: AppText.sans(size: 11, color: AppColors.oliveLight),
            ),
          ]),
        ),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.hairline),
        ),
        child: Row(children: [
          Container(
            width: 30,
            height: 30,
            decoration: const BoxDecoration(color: AppColors.olive, shape: BoxShape.circle),
            alignment: Alignment.center,
            child: Text('${row['elevation_rank']}',
                style: AppText.sans(size: 13, weight: FontWeight.w700, color: Colors.white)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text('${row['label']}',
                style: AppText.sans(size: 15, weight: FontWeight.w600)),
          ),
          if (baro != null)
            Text('${baro >= 0 ? '+' : ''}${baro.toStringAsFixed(1)} m',
                style: AppText.sans(size: 12, color: AppColors.oliveLight)),
        ]),
      ),
    ]);
  }
}
