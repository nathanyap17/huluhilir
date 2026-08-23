/// The block profile shown when a terrain node is tapped.
///
/// Previously this rendered only the fields already present in the dashboard
/// payload — label, rank, drainage, vine count — so the block photo, the
/// voice label and the observation history simply had nowhere to come from.
/// It now fetches `/blocks/{id}/detail` on demand.
///
/// The voice label is **played, never transcribed**. There is no speech
/// recognition anywhere in this codebase, and that is precisely why an Iban
/// label works here at all (huluhilir-rules §1).
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:just_audio/just_audio.dart';

import 'models.dart';
import 'i18n.dart';
import 'providers.dart';
import 'terrain_canvas.dart' show TerrainCanvas;
import 'theme.dart';

/// Fetched per block, so tapping around the terrain does not refetch a block
/// already looked at in this session.
final blockDetailProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, blockId) async {
  return ref.watch(apiClientProvider).blockDetail(blockId);
});


class BlockProfileCard extends ConsumerWidget {
  final BlockModel block;
  final RecommendationModel? action;
  final VoidCallback? onClose;

  const BlockProfileCard({
    super.key,
    required this.block,
    this.action,
    this.onClose,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colour = TerrainCanvas.stateColour(block.currentState);
    final api = ref.watch(apiClientProvider);
    final detail = ref.watch(blockDetailProvider(block.blockId));

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: softShadow(),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        // Header: the block's own photo as the background, which is what
        // makes a block recognisable to the person who marked it. Falls back
        // to the state colour when there is no photo or it will not load --
        // never a broken-image glyph.
        SizedBox(
          height: 108,
          width: double.infinity,
          child: Stack(fit: StackFit.expand, children: [
            Container(color: colour),
            detail.maybeWhen(
              data: (d) {
                // Server-resolved: the block's capture photo, or its most
                // recent observation photo when that is a seed placeholder.
                final uri = d['header_image_uri'] as String?;
                if (uri == null || uri.isEmpty) return const SizedBox.shrink();
                return Image.network(
                  api.mediaUrl(uri),
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stack) => const SizedBox.shrink(),
                );
              },
              orElse: () => const SizedBox.shrink(),
            ),
            // Scrim, so white type stays readable over an arbitrary photo.
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.10),
                    colour.withValues(alpha: 0.86),
                  ],
                ),
              ),
            ),
            Positioned(
              left: 14,
              right: 44,
              bottom: 10,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(block.label,
                      style: AppText.sans(
                          size: 17, weight: FontWeight.w700, color: Colors.white)),
                  Text(
                    '#${block.elevationRank} · ${TerrainCanvas.stateLabelMs(block.currentState)}',
                    style: AppText.sans(
                        size: 12, color: Colors.white.withValues(alpha: 0.92)),
                  ),
                ],
              ),
            ),
            // Sits over an arbitrary photo, so it carries its own dark disc
            // rather than relying on the scrim for contrast. 44x44 is the
            // minimum comfortable touch target, and this is the only close
            // affordance on the card -- the terrain views used to stack a
            // second, smaller one on top of it.
            if (onClose != null)
              Positioned(
                right: 6,
                top: 6,
                child: Material(
                  color: Colors.black.withValues(alpha: 0.42),
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: onClose,
                    child: const SizedBox(
                      width: 44,
                      height: 44,
                      child: Icon(Icons.close, size: 22, color: Colors.white),
                    ),
                  ),
                ),
              ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(children: [
                Expanded(
                  child: Text('${tr(ref, 'block.drainage')}: ${block.drainage}', style: AppText.sans(size: 12)),
                ),
                if (block.vineCount != null)
                  Text('${block.vineCount} ${tr(ref, 'block.vines')}', style: AppText.sans(size: 12)),
              ]),
              detail.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 14),
                  child: SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                ),
                error: (e, _) => Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(tr(ref, 'block.historyFailed'),
                      style: AppText.sans(size: 11, color: AppColors.oliveLight)),
                ),
                data: (d) => _Detail(detail: d, mediaUrl: api.mediaUrl),
              ),
              if (action != null) ...[
                const SizedBox(height: 10),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.cream,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(action!.reasonMs, style: AppText.sans(size: 12)),
                ),
              ],
            ],
          ),
        ),
      ]),
    );
  }
}

