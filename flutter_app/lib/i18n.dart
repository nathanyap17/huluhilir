/// English ⇄ Malay switching for the interface.
///
/// Malay is the default and stays the default: the farmers this is built for
/// read Bahasa Malaysia, and English is here for judges, extension officers,
/// and anyone reviewing the app — not as the primary experience.
///
/// **Iban is deliberately not a UI language here.** It is offered for
/// *speech* on the priority action (see `speech.dart`), because that is where
/// it matters and where a native-speaker-verified phrasing exists. Machine-
/// translating the whole interface into Iban would produce text no Iban
/// speaker vouched for, which is worse than not offering it — and voice, not
/// text, is how the app is meant to reach an Iban speaker anyway
/// (huluhilir-rules §7).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum AppLang { ms, en }

class LangNotifier extends StateNotifier<AppLang> {
  LangNotifier() : super(AppLang.ms) {
    _restore();
  }

  static const _key = 'huluhilir.ui_lang';

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_key);
    if (mounted && v == 'en') state = AppLang.en;
  }

  Future<void> set(AppLang lang) async {
    state = lang;
    (await SharedPreferences.getInstance()).setString(_key, lang.name);
  }

  Future<void> toggle() => set(state == AppLang.ms ? AppLang.en : AppLang.ms);
}

final langProvider = StateNotifierProvider<LangNotifier, AppLang>((ref) => LangNotifier());

/// Look up a UI string. Falls back to the Malay text when an English
/// translation is missing, rather than showing a bare key — a farmer seeing
/// Malay in an English session is a cosmetic gap; a screen full of
/// `dashboard.title` is a broken app.
String tr(WidgetRef ref, String key) {
  final lang = ref.watch(langProvider);
  final table = lang == AppLang.en ? _en : _ms;
  return table[key] ?? _ms[key] ?? key;
}

/// Non-reactive variant for call sites without a WidgetRef (dialogs, helpers).
String trFor(AppLang lang, String key) {
  final table = lang == AppLang.en ? _en : _ms;
  return table[key] ?? _ms[key] ?? key;
}

const _ms = <String, String>{
  'app.tagline': 'Dari hulu ke hilir — sebelum penyakit sampai.',

  'dash.rainPulse': 'DENYUT HUJAN',
  'dash.advisor': 'ADVISOR',
  'dash.startDiagnosis': 'MULA DIAGNOSIS',
  'dash.terrain': 'TERRAIN RISK MODEL',
  'dash.terrainNote': 'Anggaran sahaja — bukan ukuran lapangan.',
  'dash.priorityAction': 'TINDAKAN UTAMA',
  'dash.listen': 'Dengar',
  'dash.retry': 'CUBA LAGI',
  'dash.daysAway': 'hari lagi',

  'action.why': 'Kenapa tindakan ini?',
  'action.blueprint': 'CARA KEPUTUSAN DIBUAT',
  'action.deferred': 'Ditangguh',
  'action.doAt': 'Buat pada',

  'settings.title': 'TETAPAN',
  'settings.language': 'Bahasa',
  'settings.ask': 'Tanya',
  'settings.askSub': 'Soalan tentang penyakit dan parit',
  'settings.rainAlerts': 'Peringatan hujan',
  'settings.rainAlertsSub': 'Papar amaran bila hujan lebat dijangka',
  'settings.logout': 'Log keluar',
  'settings.logoutSub': 'Ladang kekal di pelayan — anda boleh masuk semula',
  'settings.reset': 'Tetapkan semula ladang',
  'settings.resetSub': 'Padam sesi tempatan dan mula semula',
  'common.cancel': 'BATAL',
  'common.close': 'Tutup',

  'block.drainage': 'Saliran',
  'block.vines': 'pokok',
  'block.history': 'SEJARAH',
  'block.noPhotos': 'Belum ada gambar untuk blok ini.',
  'block.playLabel': 'Dengar nama blok',
  'block.lowConfidence': 'Keyakinan rendah — periksa sendiri',
  'block.historyFailed': 'Sejarah tidak dapat dimuatkan.',
};

const _en = <String, String>{
  'app.tagline': 'From upstream to downstream — before the disease arrives.',

  'dash.rainPulse': 'RAIN PULSE',
  'dash.advisor': 'ADVISOR',
  'dash.startDiagnosis': 'START DIAGNOSIS',
  'dash.terrain': 'TERRAIN RISK MODEL',
  'dash.terrainNote': 'Estimate only — not a field measurement.',
  'dash.priorityAction': 'PRIORITY ACTION',
  'dash.listen': 'Listen',
  'dash.retry': 'TRY AGAIN',
  'dash.daysAway': 'days away',

  'action.why': 'Why this action?',
  'action.blueprint': 'HOW THIS WAS DECIDED',
  'action.deferred': 'Deferred',
  'action.doAt': 'Do at',

  'settings.title': 'SETTINGS',
  'settings.language': 'Language',
  'settings.ask': 'Ask',
  'settings.askSub': 'Questions about disease and drainage',
  'settings.rainAlerts': 'Rain alerts',
  'settings.rainAlertsSub': 'Show a warning when heavy rain is expected',
  'settings.logout': 'Log out',
  'settings.logoutSub': 'Your farm stays on the server — you can sign back in',
  'settings.reset': 'Reset farm',
  'settings.resetSub': 'Clear the local session and start over',
  'common.cancel': 'CANCEL',
  'common.close': 'Close',

  'block.drainage': 'Drainage',
  'block.vines': 'vines',
  'block.history': 'HISTORY',
  'block.noPhotos': 'No photographs for this block yet.',
  'block.playLabel': 'Play block name',
  'block.lowConfidence': 'Low confidence — inspect it yourself',
  'block.historyFailed': 'Could not load history.',
};

/// The six diagnosis classes, in both languages. The Malay terms are the ones
/// used in the classifier's own class table, kept identical so a spoken
/// diagnosis and a written one never disagree.
const classLabels = <String, Map<AppLang, String>>{
  'healthy_leaf': {AppLang.ms: 'SIHAT (DAUN)', AppLang.en: 'HEALTHY (LEAF)'},
  'healthy_collar': {AppLang.ms: 'SIHAT (PANGKAL)', AppLang.en: 'HEALTHY (COLLAR)'},
  'foliar_yellowing': {AppLang.ms: 'DAUN MENGUNING', AppLang.en: 'LEAF YELLOWING'},
  'collar_lesion': {AppLang.ms: 'LESI PANGKAL', AppLang.en: 'COLLAR LESION'},
  'defoliation_wilt': {AppLang.ms: 'GUGUR DAUN / LAYU', AppLang.en: 'DEFOLIATION / WILT'},
  'unrelated': {AppLang.ms: 'TIADA KAITAN', AppLang.en: 'NOT RELEVANT'},
};

String classLabel(String cls, AppLang lang) =>
    classLabels[cls]?[lang] ?? classLabels[cls]?[AppLang.ms] ?? cls;

/// Compact language switch for headers.
class LangToggle extends ConsumerWidget {
  const LangToggle({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(langProvider);
    return TextButton(
      onPressed: () => ref.read(langProvider.notifier).toggle(),
      style: TextButton.styleFrom(
        minimumSize: const Size(44, 44),
        padding: const EdgeInsets.symmetric(horizontal: 10),
      ),
      child: Text(
        lang == AppLang.ms ? 'BM · EN' : 'EN · BM',
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
      ),
    );
  }
}
