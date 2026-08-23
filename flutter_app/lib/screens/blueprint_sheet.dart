/// "How this was decided" — the arbitration, made visible.
///
/// Every step shown here was **recorded while the decision was being made**,
/// from `agent_runs.tools_called`. Nothing is re-inferred and nothing is
/// narrated by a model after the fact: a blueprint that asked an LLM to
/// explain the decision afterwards would be a plausible story *about* the
/// decision rather than the decision itself, and the two come apart exactly
/// when it matters most.
///
/// The deferral row is the point of the whole product. It reports the cause
/// stored on the recommendation, which the backend reconciles against the
/// real `find_spray_window` result rather than trusting the model's account
/// of its own reasoning.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../providers.dart';
import '../theme.dart';

final blueprintProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, recId) async {
  return ref.watch(apiClientProvider).recommendationBlueprint(recId);
});

class BlueprintSheet extends ConsumerWidget {
  final String recommendationId;
  const BlueprintSheet({super.key, required this.recommendationId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(blueprintProvider(recommendationId));

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      builder: (context, scrollController) => Container(
        decoration: const BoxDecoration(
          color: AppColors.cream,
          borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.card)),
        ),
        padding: const EdgeInsets.fromLTRB(24, 18, 24, 24),
        child: Column(children: [
          Row(children: [
            Text(tr(ref, 'action.blueprint'), style: AppText.eyebrow()),
            const Spacer(),
            IconButton(
              icon: const Icon(Icons.close, color: AppColors.olive),
              tooltip: tr(ref, 'common.close'),
              onPressed: () => Navigator.pop(context),
            ),
          ]),
          Expanded(
            child: data.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: Text('$e', style: AppText.sans(size: 12, color: AppColors.terracotta)),
              ),
              data: (d) => _Body(d: d, controller: scrollController),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  final Map<String, dynamic> d;
  final ScrollController controller;
  const _Body({required this.d, required this.controller});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final steps = ((d['steps'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final deferral = d['deferral'] as Map<String, dynamic>?;
    final run = d['run'] as Map<String, dynamic>?;

    return ListView(controller: controller, children: [
      // The outcome first: what the farmer is being asked to do.
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: AppColors.olive,
          borderRadius: BorderRadius.circular(AppRadius.card),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${d['block_label'] ?? ''} · ${d['action_type'] ?? ''}',
              style: AppText.sans(size: 11, color: Colors.white.withValues(alpha: 0.7))),
          const SizedBox(height: 8),
          Text('${d['reason_ms'] ?? ''}',
              style: AppText.serif(size: 19, weight: FontWeight.w600, color: Colors.white)),
        ]),
      ),

      // The arbitration. Shown before the steps because it is the answer to
      // "why not just spray now", which is the question a farmer actually has.
      if (deferral != null) ...[
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.terracotta.withValues(alpha: 0.09),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.terracotta.withValues(alpha: 0.3)),
          ),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.schedule, size: 18, color: AppColors.terracotta),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr(ref, 'action.deferred'),
                    style: AppText.sans(
                        size: 12, weight: FontWeight.w700, color: AppColors.terracotta)),
                const SizedBox(height: 4),
                Text(
                  _deferText(deferral),
                  style: AppText.sans(size: 12.5, color: AppColors.charcoal),
                ),
              ]),
            ),
          ]),
        ),
      ],

      const SizedBox(height: 20),
      Text('LANGKAH', style: AppText.eyebrow()),
      const SizedBox(height: 4),
      Text(
        '${d['steps_note'] ?? ''}',
        style: AppText.sans(size: 11, color: AppColors.oliveLight)
            .copyWith(fontStyle: FontStyle.italic),
      ),
      const SizedBox(height: 12),

      if (steps.isEmpty)
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.hairline),
          ),
          // Distinguished from a load failure on purpose.
          child: Text(
            'Tiada panggilan alat direkod untuk keputusan ini.',
            style: AppText.sans(size: 12, color: AppColors.oliveLight),
          ),
        )
      else
        for (var i = 0; i < steps.length; i++) _Step(step: steps[i], index: i + 1),

      if (run != null) ...[
        const SizedBox(height: 18),
        Text(
          'Model: ${run['llm_model']} · ${run['trigger']} · ${run['status']}',
          style: AppText.sans(size: 10, color: AppColors.oliveLight),
        ),
      ],
      const SizedBox(height: 20),
    ]);
  }

  String _deferText(Map<String, dynamic> deferral) {
    final cause = deferral['defer_cause'];
    switch (cause) {
      case 'rain_forecast':
        return 'Semburan ditangguh kerana hujan lebat dijangka sebelum racun sempat melekat. '
            'Kerja parit didahulukan kerana ia tidak dibasuh hujan.';
      case 'no_dry_window':
        return 'Tiada tetingkap kering yang cukup panjang dijumpai dalam ramalan.';
      case 'reentry':
        return 'Ditangguh untuk tempoh selamat masuk semula selepas rawatan.';
      default:
        return 'Ditangguh${cause == null ? '' : ' ($cause)'}.';
    }
  }
}

class _Step extends StatelessWidget {
  final Map<String, dynamic> step;
  final int index;
  const _Step({required this.step, required this.index});

  @override
  Widget build(BuildContext context) {
    final latency = step['latency_ms'];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (index > 1)
        Padding(
          padding: const EdgeInsets.only(left: 15),
          child: Container(width: 2, height: 16, color: AppColors.hairline),
        ),
      Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.hairline),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 26,
            height: 26,
            decoration: const BoxDecoration(color: AppColors.olive, shape: BoxShape.circle),
            alignment: Alignment.center,
            child: Text('$index',
                style: AppText.sans(size: 12, weight: FontWeight.w700, color: Colors.white)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(
                  child: Text('${step['label']}',
                      style: AppText.sans(size: 13.5, weight: FontWeight.w700)),
                ),
                if (latency != null)
                  Text('${latency}ms',
                      style: AppText.sans(size: 10, color: AppColors.oliveLight)),
              ]),
              if ((step['what_for'] as String?)?.isNotEmpty ?? false)
                Text('${step['what_for']}',
                    style: AppText.sans(size: 11.5, color: AppColors.oliveLight)),
              if ((step['result_summary'] as String?)?.isNotEmpty ?? false) ...[
                const SizedBox(height: 6),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.cream,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${step['result_summary']}',
                    style: AppText.sans(size: 10.5, color: AppColors.charcoal),
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ]),
          ),
        ]),
      ),
    ]);
  }
}