class _Detail extends ConsumerWidget {
  final Map<String, dynamic> detail;
  final String Function(String) mediaUrl;
  const _Detail({required this.detail, required this.mediaUrl});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final voice = detail['voice_label_uri'] as String?;
    final observations = (detail['observations'] as List?) ?? const [];
    final baro = detail['baro_rel_m'] as num?;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      if (baro != null)
        Text('Ketinggian relatif: ${baro.toStringAsFixed(1)} m',
            style: AppText.sans(size: 12, color: AppColors.oliveLight)),

      if (voice != null && voice.isNotEmpty) ...[
        const SizedBox(height: 8),
        _VoiceLabelButton(url: mediaUrl(voice)),
      ],

      const SizedBox(height: 12),
      Text(tr(ref, 'block.history'), style: AppText.eyebrow()),
      const SizedBox(height: 6),
      if (observations.isEmpty)
        Text(tr(ref, 'block.noPhotos'),
            style: AppText.sans(size: 12, color: AppColors.oliveLight))
      else
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 190),
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: observations.length,
            separatorBuilder: (context, index) => const SizedBox(height: 8),
            itemBuilder: (context, i) =>
                _HistoryRow(row: observations[i] as Map<String, dynamic>, mediaUrl: mediaUrl),
          ),
        ),
    ]);
  }
}

class _HistoryRow extends ConsumerWidget {
  final Map<String, dynamic> row;
  final String Function(String) mediaUrl;
  const _HistoryRow({required this.row, required this.mediaUrl});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cls = row['predicted_class'] as String?;
    final conf = row['confidence'] as num?;
    final low = row['below_threshold'] == true;
    final when = (row['captured_at'] as String? ?? '').split('T').first;
    final uri = row['image_uri'] as String?;

    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: SizedBox(
          width: 44,
          height: 44,
          child: uri == null
              ? Container(color: AppColors.cream)
              : Image.network(
                  mediaUrl(uri),
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stack) => Container(color: AppColors.cream),
                ),
        ),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(cls == null ? tr(ref, 'block.noPhotos') : classLabel(cls, ref.watch(langProvider)),
              style: AppText.sans(size: 12, weight: FontWeight.w600)),
          Text(
            '$when${conf != null ? ' · ${(conf * 100).toStringAsFixed(0)}%' : ''}',
            style: AppText.sans(size: 11, color: AppColors.oliveLight),
          ),
          // Surfaced rather than hidden: a low-confidence call must read as
          // "go and look", not as a diagnosis (huluhilir-rules §9).
          if (low)
            Text(tr(ref, 'block.lowConfidence'),
                style: AppText.sans(size: 10, color: AppColors.terracotta)),
        ]),
      ),
    ]);
  }
}

/// Plays the farmer's own recording of the block name.
class _VoiceLabelButton extends StatefulWidget {
  final String url;
  const _VoiceLabelButton({required this.url});

  @override
  State<_VoiceLabelButton> createState() => _VoiceLabelButtonState();
}

class _VoiceLabelButtonState extends State<_VoiceLabelButton> {
  final _player = AudioPlayer();
  bool _busy = false;

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _play() async {
    setState(() => _busy = true);
    try {
      await _player.setUrl(widget.url);
      await _player.play();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Rakaman tidak dapat dimainkan: $e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: _busy ? null : _play,
      icon: _busy
          ? const SizedBox(
              width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.play_arrow, size: 18),
      label: Consumer(builder: (context, ref, _) => Text(tr(ref, 'block.playLabel'))),
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.olive,
        side: const BorderSide(color: AppColors.hairline),
        minimumSize: const Size(0, 38),
      ),
    );
  }
}
