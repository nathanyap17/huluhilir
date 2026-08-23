import 'package:flutter/material.dart';

import 'models.dart';

/// The signature visual (docs/PROJECT_SPEC.md §7): blocks laid out by
/// `elevation_rank` (highest at the top), coloured by state, connected by
/// downhill flow arrows.
///
/// Layout is by RANK, not by geographic position -- this is a water-flow
/// diagram, not a map. That is deliberate: rendering real coordinates would
/// imply we hold land boundaries, and we explicitly never record those
/// (huluhilir-rules skill §4). Rank ordering is the only spatial claim the
/// system actually makes.
class TerrainCanvas extends StatelessWidget {
  final List<TerrainNode> nodes;
  final List<FlowEdgeModel> edges;
  final Map<String, String> labels;
  final void Function(String blockId)? onTapBlock;

  const TerrainCanvas({
    super.key,
    required this.nodes,
    required this.edges,
    required this.labels,
    this.onTapBlock,
  });

  static Color stateColour(String state) {
    switch (state) {
      case BlockState.harmed:
        return const Color(0xFFD32F2F);
      case BlockState.overrun:
        return const Color(0xFF6A1B1A);
      case BlockState.alerted:
        return const Color(0xFFF9A825);
      default:
        return const Color(0xFF2E7D32);
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
  Widget build(BuildContext context) {
    if (nodes.isEmpty) {
      return const SizedBox(
        height: 200,
        child: Center(child: Text('Tiada blok lagi')),
      );
    }

    final sorted = [...nodes]..sort((a, b) => a.elevationRank.compareTo(b.elevationRank));
    final positions = _layout(sorted);

    return LayoutBuilder(builder: (context, constraints) {
      final width = constraints.maxWidth;
      final height = (sorted.length * 78.0).clamp(200.0, 520.0);

      return SizedBox(
        height: height,
        child: Stack(children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _FlowPainter(
                positions: positions,
                edges: edges,
                canvasSize: Size(width, height),
              ),
            ),
          ),
          for (final node in sorted)
            Positioned(
              left: positions[node.blockId]!.dx * width - 58,
              top: positions[node.blockId]!.dy * height - 22,
              child: _BlockChip(
                label: labels[node.blockId] ?? node.blockId.substring(0, 4),
                rank: node.elevationRank,
                state: node.currentState,
                onTap: onTapBlock == null ? null : () => onTapBlock!(node.blockId),
              ),
            ),
        ]),
      );
    });
  }

  /// Normalised (0..1) positions. Rank drives the vertical axis; blocks
  /// sharing a rank band are fanned horizontally so edges stay readable.
  Map<String, Offset> _layout(List<TerrainNode> sorted) {
    final positions = <String, Offset>{};
    final n = sorted.length;
    for (var i = 0; i < n; i++) {
      final y = n == 1 ? 0.5 : 0.10 + (0.80 * i / (n - 1));
      // Alternate left/right of centre so arrows don't overlap vertically.
      final x = 0.5 + (i.isEven ? -0.16 : 0.16) * (i == 0 || i == n - 1 ? 0.3 : 1.0);
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

  const _BlockChip({
    required this.label,
    required this.rank,
    required this.state,
    this.onTap,
  });

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
          borderRadius: BorderRadius.circular(10),
          boxShadow: const [BoxShadow(blurRadius: 4, color: Color(0x33000000), offset: Offset(0, 2))],
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
          ),
          Text(
            '#$rank · ${TerrainCanvas.stateLabelMs(state)}',
            style: const TextStyle(color: Colors.white70, fontSize: 10),
          ),
        ]),
      ),
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
            : Color.lerp(const Color(0x332196F3), const Color(0xCC1565C0), edge.flowWeight)!
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
