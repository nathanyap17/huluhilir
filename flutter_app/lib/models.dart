/// Dart mirrors of the backend Pydantic contract (backend/app/schemas/).
///
/// Hand-written rather than generated: the codegen route (openapi-generator /
/// build_runner) costs more setup time than it saves for this many models, and
/// contract drift is caught by the integration test in
/// backend/tests/test_setup_flow.py plus /openapi.json being the single source
/// of truth. If these ever disagree with the backend, the backend wins.

class BlockState {
  static const protected = 'protected';
  static const alerted = 'alerted';
  static const harmed = 'harmed';
  static const overrun = 'overrun';
}

class UserModel {
  final String userId;
  final String displayName;
  final String district;

  UserModel({required this.userId, required this.displayName, required this.district});

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
        userId: json['user_id'],
        displayName: json['display_name'],
        district: json['district'],
      );
}

class FarmModel {
  final String farmId;
  final String name;
  final String elevationTier;
  final bool barometerAvailable;
  final String? setupCompletedAt;

  FarmModel({
    required this.farmId,
    required this.name,
    required this.elevationTier,
    required this.barometerAvailable,
    this.setupCompletedAt,
  });

  bool get isSetupComplete => setupCompletedAt != null;

  factory FarmModel.fromJson(Map<String, dynamic> json) => FarmModel(
        farmId: json['farm_id'],
        name: json['name'],
        elevationTier: json['elevation_tier'],
        barometerAvailable: json['barometer_available'] ?? false,
        setupCompletedAt: json['setup_completed_at'],
      );
}

class BlockModel {
  final String blockId;
  final String label;
  final String? voiceLabelUri;
  final String photoUri;
  final double lat;
  final double lon;
  final int elevationRank;
  final String drainage;
  final String currentState;
  final int? vineCount;
  final bool isExternal;

  BlockModel({
    required this.blockId,
    required this.label,
    this.voiceLabelUri,
    required this.photoUri,
    required this.lat,
    required this.lon,
    required this.elevationRank,
    required this.drainage,
    required this.currentState,
    this.vineCount,
    required this.isExternal,
  });

  factory BlockModel.fromJson(Map<String, dynamic> json) => BlockModel(
        blockId: json['block_id'],
        label: json['label'],
        voiceLabelUri: json['voice_label_uri'],
        photoUri: json['photo_uri'],
        lat: (json['centroid_lat'] as num).toDouble(),
        lon: (json['centroid_lon'] as num).toDouble(),
        elevationRank: json['elevation_rank'],
        drainage: json['drainage'],
        currentState: json['current_state'],
        vineCount: json['vine_count'],
        isExternal: json['is_external'] ?? false,
      );
}

class FlowEdgeModel {
  final String fromBlockId;
  final String toBlockId;
  final double flowWeight;
  final bool barrier;

  FlowEdgeModel({
    required this.fromBlockId,
    required this.toBlockId,
    required this.flowWeight,
    required this.barrier,
  });

  factory FlowEdgeModel.fromJson(Map<String, dynamic> json) => FlowEdgeModel(
        fromBlockId: json['from_block_id'],
        toBlockId: json['to_block_id'],
        flowWeight: (json['flow_weight'] as num).toDouble(),
        barrier: json['barrier'] ?? false,
      );
}

class RainPulse {
  final String dayLabel;
  final double rainfallMm;
  final int daysAway;
  final String? speechTemplateId;

  RainPulse({
    required this.dayLabel,
    required this.rainfallMm,
    required this.daysAway,
    this.speechTemplateId,
  });

  factory RainPulse.fromJson(Map<String, dynamic> json) => RainPulse(
        dayLabel: json['day_label'],
        rainfallMm: (json['rainfall_mm'] as num).toDouble(),
        daysAway: json['days_away'],
        speechTemplateId: json['speech_template_id'],
      );
}

class AdvisorVerdict {
  final String urgency;
  final String reasonCode;
  final String reasonMs;
  final int daysSinceLastCycle;
  final bool blocksAllProtected;

  AdvisorVerdict({
    required this.urgency,
    required this.reasonCode,
    required this.reasonMs,
    required this.daysSinceLastCycle,
    required this.blocksAllProtected,
  });

  factory AdvisorVerdict.fromJson(Map<String, dynamic> json) => AdvisorVerdict(
        urgency: json['urgency'],
        reasonCode: json['reason_code'],
        reasonMs: json['reason_ms'],
        daysSinceLastCycle: json['days_since_last_cycle'],
        blocksAllProtected: json['blocks_all_protected'] ?? false,
      );
}

class RecommendationModel {
  /// Needed to fetch the decision blueprint for this specific action.
  final String recommendationId;
  final String blockId;
  final int sequence;
  final String actionType;
  final String? treatmentId;
  final String recommendedAt;
  final String reasonMs;
  final String? deferCause;
  final String? speechTemplateId;

