import 'dart:ui';

import 'package:flutter/material.dart';

import 'models.dart';
import 'theme.dart';

/// The signature visual (docs/PROJECT_SPEC.md §7): blocks laid out by
/// `elevation_rank` (highest at the top), coloured by state, connected by
/// downhill flow arrows.
///
/// Layout is by RANK, not by geographic position -- this is a water-flow
/// diagram, not a map. That is deliberate: rendering real coordinates would
/// imply we hold land boundaries, which we explicitly never record
/// (huluhilir-rules skill §4). Rank ordering is the only spatial claim the
/// system actually makes.
///
/// Design note: the visual language here targets a stylised topographic
/// backdrop (terraced gradient) behind the rank/flow diagram, rather than a
/// literal 3D isometric scene with modelled trees. A true 3D terrain render
/// is a materially larger and riskier build (a 3D pipeline, lighting, asset
/// modelling) than the rest of this app, and the rank/flow diagram underneath
/// is the part that's actually load-bearing -- it's what compute_spread's
/// output means. This keeps that correct and legible while matching the
/// warm/organic colour language everywhere else.
class TerrainCanvas extends StatefulWidget {
  final List<TerrainNode> nodes;
  final List<FlowEdgeModel> edges;
  final Map<String, String> labels;
  final void Function(String blockId)? onTapBlock;
  final Widget Function(String blockId, VoidCallback onClose)? profileBuilder;

  const TerrainCanvas({
    super.key,
    required this.nodes,
    required this.edges,
    required this.labels,
    this.onTapBlock,
    this.profileBuilder,
  });

  static Color stateColour(String state) {
    switch (state) {
      case BlockState.harmed:
        return AppColors.stateHarmed;
      case BlockState.overrun:
        return AppColors.stateOverrun;
      case BlockState.alerted:
        return AppColors.stateAlerted;
      default:
        return AppColors.stateProtected;
    }
  }

  static String stateLabelMs(String state) {
    switch (state) {
      case BlockState.harmed:
        return 'Terjejas';
      case BlockState.overrun:
        return 'Teruk';
      case BlockState.alerted:
        return 'Berisiko';
      default:
        return 'Selamat';
    }
  }

  @override
  State<TerrainCanvas> createState() => _TerrainCanvasState();
}

class _TerrainCanvasState extends State<TerrainCanvas> {
  String? _openProfileBlockId;

  @override
  Widget build(BuildContext context) {
    if (widget.nodes.isEmpty) {
      return SizedBox(
        height: 200,
        child: Center(child: Text('Tiada blok lagi', style: AppText.sans(color: AppColors.oliveLight))),
      );
    }

    final sorted = [...widget.nodes]..sort((a, b) => a.elevationRank.compareTo(b.elevationRank));
    final positions = _layout(sorted);

    return LayoutBuilder(builder: (context, constraints) {
      final width = constraints.maxWidth;
      final height = (sorted.length * 78.0).clamp(220.0, 520.0);

      return ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: SizedBox(
          height: height,
          child: Stack(children: [
            // Stylised terraced backdrop: low ground (cool) to high ground
            // (warm/green) -- evokes topography without claiming to be one.
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      AppColors.olive.withValues(alpha: 0.10),
                      AppColors.terracotta.withValues(alpha: 0.06),
                      const Color(0xFFDCE8EC),
                    ],
                  ),
                ),
              ),
            ),
            Positioned.fill(
              child: CustomPaint(
                painter: _FlowPainter(
                  positions: positions,
                  edges: widget.edges,
                  canvasSize: Size(width, height),
                ),
              ),
            ),
            for (final node in sorted)
              Positioned(
                left: positions[node.blockId]!.dx * width - 58,
                top: positions[node.blockId]!.dy * height - 22,
                child: _BlockChip(
                  label: widget.labels[node.blockId] ?? node.blockId.substring(0, 4),
                  rank: node.elevationRank,
                  state: node.currentState,
                  onTap: () {
                    widget.onTapBlock?.call(node.blockId);
                    if (widget.profileBuilder != null) {
                      setState(() => _openProfileBlockId = node.blockId);
                    }
                  },
                ),
              ),
            Positioned(top: 12, left: 12, child: _LegendOverlay()),
            if (_openProfileBlockId != null && widget.profileBuilder != null)
              // left AND right, not right alone. With only `right` set the card
              // gets UNBOUNDED width, and BlockProfileCard's header uses
              // `SizedBox(width: double.infinity)` — so it laid out wider than
              // the Stack, putting its close button outside the parent's
              // bounds. Flutter does not hit-test outside those bounds, so the
              // X was visible (ClipRRect hid the overflow) but untappable.
              // Same fix applied in terrain_3d_view.dart.
              Positioned(
                top: 12,
                left: 12,
                right: 12,
                child: Material(
                  color: Colors.transparent,
                  child: widget.profileBuilder!(
                    _openProfileBlockId!,
                    () => setState(() => _openProfileBlockId = null),
                  ),
                ),
              ),
          ]),
        ),
      );
    });
  }

  /// Normalised (0..1) positions. Rank drives the vertical axis; blocks
  /// sharing a rank band are fanned horizontally so edges stay readable.
  ///
  /// The topmost (highest-ranked) node is pinned to the right half: the
  /// legend overlay always occupies the top-left corner, and centring rank 1
  /// there (as a naive alternating fan does) overlaps its label.
  Map<String, Offset> _layout(List<TerrainNode> sorted) {
    final positions = <String, Offset>{};
    final n = sorted.length;
    for (var i = 0; i < n; i++) {
      final y = n == 1 ? 0.5 : 0.14 + (0.74 * i / (n - 1));
      double x;
      if (i == 0) {
        x = 0.68;
      } else if (i == n - 1) {
        x = 0.5 - 0.16 * 0.3;
      } else {
        x = 0.5 + (i.isEven ? -0.16 : 0.16);
      }
      positions[sorted[i].blockId] = Offset(x, y);
    }
    return positions;
  }
}

