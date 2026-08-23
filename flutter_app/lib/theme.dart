import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Design language: warm, organic, and legible in field sunlight -- large
/// touch targets, big soft radii, high-contrast text. Literacy is not
/// assumed (huluhilir-rules skill §8), so weight and colour carry meaning
/// alongside text, never instead of it.
///
/// Typography note: google_fonts fetches Playfair Display / Inter over the
/// network on first use and caches them afterward. That's an acceptable
/// tradeoff here -- the app already needs connectivity for every screen that
/// matters (backend calls, the agent) -- but it does mean the very first
/// launch on a booth demo should happen with the hotspot already up.
class AppColors {
  static const cream = Color(0xFFF5F2ED);
  static const charcoal = Color(0xFF2D2D2D);
  static const olive = Color(0xFF5A5A40);
  static const oliveLight = Color(0xFF8A8A70);
  static const terracotta = Color(0xFFCC7A5C);
  static const hairline = Color(0xFFE5E2DD);
  static const cardOffWhite = Color(0xFFF5F5F0);

  // Block/risk states -- kept distinct from the brand palette on purpose so
  // "harmed" reads as alarm-red-adjacent even to a viewer who can't read the
  // label (huluhilir-rules skill §8).
  static const stateProtected = olive;
  static const stateAlerted = Color(0xFFD9A441);
  static const stateHarmed = terracotta;
  static const stateOverrun = Color(0xFF8B3A2B);
}

class AppRadius {
  static const card = 32.0;
  static const button = 16.0;
  static const chip = 50.0;
}

class AppText {
  static TextStyle serif({
    required double size,
    FontWeight weight = FontWeight.w400,
    Color color = AppColors.charcoal,
    double? height,
    bool italic = false,
  }) =>
      GoogleFonts.playfairDisplay(
        fontSize: size,
        fontWeight: weight,
        color: color,
        height: height,
        fontStyle: italic ? FontStyle.italic : FontStyle.normal,
      );

  static TextStyle sans({
    double size = 14,
    FontWeight weight = FontWeight.w500,
    Color color = AppColors.charcoal,
    double? letterSpacing,
    double? height,
  }) =>
      GoogleFonts.inter(
        fontSize: size,
        fontWeight: weight,
        color: color,
        letterSpacing: letterSpacing,
        height: height,
      );

  /// The "RAIN PULSE" / "ADVISOR" / "TINDAKAN UTAMA" small-caps eyebrow label
  /// used at the top of every dashboard card.
  static TextStyle eyebrow({Color color = AppColors.oliveLight}) => sans(
        size: 12,
        weight: FontWeight.w700,
        color: color,
        letterSpacing: 1.6,
      );
}

ThemeData buildAppTheme() {
  final base = ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.cream,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.olive,
      surface: AppColors.cream,
    ),
  );

  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: AppColors.charcoal,
      displayColor: AppColors.charcoal,
      fontFamily: GoogleFonts.inter().fontFamily,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.cream,
      surfaceTintColor: AppColors.cream,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: AppText.serif(size: 28, weight: FontWeight.bold, color: AppColors.olive),
      iconTheme: const IconThemeData(color: AppColors.olive),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.olive,
        foregroundColor: Colors.white,
        textStyle: AppText.sans(weight: FontWeight.w700, size: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.button)),
        padding: const EdgeInsets.symmetric(vertical: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.olive,
        side: const BorderSide(color: AppColors.hairline, width: 1.5),
        textStyle: AppText.sans(weight: FontWeight.w700, size: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.button)),
        padding: const EdgeInsets.symmetric(vertical: 16),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      labelStyle: AppText.sans(color: AppColors.oliveLight),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.button),
        borderSide: const BorderSide(color: AppColors.hairline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.button),
        borderSide: const BorderSide(color: AppColors.hairline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.button),
        borderSide: const BorderSide(color: AppColors.olive, width: 2),
      ),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.card),
        side: const BorderSide(color: AppColors.hairline),
      ),
    ),
  );
}

/// Shared drop shadow for cards that sit on the flat cream background --
/// CardTheme alone doesn't give the soft elevation the design calls for.
List<BoxShadow> softShadow({Color tint = const Color(0x14000000)}) => [
      BoxShadow(color: tint, blurRadius: 24, offset: const Offset(0, 8)),
    ];
