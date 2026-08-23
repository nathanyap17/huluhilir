/// Tells the farmer, in plain terms, whether their phone has a barometer —
/// and what that costs them.
///
/// The tier was always *detected* correctly and stored on the farm, but
/// nothing ever said so, which made the two very different setup experiences
/// look like the same flow behaving inconsistently. The detection stays
/// silent and automatic (docs/PROJECT_SPEC.md §4 — the farmer is never asked
/// and never chooses); this only reports the result.
///
/// The honest framing matters: a phone without a barometer is not broken, it
/// just means the farmer answers the elevation questions themselves. And
/// there are more of them than people expect — C(n,2), so 6 blocks is 15
/// comparisons — which is worth saying up front rather than discovering
/// halfway through.
library;

import 'package:flutter/material.dart';

import 'theme.dart';

class TierBanner extends StatelessWidget {
  final bool available;

  /// When set, the banner also states how many comparison questions the walk
  /// will end with — only meaningful on the minimal path.
  final int? blockCount;

  const TierBanner({super.key, required this.available, this.blockCount});

  /// C(n, 2). The whole reason the barometer path is worth having.
  static int pairwiseQuestions(int n) => n < 2 ? 0 : (n * (n - 1)) ~/ 2;

  @override
  Widget build(BuildContext context) {
    final n = blockCount ?? 0;
    final questions = pairwiseQuestions(n);

    final title = available ? 'Barometer dikesan' : 'Tiada barometer';
    final body = available
        ? 'Telefon anda boleh mengesan beza ketinggian sendiri. Ketinggian direkod '
            'sepanjang anda berjalan, jadi soalan arah air hanya ditanya bila perlu.'
        : n >= 2
            ? 'Telefon anda tiada sensor ketinggian. Selepas berjalan, anda akan '
                'ditanya $questions soalan perbandingan ($n blok) untuk menentukan arah air.'
            : 'Telefon anda tiada sensor ketinggian. Selepas berjalan, anda akan '
                'ditanya beberapa soalan perbandingan untuk menentukan arah air.';

    final accent = available ? AppColors.olive : AppColors.terracotta;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: accent.withValues(alpha: 0.28)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(available ? Icons.terrain : Icons.help_outline, size: 20, color: accent),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(title,
                  style: AppText.sans(size: 13, weight: FontWeight.w700, color: accent)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(available ? 'OPTIMISED' : 'MINIMAL',
                    style: AppText.sans(size: 9, weight: FontWeight.w700, color: accent)),
              ),
            ]),
            const SizedBox(height: 5),
            Text(body, style: AppText.sans(size: 12, color: AppColors.charcoal)),
          ]),
        ),
      ]),
    );
  }
}

/// Compact live altitude readout for the walk screen.
///
/// Relative to the pressure baseline captured before walking — never an
/// absolute altitude, which a phone barometer cannot honestly claim.
class AltitudeReadout extends StatelessWidget {
  final double? relativeM;
  const AltitudeReadout({super.key, required this.relativeM});

  @override
  Widget build(BuildContext context) {
    final has = relativeM != null;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(has ? Icons.height : Icons.height_outlined,
          size: 16, color: has ? AppColors.olive : AppColors.oliveLight),
      const SizedBox(width: 6),
      Text(
        has ? '${relativeM! >= 0 ? '+' : ''}${relativeM!.toStringAsFixed(1)} m' : '— m',
        style: AppText.sans(
          size: 13,
          weight: FontWeight.w600,
          color: has ? AppColors.olive : AppColors.oliveLight,
        ),
      ),
      const SizedBox(width: 4),
      Text('dari mula', style: AppText.sans(size: 10, color: AppColors.oliveLight)),
    ]);
  }
}
