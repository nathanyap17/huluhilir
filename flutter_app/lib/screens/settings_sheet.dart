/// Settings. Previously the gear icon only showed a snackbar telling the
/// farmer to long-press it, which is not a setting — it is a hint about a
/// hidden gesture.
///
/// Reset stays behind a confirmation *and* keeps its long-press shortcut:
/// wiping a farm means re-walking the whole garden, and nothing in this sheet
/// should be one mis-tap away from that (docs/PROJECT_SPEC.md §7 "hide
/// reset").
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme.dart';
import 'tanya_sheet.dart';

class SettingsSheet extends ConsumerStatefulWidget {
  const SettingsSheet({super.key});

  @override
  ConsumerState<SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends ConsumerState<SettingsSheet> {
  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final farm = session.farm;
    final notify = ref.watch(rainAlertsEnabledProvider);

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.cream,
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.card)),
      ),
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Row(children: [
          Text('TETAPAN', style: AppText.eyebrow()),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.close, color: AppColors.olive),
            onPressed: () => Navigator.pop(context),
          ),
        ]),
        if (farm != null) ...[
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              '${farm.name} · ${farm.elevationTier == 'optimised' ? 'Barometer dikesan' : 'Tiada barometer'}',
              style: AppText.sans(size: 12, color: AppColors.oliveLight),
            ),
          ),
          const SizedBox(height: 18),
        ],

        _Row(
          icon: Icons.chat_bubble_outline,
          title: 'Tanya',
          subtitle: 'Soalan tentang penyakit dan parit',
          onTap: () {
            Navigator.pop(context);
            showModalBottomSheet(
              context: context,
              isScrollControlled: true,
              backgroundColor: Colors.transparent,
              builder: (_) => const TanyaSheet(),
            );
          },
        ),

        // Local-only preference. It gates whether the dashboard surfaces a
        // rain-pulse prompt; it does NOT subscribe to push, and nothing here
        // messages a neighbour -- neighbour alerts stay drafted and
        // farmer-approved (huluhilir-rules §5).
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: notify,
          activeThumbColor: AppColors.olive,
          onChanged: (v) => ref.read(rainAlertsEnabledProvider.notifier).set(v),
          title: Text('Peringatan hujan',
              style: AppText.sans(size: 15, weight: FontWeight.w600, color: AppColors.charcoal)),
          subtitle: Text('Papar amaran bila hujan lebat dijangka',
              style: AppText.sans(size: 12, color: AppColors.oliveLight)),
          secondary: const Icon(Icons.notifications_outlined, color: AppColors.olive),
        ),

        const Divider(color: AppColors.hairline, height: 28),

        _Row(
          icon: Icons.logout,
          title: 'Log keluar',
          subtitle: 'Ladang kekal di pelayan — anda boleh masuk semula',
          onTap: () async {
            final ok = await _confirm(
              context,
              title: 'Log keluar?',
              body: 'Ladang anda kekal disimpan. Anda perlu daftar semula pada telefon ini '
                  'untuk membukanya.',
              confirmLabel: 'LOG KELUAR',
            );
            if (ok != true || !context.mounted) return;
            await ref.read(sessionProvider.notifier).signOut();
            if (context.mounted) Navigator.pop(context);
          },
        ),

        _Row(
          icon: Icons.restart_alt,
          title: 'Tetapkan semula ladang',
          subtitle: 'Padam sesi tempatan dan mula semula',
          danger: true,
          onTap: () async {
            final ok = await _confirm(
              context,
              title: 'Tetapkan semula?',
              body: 'Anda perlu berjalan dan menanda semula setiap blok. '
                  'Tindakan ini tidak boleh dibatalkan pada telefon ini.',
              confirmLabel: 'TETAPKAN SEMULA',
              danger: true,
            );
            if (ok != true || !context.mounted) return;
            await ref.read(sessionProvider.notifier).reset();
            if (context.mounted) Navigator.pop(context);
          },
        ),
      ]),
    );
  }
}

Future<bool?> _confirm(
  BuildContext context, {
  required String title,
  required String body,
  required String confirmLabel,
  bool danger = false,
}) {
  return showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      backgroundColor: AppColors.cream,
      title: Text(title, style: AppText.serif(size: 20, weight: FontWeight.w600)),
      content: Text(body, style: AppText.sans(size: 14, color: AppColors.charcoal)),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('BATAL'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: danger ? AppColors.terracotta : AppColors.olive,
          ),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool danger;

  const _Row({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.danger = false,
  });

  @override
  Widget build(BuildContext context) {
    final colour = danger ? AppColors.terracotta : AppColors.olive;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon, color: colour),
      title: Text(title,
          style: AppText.sans(size: 15, weight: FontWeight.w600, color: AppColors.charcoal)),
      subtitle: Text(subtitle, style: AppText.sans(size: 12, color: AppColors.oliveLight)),
      onTap: onTap,
    );
  }
}