class _BlockChip extends StatelessWidget {
  final String label;
  final int rank;
  final String state;
  final VoidCallback? onTap;

  const _BlockChip({required this.label, required this.rank, required this.state, this.onTap});

  @override
  Widget build(BuildContext context) {
    final colour = TerrainCanvas.stateColour(state);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 116,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: colour,
          borderRadius: BorderRadius.circular(14),
          boxShadow: softShadow(tint: colour.withValues(alpha: 0.35)),
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: AppText.sans(color: Colors.white, weight: FontWeight.w700, size: 13),
          ),
          Text(
            '#$rank · ${TerrainCanvas.stateLabelMs(state)}',
            style: AppText.sans(color: Colors.white.withValues(alpha: 0.85), size: 10),
          ),
        ]),
      ),
    );
  }
}

/// Top-left blurred legend: state colours + the downhill-flow line convention.
class _LegendOverlay extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.72),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.hairline),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            _legendRow(AppColors.stateHarmed, 'Terjejas'),
            _legendRow(AppColors.stateAlerted, 'Berisiko'),
            _legendRow(AppColors.stateProtected, 'Selamat'),
            const SizedBox(height: 4),
            Row(children: [
              SizedBox(
                width: 16,
                child: CustomPaint(painter: _DashedLinePainter(color: AppColors.olive)),
              ),
              const SizedBox(width: 6),
              Text('Aliran hiliran', style: AppText.sans(size: 10, color: AppColors.charcoal)),
            ]),
          ]),
        ),
      ),
    );
  }

  Widget _legendRow(Color color, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(label, style: AppText.sans(size: 10, color: AppColors.charcoal)),
        ]),
      );
}

class _DashedLinePainter extends CustomPainter {
  final Color color;
  _DashedLinePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2;
    const dash = 3.0, gap = 2.0;
    var x = 0.0;
    while (x < size.width) {
      canvas.drawLine(Offset(x, size.height / 2), Offset((x + dash).clamp(0, size.width), size.height / 2), paint);
      x += dash + gap;
    }
  }

  @override
  bool shouldRepaint(covariant _DashedLinePainter old) => old.color != color;
}

/// Block "profile" card shown on tap -- photo/state header plus whatever
/// history content the caller supplies via profileBuilder.
class _ProfileOverlay extends StatelessWidget {
  final Widget child;
  const _ProfileOverlay({required this.child});

  @override
  Widget build(BuildContext context) {
    // Positioning and sizing ONLY. This used to add its own white card and a
    // second, smaller close button stacked over the one BlockProfileCard
    // already draws -- two X's, with the wrapper's on top, so taps landed on
    // whichever happened to win hit-testing. The card owns its own chrome.
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 320, maxHeight: 460),
      child: child,
    );
  }
}
class _FlowPainter extends CustomPainter {
  final Map<String, Offset> positions;
  final List<FlowEdgeModel> edges;
  final Size canvasSize;

  _FlowPainter({required this.positions, required this.edges, required this.canvasSize});

  @override
  void paint(Canvas canvas, Size size) {
    for (final edge in edges) {
      final from = positions[edge.fromBlockId];
      final to = positions[edge.toBlockId];
      if (from == null || to == null) continue;

      final start = Offset(from.dx * size.width, from.dy * size.height + 22);
      final end = Offset(to.dx * size.width, to.dy * size.height - 24);

      // Heavier flow = thicker, more opaque arrow. Barriers (bund/road) are
      // drawn dashed and greyed -- water does not pass.
      final paint = Paint()
        ..color = edge.barrier
            ? const Color(0x44607D8B)
            : Color.lerp(AppColors.olive.withValues(alpha: 0.25), AppColors.olive, edge.flowWeight)!
        ..strokeWidth = edge.barrier ? 1.2 : (1.5 + 3.0 * edge.flowWeight)
        ..style = PaintingStyle.stroke;

      if (edge.barrier) {
        _drawDashed(canvas, start, end, paint);
      } else {
        canvas.drawLine(start, end, paint);
        _drawArrowHead(canvas, start, end, paint);
      }
    }
  }

  void _drawArrowHead(Canvas canvas, Offset start, Offset end, Paint paint) {
    final direction = (end - start);
    final length = direction.distance;
    if (length < 1) return;
    final unit = direction / length;
    final perpendicular = Offset(-unit.dy, unit.dx);
    const headLength = 9.0;
    const headWidth = 5.0;
    final base = end - unit * headLength;

    final path = Path()
      ..moveTo(end.dx, end.dy)
      ..lineTo(base.dx + perpendicular.dx * headWidth, base.dy + perpendicular.dy * headWidth)
      ..lineTo(base.dx - perpendicular.dx * headWidth, base.dy - perpendicular.dy * headWidth)
      ..close();

    canvas.drawPath(path, Paint()..color = paint.color);
  }

  void _drawDashed(Canvas canvas, Offset start, Offset end, Paint paint) {
    const dash = 6.0, gap = 4.0;
    final total = (end - start).distance;
    if (total < 1) return;
    final unit = (end - start) / total;
    var travelled = 0.0;
    while (travelled < total) {
      final segmentEnd = (travelled + dash).clamp(0.0, total);
      canvas.drawLine(start + unit * travelled, start + unit * segmentEnd, paint);
      travelled = segmentEnd + gap;
    }
  }

  @override
  bool shouldRepaint(covariant _FlowPainter old) =>
      old.positions != positions || old.edges != edges;
}
