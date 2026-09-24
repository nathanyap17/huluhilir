/** Split out from TerrainScene.tsx so SafeTerrainScene.tsx can import these
 * types without pulling in @react-three/fiber/three at module-eval time. */
export interface TerrainBlockNode {
  block_id: string;
  elevation_rank: number;
  current_state: string;
  x_rot_m: number;
  y_rot_m: number;
}

export interface TerrainEdge {
  from_block_id: string;
  to_block_id: string;
  flow_weight?: number;
  barrier?: boolean;
}

export interface TerrainSceneProps {
  blocks: TerrainBlockNode[];
  edges: TerrainEdge[];
  onSelectBlock: (blockId: string) => void;
}