  RecommendationModel({
    required this.recommendationId,
    required this.blockId,
    required this.sequence,
    required this.actionType,
    this.treatmentId,
    required this.recommendedAt,
    required this.reasonMs,
    this.deferCause,
    this.speechTemplateId,
  });

  factory RecommendationModel.fromJson(Map<String, dynamic> json) => RecommendationModel(
        recommendationId: json['recommendation_id'] ?? '',
        blockId: json['block_id'],
        sequence: json['sequence'],
        actionType: json['action_type'],
        treatmentId: json['treatment_id'],
        recommendedAt: json['recommended_at'],
        reasonMs: json['reason_ms'],
        deferCause: json['defer_cause'],
        speechTemplateId: json['speech_template_id'],
      );
}

class TerrainNode {
  final String blockId;
  final int elevationRank;
  final String currentState;

  TerrainNode({required this.blockId, required this.elevationRank, required this.currentState});

  factory TerrainNode.fromJson(Map<String, dynamic> json) => TerrainNode(
        blockId: json['block_id'],
        elevationRank: json['elevation_rank'],
        currentState: json['current_state'],
      );
}

class DashboardModel {
  final String farmId;
  final RainPulse rainPulse;
  final AdvisorVerdict? advisor;
  final RecommendationModel? topAction;
  final List<TerrainNode> terrainNodes;
  final List<FlowEdgeModel> terrainEdges;
  final int pendingNeighbourAlerts;
  final List<BlockModel> blocks;

  DashboardModel({
    required this.farmId,
    required this.rainPulse,
    this.advisor,
    this.topAction,
    required this.terrainNodes,
    required this.terrainEdges,
    required this.pendingNeighbourAlerts,
    required this.blocks,
  });

  factory DashboardModel.fromJson(Map<String, dynamic> json) => DashboardModel(
        farmId: json['farm_id'],
        rainPulse: RainPulse.fromJson(json['rain_pulse']),
        advisor: json['advisor'] != null ? AdvisorVerdict.fromJson(json['advisor']) : null,
        topAction:
            json['top_action'] != null ? RecommendationModel.fromJson(json['top_action']) : null,
        terrainNodes: (json['terrain_nodes'] as List).map((e) => TerrainNode.fromJson(e)).toList(),
        terrainEdges: (json['terrain_edges'] as List).map((e) => FlowEdgeModel.fromJson(e)).toList(),
        pendingNeighbourAlerts: json['pending_neighbour_alerts'] ?? 0,
        blocks: (json['blocks'] as List).map((e) => BlockModel.fromJson(e)).toList(),
      );
}

class ElevationQuestion {
  final String blockAId;
  final String blockBId;
  final String? blockALabel;
  final String? blockBLabel;

  ElevationQuestion({
    required this.blockAId,
    required this.blockBId,
    this.blockALabel,
    this.blockBLabel,
  });

  factory ElevationQuestion.fromJson(Map<String, dynamic> json) => ElevationQuestion(
        blockAId: json['block_a_id'],
        blockBId: json['block_b_id'],
        blockALabel: json['block_a_label'],
        blockBLabel: json['block_b_label'],
      );
}

class DiagnosisCycleModel {
  final String cycleId;
  final int blocksTotal;
  final int blocksCaptured;
  final String status;

  DiagnosisCycleModel({
    required this.cycleId,
    required this.blocksTotal,
    required this.blocksCaptured,
    required this.status,
  });

  factory DiagnosisCycleModel.fromJson(Map<String, dynamic> json) => DiagnosisCycleModel(
        cycleId: json['cycle_id'],
        blocksTotal: json['blocks_total'],
        blocksCaptured: json['blocks_captured'],
        status: json['status'],
      );
}

/// Result of one photo classification. `retakePrompt` non-null means the photo
/// did not match what the farmer said they were photographing -- the UI must
/// prompt a retake and NOT record it as a completed check.
class DiagnosisResult {
  final String predictedClass;
  final double confidence;
  final bool belowThreshold;
  final bool countsAsCheck;
  final String? retakePrompt;

  DiagnosisResult({
    required this.predictedClass,
    required this.confidence,
    required this.belowThreshold,
    required this.countsAsCheck,
    this.retakePrompt,
  });

  factory DiagnosisResult.fromJson(Map<String, dynamic> json) {
    final d = json['diagnosis'];
    return DiagnosisResult(
      predictedClass: d['predicted_class'],
      confidence: (d['confidence'] as num).toDouble(),
      belowThreshold: d['below_threshold'] ?? false,
      countsAsCheck: json['counts_as_check'] ?? false,
      retakePrompt: json['retake_prompt'],
    );
  }
}
