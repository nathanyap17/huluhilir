/// "Tanya" — free-form questions answered over retrieval. L3/L4.
///
/// The Advisor agent behind this can only reach `retrieve_knowledge`, which
/// is hard-scoped away from the authoritative namespace. It therefore
/// **explains why, and structurally cannot decide what** (huluhilir-rules
/// §2) — no dose, product, or timing can come back through this path. That
/// guarantee comes from what the agent can reach, not from prompt wording,
/// which is why the disclaimer below can be stated as fact.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../speech.dart';
import '../theme.dart';

class TanyaSheet extends ConsumerStatefulWidget {
  const TanyaSheet({super.key});

  @override
  ConsumerState<TanyaSheet> createState() => _TanyaSheetState();
}

class _QA {
  final String question;
  final String answer;
  _QA(this.question, this.answer);
}

class _TanyaSheetState extends ConsumerState<TanyaSheet> {
  final _controller = TextEditingController();
  final _history = <_QA>[];
  bool _busy = false;
  String? _error;

  /// Openers, so a farmer facing an empty text box has somewhere to start.
  /// Phrased as questions a farmer would actually ask, not as feature names.
  static const _suggestions = [
    'Apa punca penyakit busuk pangkal?',
    'Kenapa hujan penting untuk semburan?',
    'Bagaimana air membawa penyakit ke bawah?',
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _ask(String question) async {
    if (question.trim().length < 2 || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref.read(apiClientProvider).askAdvisor(question.trim());
      final answer = (result['answer'] as String?)?.trim();
      setState(() {
        _history.insert(
          0,
          _QA(question.trim(), answer?.isNotEmpty == true ? answer! : 'Tiada maklumat.'),
        );
        _controller.clear();
      });
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: DraggableScrollableSheet(
        initialChildSize: 0.85,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scrollController) => Container(
          decoration: const BoxDecoration(
            color: AppColors.cream,
            borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.card)),
          ),
          padding: const EdgeInsets.all(24),
          child: Column(children: [
            Row(children: [
              Text('TANYA', style: AppText.eyebrow()),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.close, color: AppColors.olive),
                onPressed: () => Navigator.pop(context),
              ),
            ]),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Penerangan sahaja — dos dan masa semburan datang dari cadangan rasmi.',
                style: AppText.sans(size: 11, color: AppColors.oliveLight)
                    .copyWith(fontStyle: FontStyle.italic),
              ),
            ),
            const SizedBox(height: 16),
            Expanded(
              child: _history.isEmpty && !_busy
                  ? ListView(
                      controller: scrollController,
                      children: [
                        Text('Contoh soalan:',
                            style: AppText.sans(size: 12, color: AppColors.oliveLight)),
                        const SizedBox(height: 12),
                        for (final s in _suggestions)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: OutlinedButton(
                              onPressed: () => _ask(s),
                              style: OutlinedButton.styleFrom(
                                alignment: Alignment.centerLeft,
                                minimumSize: const Size.fromHeight(52),
                                side: const BorderSide(color: AppColors.hairline),
                              ),
                              child: Align(
                                alignment: Alignment.centerLeft,
                                child: Text(s,
                                    style: AppText.sans(size: 14, color: AppColors.charcoal)),
                              ),
                            ),
                          ),
                      ],
                    )
                  : ListView.builder(
                      controller: scrollController,
                      itemCount: _history.length,
                      itemBuilder: (context, i) => _AnswerCard(qa: _history[i]),
                    ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: AppText.sans(size: 12, color: AppColors.terracotta)),
            ],
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  enabled: !_busy,
                  textInputAction: TextInputAction.send,
                  onSubmitted: _ask,
                  decoration: InputDecoration(
                    hintText: 'Tanya sesuatu…',
                    filled: true,
                    fillColor: Colors.white,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppRadius.card),
                      borderSide: const BorderSide(color: AppColors.hairline),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _busy
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : IconButton.filled(
                      icon: const Icon(Icons.send),
                      onPressed: () => _ask(_controller.text),
                    ),
            ]),
          ]),
        ),
      ),
    );
  }
}

class _AnswerCard extends ConsumerWidget {
  final _QA qa;
  const _AnswerCard({required this.qa});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.hairline),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(qa.question,
            style: AppText.sans(size: 13, weight: FontWeight.w600, color: AppColors.oliveLight)),
        const SizedBox(height: 10),
        Text(qa.answer, style: AppText.serif(size: 16, color: AppColors.charcoal)),
        const SizedBox(height: 6),
        Align(
          alignment: Alignment.centerRight,
          child: IconButton(
            icon: const Icon(Icons.volume_up, size: 20, color: AppColors.oliveLight),
            tooltip: 'Dengar',
            onPressed: () => speak(context, ref, qa.answer),
          ),
        ),
      ]),
    );
  }
}
