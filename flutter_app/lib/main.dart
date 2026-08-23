import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers.dart';
import 'screens/dashboard_screen.dart';
import 'screens/registration_screen.dart';
import 'screens/walk_screen.dart';

void main() {
  runApp(const ProviderScope(child: HuluHilirApp()));
}

class HuluHilirApp extends ConsumerWidget {
  const HuluHilirApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);

    return MaterialApp(
      title: 'HuluHilir',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2E7D32)),
        useMaterial3: true,
        // Large touch targets and text: the user may be standing on a slope in
        // sunlight, and literacy is not assumed (huluhilir-rules skill §8).
        textTheme: const TextTheme(
          bodyMedium: TextStyle(fontSize: 16),
          titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
      ),
      home: _home(session),
    );
  }

  Widget _home(SessionState session) {
    // Splash while the persisted session is being restored, so a returning
    // farmer never sees the registration form flash first.
    if (session.restoring) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!session.isRegistered) {
      return const RegistrationScreen();
    }
    // Registered but the walk was never finished -- resume setup rather than
    // showing an empty dashboard for a farm with no blocks.
    if (!session.isSetupComplete) {
      return const WalkScreen();
    }
    // On app open mid-cycle we land on the dashboard, which offers the resume
    // prompt -- never drop straight into capture (docs/PROJECT_SPEC.md §7).
    return const DashboardScreen();
  }
}
