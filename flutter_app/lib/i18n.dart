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

  'diag.title': 'Diagnosis',
  'diag.part': 'Bahagian yang difoto:',
  'diag.collar': 'Pangkal',
  'diag.leaf': 'Daun',
  'diag.take': 'Ambil',
  'diag.add': 'Tambah',
  'diag.useAnyway': 'Guna juga',
  'diag.rejected': 'gambar ditolak',
  'diag.retakePlease': 'Sila ambil semula.',
  'diag.lowConf': 'keyakinan rendah — periksa sendiri',
  'diag.acceptedAfter': 'diterima selepas beberapa cubaan',
  'diag.attempt': 'cubaan',
  'diag.more': 'lagi',
  'diag.runAgent': 'DAPATKAN CADANGAN',
  'diag.noBlocks': 'Belum ada blok direkod',

  'walk.title': 'Jalan Ladang',
  'walk.instruction': 'Jalan ke setiap blok lada anda.',
  'walk.waitingGps': 'Menunggu GPS...',
  'walk.gpsAccuracy': 'Ketepatan GPS',
  'walk.markBlock': 'TANDA BLOK',
  'walk.finish': 'SELESAI',
  'walk.offline': 'Luar talian',
  'walk.samplesSaved': 'sampel disimpan',

  'error.title': 'Ralat',
  'error.noFarm': 'Tiada ladang',
  'error.sendFailed': 'Gagal hantar',

  'reg.yourName': 'Nama anda',
  'reg.district': 'Daerah',
  'reg.farmName': 'Nama ladang',
  'reg.start': 'MULA',
  'reg.viewDemo': 'Lihat ladang demo',
  'reg.noDemo': 'Ladang demo tiada pada pelayan.',
  'reg.noServer': 'Tidak dapat sambung ke pelayan. Semak WiFi dan cuba lagi.',
  'reg.defaultName': 'Petani',

  'walk.waitingSignal': 'Menunggu isyarat GPS...',
  'walk.blockNameOptional': 'Nama blok (pilihan)',
  'walk.takePhoto': 'AMBIL GAMBAR',
  'walk.photoTaken': 'Gambar diambil',
  'walk.recordName': 'RAKAM NAMA (pilihan)',
  'walk.stopRecording': 'BERHENTI RAKAM',
  'walk.recordingSaved': 'Rakaman disimpan',
  'walk.drainage': 'Keadaan saliran:',
  'walk.drainGood': 'Baik',
  'walk.drainFair': 'Sederhana',
  'walk.drainPoor': 'Lemah',
  'walk.saveBlock': 'SIMPAN BLOK',
  'walk.blockDefault': 'Blok',
  'walk.saveFailed': 'Gagal simpan blok',
  'walk.pendingSamples': 'sampel menunggu',
  'walk.trace': 'Jejak',

  'elev.title': 'Arah Air',
  'elev.question': 'Jika hujan lebat, air mengalir dari blok mana ke blok mana?',
  'elev.final': 'Jawapan anda adalah muktamad — sistem tidak akan menggantikannya.',
  'elev.blockA': 'Blok A',
  'elev.blockB': 'Blok B',

  'tanya.title': 'TANYA',
  'tanya.disclaimer': 'Penerangan sahaja — dos dan masa semburan datang dari cadangan rasmi.',
  'tanya.examples': 'Contoh soalan:',
  'tanya.placeholder': 'Tanya sesuatu…',
  'tanya.noInfo': 'Tiada maklumat.',
  'tanya.q1': 'Apa punca penyakit busuk pangkal?',
  'tanya.q2': 'Kenapa hujan penting untuk semburan?',
  'tanya.q3': 'Bagaimana air membawa penyakit ke bawah?',

  'derived.title': 'Peta Ladang Siap',
  'derived.auto': 'AUTOMATIK',
  'derived.headline': 'Kami sudah tahu arah air ladang anda.',
  'derived.body': 'Barometer telefon anda merekod ketinggian sepanjang anda berjalan. Susunan blok dari hulu ke hilir dikira sendiri — anda tidak perlu menjawab satu soalan pun.',
  'derived.blocks': 'blok',
  'derived.drop': 'beza tinggi',
  'derived.paths': 'laluan air',
  'derived.order': 'HULU → HILIR',
  'derived.continue': 'TERUSKAN',
  'derived.down': 'turun',

  'legend.harmed': 'Terjejas',
  'legend.atRisk': 'Berisiko',
  'legend.safe': 'Selamat',
  'legend.flow': 'Aliran hiliran',

  'tier.detected': 'Barometer dikesan',
  'tier.browser': 'Barometer tidak boleh dibaca di pelayar',
  'tier.none': 'Tiada barometer',
  'tier.retry': 'Cuba kesan semula',
  'tier.fromStart': 'dari mula',
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

  'diag.title': 'Diagnosis',
  'diag.part': 'Part photographed:',
  'diag.collar': 'Collar',
  'diag.leaf': 'Leaf',
  'diag.take': 'Take',
  'diag.add': 'Add',
  'diag.useAnyway': 'Use anyway',
  'diag.rejected': 'photo rejected',
  'diag.retakePlease': 'Please take another photo.',
  'diag.lowConf': 'low confidence — inspect it yourself',
  'diag.acceptedAfter': 'accepted after several attempts',
  'diag.attempt': 'attempt',
  'diag.more': 'left',
  'diag.runAgent': 'GET RECOMMENDATION',
  'diag.noBlocks': 'No blocks recorded yet',

  'walk.title': 'Walk the Farm',
  'walk.instruction': 'Walk to each of your pepper blocks.',
  'walk.waitingGps': 'Waiting for GPS...',
  'walk.gpsAccuracy': 'GPS accuracy',
  'walk.markBlock': 'MARK BLOCK',
  'walk.finish': 'DONE',
  'walk.offline': 'Offline',
  'walk.samplesSaved': 'samples saved',

  'error.title': 'Error',
  'error.noFarm': 'No farm',
  'error.sendFailed': 'Could not send',

  'reg.yourName': 'Your name',
  'reg.district': 'District',
  'reg.farmName': 'Farm name',
  'reg.start': 'START',
  'reg.viewDemo': 'View the demo farm',
  'reg.noDemo': 'No demo farm on the server.',
  'reg.noServer': 'Cannot reach the server. Check WiFi and try again.',
  'reg.defaultName': 'Farmer',

  'walk.waitingSignal': 'Waiting for a GPS signal...',
  'walk.blockNameOptional': 'Block name (optional)',
  'walk.takePhoto': 'TAKE PHOTO',
  'walk.photoTaken': 'Photo taken',
  'walk.recordName': 'RECORD NAME (optional)',
  'walk.stopRecording': 'STOP RECORDING',
  'walk.recordingSaved': 'Recording saved',
  'walk.drainage': 'Drainage:',
  'walk.drainGood': 'Good',
  'walk.drainFair': 'Fair',
  'walk.drainPoor': 'Poor',
  'walk.saveBlock': 'SAVE BLOCK',
  'walk.blockDefault': 'Block',
  'walk.saveFailed': 'Could not save block',
  'walk.pendingSamples': 'samples pending',
  'walk.trace': 'Trace',

  'elev.title': 'Water Direction',
  'elev.question': 'In heavy rain, which block does water flow from, and to?',
  'elev.final': 'Your answer is final — the system will not override it.',
  'elev.blockA': 'Block A',
  'elev.blockB': 'Block B',

  'tanya.title': 'ASK',
  'tanya.disclaimer': 'Explanation only — dose and spray timing come from the official recommendation.',
  'tanya.examples': 'Example questions:',
  'tanya.placeholder': 'Ask something…',
  'tanya.noInfo': 'No information.',
  'tanya.q1': 'What causes foot rot?',
  'tanya.q2': 'Why does rain matter for spraying?',
  'tanya.q3': 'How does water carry the disease downhill?',

  'derived.title': 'Farm Map Ready',
  'derived.auto': 'AUTOMATIC',
  'derived.headline': 'We already know how water moves across your farm.',
  'derived.body': 'Your phone barometer recorded altitude as you walked. The order of blocks from upstream to downstream was worked out on its own — you did not have to answer a single question.',
  'derived.blocks': 'blocks',
  'derived.drop': 'height range',
  'derived.paths': 'water paths',
  'derived.order': 'UPSTREAM → DOWNSTREAM',
  'derived.continue': 'CONTINUE',
  'derived.down': 'down',

  'legend.harmed': 'Harmed',
  'legend.atRisk': 'At risk',
  'legend.safe': 'Safe',
  'legend.flow': 'Downhill flow',

  'tier.detected': 'Barometer detected',
  'tier.browser': 'A browser cannot read the barometer',
  'tier.none': 'No barometer',
  'tier.retry': 'Try detecting again',
  'tier.fromStart': 'from start',
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
