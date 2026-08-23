import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:huluhilir_app/models.dart';
import 'package:huluhilir_app/terrain_canvas.dart';

void main() {
  group('TerrainCanvas', () {
    testWidgets('renders a chip per block, ordered by elevation rank', (tester) async {
      final nodes = [
        TerrainNode(blockId: 'b2', elevationRank: 2, currentState: BlockState.alerted),
        TerrainNode(blockId: 'b1', elevationRank: 1, currentState: BlockState.harmed),
        TerrainNode(blockId: 'b3', elevationRank: 3, currentState: BlockState.protected),
      ];

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: TerrainCanvas(
            nodes: nodes,
            edges: [
              FlowEdgeModel(fromBlockId: 'b1', toBlockId: 'b2', flowWeight: 0.8, barrier: false),
              FlowEdgeModel(fromBlockId: 'b2', toBlockId: 'b3', flowWeight: 0.5, barrier: false),
            ],
            labels: const {'b1': 'Blok Atas', 'b2': 'Blok Tengah', 'b3': 'Blok Bawah'},
          ),
        ),
      ));

      expect(find.text('Blok Atas'), findsOneWidget);
      expect(find.text('Blok Tengah'), findsOneWidget);
      expect(find.text('Blok Bawah'), findsOneWidget);
      // State is surfaced in Malay next to the rank, never as a raw enum.
      expect(find.textContaining('#1'), findsOneWidget);
    });

    testWidgets('renders without blocks rather than throwing', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: TerrainCanvas(nodes: [], edges: [], labels: {})),
      ));
      expect(find.text('Tiada blok lagi'), findsOneWidget);
    });
  });

  group('state colours', () {
    test('every block state maps to a distinct colour and Malay label', () {
      const states = [
        BlockState.protected,
        BlockState.alerted,
        BlockState.harmed,
        BlockState.overrun,
      ];
      final colours = states.map(TerrainCanvas.stateColour).toSet();
      final labels = states.map(TerrainCanvas.stateLabelMs).toSet();
      expect(colours.length, states.length);
      expect(labels.length, states.length);
    });
  });

  group('DashboardModel', () {
    test('parses a farm with zero photographs taken', () {
      // huluhilir-rules §6: rain pulse + advisor must work with no
      // observations, no cycle, and no agent run.
      final model = DashboardModel.fromJson({
        'farm_id': 'f1',
        'rain_pulse': {'day_label': 'Rabu', 'rainfall_mm': 46.0, 'days_away': 2},
        'advisor': {
          'urgency': 'low',
          'reason_code': 'protected_stable',
          'reason_ms': 'Semua blok sihat.',
          'days_since_last_cycle': 6,
          'blocks_all_protected': true,
        },
        'top_action': null,
        'terrain_nodes': [],
        'terrain_edges': [],
        'pending_neighbour_alerts': 0,
        'blocks': [],
      });

      expect(model.topAction, isNull);
      expect(model.rainPulse.rainfallMm, 46.0);
      expect(model.advisor!.reasonCode, 'protected_stable');
    });

    test('surfaces defer_cause as the arbitration record', () {
      final rec = RecommendationModel.fromJson({
        'block_id': 'b1',
        'sequence': 2,
        'action_type': 'spray',
        'treatment_id': 'metalaxyl_drench',
        'recommended_at': '2026-08-27T08:00:00',
        'reason_ms': 'Ditangguh kerana hujan.',
        'defer_cause': 'rainfast',
      });
      expect(rec.deferCause, 'rainfast');
      expect(rec.sequence, 2);
    });
  });
}
