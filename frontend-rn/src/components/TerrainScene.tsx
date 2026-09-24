/**
 * §9.6 — Terrain Risk Canvas (3D scene, @react-three/fiber + expo-gl).
 *
 * Adapted from the Flutter WebView terrain (flutter_app/assets/terrain/terrain.html)
 * for React Native with full 3D visual fidelity:
 *
 *   • IDW-interpolated terraced height field on PlaneGeometry with vivid
 *     elevation gradient and earth-tinted terrace cliff risers.
 *   • Diorama bedrock pedestal: 3D skirt down to base plate showing the
 *     topographic cross-section.
 *   • Block depiction as an authentic CLUSTER OF VINES (mini pepper plot):
 *     raised agricultural soil mound with 5 wooden tiang posts, climbing bushy
 *     pepper foliage on each post, and a translucent disease core beneath.
 *   • 3D directional water drainage flow with downstream arrowheads pointing
 *     down the slope, plus barrier styling.
 *   • Smooth orbit controls: delta-based drag (no fighting/trembling),
 *     inertial momentum damping on release, gentle idle auto-rotate, and
 *     responsive block tap selection.
 *
 * Layout is rank-based synthetic (never real lat/lon, pepperdex-rules §4).
 */
import { Canvas, useFrame, useThree } from "@react-three/fiber/native";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GestureResponderEvent, PanResponder, PanResponderGestureState, View } from "react-native";
import * as THREE from "three";
import { colors } from "../constants/theme";
import type { TerrainBlockNode, TerrainEdge, TerrainSceneProps } from "./terrainTypes";

export type { TerrainBlockNode, TerrainEdge };

// ---- constants ----

const PLANE_SIZE = 18;
const SEGMENTS = 70; // High enough for crisp terraces, lightweight for mobile GPU
const STEP_HEIGHT = 0.35;
const MAX_HEIGHT = 4.2; // Pronounced height relief so altitude difference is vivid
const ISLAND_RADIUS = 7.8;
const IDW_POWER = 2.8;

const STATE_COLOR: Record<string, number> = {
  protected: 0x5a5a40, // olive green (healthy)
  alerted: 0xebc366,   // warning yellow
  harmed: 0xcc7a5c,    // terracotta orange
  overrun: 0x8b3a2b,   // deep rust red
};

// High-contrast elevation colour ramp:
// Base valley floor -> lush mid slope -> sunlit ridge highland
const ELEVATION_STOPS: [number, number][] = [
  [0.00, 0x1f3d22], // deep damp valley floor
  [0.20, 0x2e562b], // lower slope
  [0.45, 0x487935], // mid terrace agricultural green
  [0.70, 0x699942], // upper terrace
  [0.88, 0x8eb84b], // sunlit ridge
  [1.00, 0xb8c95a], // high plateau golden green
];

// Terrace riser earth/rock tint
const ROCK_TINT: [number, number, number] = [0.36, 0.31, 0.25];

function lerpColour(c1: number, c2: number, t: number): [number, number, number] {
  const r1 = (c1 >> 16) & 255, g1 = (c1 >> 8) & 255, b1 = c1 & 255;
  const r2 = (c2 >> 16) & 255, g2 = (c2 >> 8) & 255, b2 = c2 & 255;
  return [
    (r1 + (r2 - r1) * t) / 255,
    (g1 + (g2 - g1) * t) / 255,
    (b1 + (b2 - b1) * t) / 255,
  ];
}

function elevationColour(t: number): [number, number, number] {
  t = Math.max(0, Math.min(1, t));
  for (let i = 0; i < ELEVATION_STOPS.length - 1; i++) {
    const [t0, c0] = ELEVATION_STOPS[i];
    const [t1, c1] = ELEVATION_STOPS[i + 1];
    if (t >= t0 && t <= t1) {
      const localT = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
      return lerpColour(c0, c1, localT);
    }
  }
  const last = ELEVATION_STOPS[ELEVATION_STOPS.length - 1];
  return lerpColour(last[1], last[1], 0);
}

interface IDWSample {
  x: number;
  z: number;
  height: number;
}

function idwHeight(x: number, z: number, samples: IDWSample[]): number {
  let weightSum = 0, valueSum = 0;
  for (const s of samples) {
    const dx = x - s.x, dz = z - s.z;
    const dist2 = dx * dx + dz * dz;
    if (dist2 < 0.01) return s.height;
    const w = 1 / Math.pow(dist2, IDW_POWER / 2);
    weightSum += w;
    valueSum += w * s.height;
  }
  return weightSum > 0 ? valueSum / weightSum : 0;
}

function heightAt(samples: IDWSample[], x: number, z: number): number {
  if (!samples.length) return 0;
  let h = idwHeight(x, z, samples);
  const distFromCentre = Math.sqrt(x * x + z * z);
  if (distFromCentre > ISLAND_RADIUS) {
    const outer = PLANE_SIZE / 2;
    const t = Math.min(1, (distFromCentre - ISLAND_RADIUS) / (outer - ISLAND_RADIUS));
    h *= 1 - t;
  }
  return Math.floor(h / STEP_HEIGHT) * STEP_HEIGHT;
}

// ---- layout (rank-based synthetic with natural 3D dispersion) ----

interface BlockLayout {
  x: number;
  z: number;
  heightFrac: number;
}

function computeLayout(blocks: TerrainBlockNode[]): Map<string, BlockLayout> {
  const sorted = [...blocks].sort((a, b) => a.elevation_rank - b.elevation_rank);
  const ranks = blocks.map((b) => b.elevation_rank);
  const minRank = Math.min(...ranks);
  const maxRank = Math.max(...ranks);
  const rankSpan = Math.max(1, maxRank - minRank);
  const n = sorted.length;
  const result = new Map<string, BlockLayout>();

  // Distribute blocks along a gentle hillside curve from peak to valley
  sorted.forEach((node, i) => {
    const t = n === 1 ? 0.3 : i / (n - 1); // 0 (highest) to 1 (lowest)
    const heightFrac = 1 - (node.elevation_rank - minRank) / rankSpan;
    // Radial distance from hill crest
    const dist = 1.0 + t * 6.2;
    // Alternating lateral offset for natural hillside planting rows
    const angle = -Math.PI / 2 + (i % 2 === 0 ? -0.32 : 0.32) * (1 - t * 0.4);
    const x = dist * Math.cos(angle);
    const z = dist * Math.sin(angle);
    result.set(node.block_id, { x, z, heightFrac });
  });

  return result;
}

// ---- Main Component ----

export function TerrainScene({ blocks, edges, onSelectBlock }: TerrainSceneProps) {
  // Polar coords: phi (polar tilt: 0.2 to ~1.4), theta (azimuth)
  const rotationRef = useRef({ x: 1.05, y: 0.5 }); // Initial camera angle showing clear elevation profile
  const velocityRef = useRef({ x: 0, y: 0 });
  const isDraggingRef = useRef(false);
  const autoRotateRef = useRef(true);
  const lastMoveRef = useRef({ x: 0, y: 0, time: 0 });
  const touchStartRef = useRef({ x: 0, y: 0, time: 0 });

  // Compute scene data
  const sceneData = useMemo(() => {
    if (blocks.length === 0) return null;

    const layout = computeLayout(blocks);
    const samples: IDWSample[] = blocks.map((node) => {
      const pos = layout.get(node.block_id)!;
      return { x: pos.x, z: pos.z, height: Math.max(0.4, pos.heightFrac * MAX_HEIGHT) };
    });

    const blockPositions = new Map<string, THREE.Vector3>();
    for (const node of blocks) {
      const pos = layout.get(node.block_id)!;
      const y = heightAt(samples, pos.x, pos.z);
      blockPositions.set(node.block_id, new THREE.Vector3(pos.x, y, pos.z));
    }

    return { layout, samples, blockPositions };
  }, [blocks]);

  // Smooth gesture responder with delta updates
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => false,
        onMoveShouldSetPanResponder: (_e, gs) =>
          Math.abs(gs.dx) > 3 || Math.abs(gs.dy) > 3,
        onPanResponderGrant: (evt: GestureResponderEvent) => {
          isDraggingRef.current = true;
          autoRotateRef.current = false;
          velocityRef.current = { x: 0, y: 0 };
          const locX = evt.nativeEvent.pageX;
          const locY = evt.nativeEvent.pageY;
          lastMoveRef.current = { x: locX, y: locY, time: Date.now() };
          touchStartRef.current = { x: locX, y: locY, time: Date.now() };
        },
        onPanResponderMove: (evt: GestureResponderEvent) => {
          const locX = evt.nativeEvent.pageX;
          const locY = evt.nativeEvent.pageY;
          const deltaX = locX - lastMoveRef.current.x;
          const deltaY = locY - lastMoveRef.current.y;
          const now = Date.now();
          const dt = Math.max(1, now - lastMoveRef.current.time);

          const sensitivity = 0.0055;
          // Invert deltaX so swiping right turns the model right (natural turntable/object rotation)
          rotationRef.current.y -= deltaX * sensitivity;
          rotationRef.current.x = Math.max(
            0.2,
            Math.min(Math.PI / 2.15, rotationRef.current.x - deltaY * sensitivity)
          );

          // Track instantaneous velocity for inertia
          velocityRef.current = {
            x: (deltaY / dt) * sensitivity * 12,
            y: -(deltaX / dt) * sensitivity * 12,
          };

          lastMoveRef.current = { x: locX, y: locY, time: now };
        },
        onPanResponderRelease: () => {
          isDraggingRef.current = false;
        },
        onPanResponderTerminate: () => {
          isDraggingRef.current = false;
        },
      }),
    []
  );

  if (blocks.length === 0 || !sceneData) {
    return null;
  }

  return (
    <View style={{ flex: 1 }} {...panResponder.panHandlers}>
      <Canvas
        camera={{ position: [14, 13, 14], fov: 42, near: 0.1, far: 100 }}
        style={{ flex: 1 }}
      >
        <ambientLight intensity={0.55} color={0xdfe9d8} />
        <directionalLight position={[10, 16, 8]} intensity={1.1} color={0xfff8ea} />
        <directionalLight position={[-8, 6, -8]} intensity={0.3} color={0xaec4aa} />

        <SceneCameraController
          rotationRef={rotationRef}
          velocityRef={velocityRef}
          isDraggingRef={isDraggingRef}
          autoRotateRef={autoRotateRef}
        />

        <group>
          {/* Diorama shadow-catcher base plate */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.6, 0]}>
            <planeGeometry args={[50, 50]} />
            <meshStandardMaterial color={0xede9e1} roughness={1} />
          </mesh>

          {/* Terraced 3D terrain island with rock cliff risers */}
          <TerrainMesh samples={sceneData.samples} />

          {/* Diorama bedrock pedestal skirt */}
          <TerrainPedestal />

          {/* Blocks rendered as clusters of vines (mini pepper plots) */}
          {blocks.map((block) => {
            const pos = sceneData.blockPositions.get(block.block_id);
            if (!pos) return null;
            return (
              <VineClusterBlock
                key={block.block_id}
                position={pos}
                state={block.current_state}
                rank={block.elevation_rank}
                onPress={() => onSelectBlock(block.block_id)}
              />
            );
          })}

          {/* Directional 3D water drainage arrows */}
          {edges.map((edge) => {
            const from = sceneData.blockPositions.get(edge.from_block_id);
            const to = sceneData.blockPositions.get(edge.to_block_id);
            if (!from || !to) return null;
            return (
              <DrainageFlowVector
                key={`${edge.from_block_id}->${edge.to_block_id}`}
                from={from}
                to={to}
                weight={edge.flow_weight ?? 0.6}
                barrier={!!edge.barrier}
              />
            );
          })}
        </group>
      </Canvas>
    </View>
  );
}

// ---- Camera Controller (runs at 60 FPS in useFrame without re-rendering) ----

function SceneCameraController({
  rotationRef,
  velocityRef,
  isDraggingRef,
  autoRotateRef,
}: {
  rotationRef: React.MutableRefObject<{ x: number; y: number }>;
  velocityRef: React.MutableRefObject<{ x: number; y: number }>;
  isDraggingRef: React.MutableRefObject<boolean>;
  autoRotateRef: React.MutableRefObject<boolean>;
}) {
  const { camera } = useThree();
  const target = useMemo(() => new THREE.Vector3(0, 1.2, -2.8), []);

  useFrame(() => {
    // Only apply inertial velocity when NOT dragging (prevents jitter/fighting)
    if (!isDraggingRef.current) {
      const damping = 0.93;
      velocityRef.current.x *= damping;
      velocityRef.current.y *= damping;

      if (Math.abs(velocityRef.current.x) > 0.0001 || Math.abs(velocityRef.current.y) > 0.0001) {
        rotationRef.current.x = Math.max(
          0.2,
          Math.min(Math.PI / 2.15, rotationRef.current.x - velocityRef.current.x)
        );
        rotationRef.current.y += velocityRef.current.y;
      } else if (autoRotateRef.current) {
        // Slow peaceful ambient orbit
        rotationRef.current.y += 0.0018;
      }
    }

    // Spherical orbit around target
    const radius = 21;
    const phi = rotationRef.current.x;
    const theta = rotationRef.current.y;

    camera.position.set(
      target.x + radius * Math.sin(phi) * Math.sin(theta),
      target.y + radius * Math.cos(phi),
      target.z + radius * Math.sin(phi) * Math.cos(theta)
    );
    camera.lookAt(target);
  });

  return null;
}

// ---- Terraced 3D Terrain Mesh with Riser Highlighting ----

function TerrainMesh({ samples }: { samples: IDWSample[] }) {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(PLANE_SIZE, PLANE_SIZE, SEGMENTS, SEGMENTS);
    geo.rotateX(-Math.PI / 2);

    const pos = geo.attributes.position;
    const rawHeights = new Float32Array(pos.count);

    // 1. Calculate stepped terrace heights
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      let h = samples.length ? idwHeight(x, z, samples) : 0;

      // Island radial tapering
      const distFromCentre = Math.sqrt(x * x + z * z);
      if (distFromCentre > ISLAND_RADIUS) {
        const outer = PLANE_SIZE / 2;
        const t = Math.min(1, (distFromCentre - ISLAND_RADIUS) / (outer - ISLAND_RADIUS));
        h *= 1 - t;
      }

      // Topographic terracing
      const stepped = Math.floor(h / STEP_HEIGHT) * STEP_HEIGHT;
      pos.setY(i, stepped);
      rawHeights[i] = stepped;
    }

    // Convert to non-indexed so each face has independent vertex normals & colors
    const flat = geo.toNonIndexed();
    flat.computeVertexNormals();

    const flatPos = flat.attributes.position;
    const flatNormals = flat.attributes.normal;
    const vertexColours = new Float32Array(flatPos.count * 3);

    // 2. Vertex coloring with terrace step contrast
    for (let i = 0; i < flatPos.count; i++) {
      const y = flatPos.getY(i);
      const ny = flatNormals.getY(i); // Vertical normal component

      const [gr, gg, gb] = elevationColour(y / MAX_HEIGHT);

      // If face is steep (a terrace cliff/riser, ny < 0.7), blend in earthy rock tone
      if (ny < 0.72) {
        const steepness = Math.max(0, 1 - ny);
        const rockBlend = Math.min(0.65, steepness * 0.7);
        vertexColours[i * 3] = gr * (1 - rockBlend) + ROCK_TINT[0] * rockBlend;
        vertexColours[i * 3 + 1] = gg * (1 - rockBlend) + ROCK_TINT[1] * rockBlend;
        vertexColours[i * 3 + 2] = gb * (1 - rockBlend) + ROCK_TINT[2] * rockBlend;
      } else {
        vertexColours[i * 3] = gr;
        vertexColours[i * 3 + 1] = gg;
        vertexColours[i * 3 + 2] = gb;
      }
    }

    flat.setAttribute("color", new THREE.BufferAttribute(vertexColours, 3));
    return flat;
  }, [samples]);

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial vertexColors flatShading roughness={0.88} />
    </mesh>
  );
}

// ---- Diorama Pedestal Skirt ----

function TerrainPedestal() {
  const pedestalGeo = useMemo(() => {
    // Cylindrical bedrock skirt under the island
    const geo = new THREE.CylinderGeometry(ISLAND_RADIUS + 0.1, ISLAND_RADIUS + 0.3, 0.6, 48, 1, false);
    return geo;
  }, []);

  return (
    <mesh position={[0, -0.3, 0]} geometry={pedestalGeo}>
      <meshStandardMaterial color={0x3a332a} roughness={0.95} flatShading />
    </mesh>
  );
}

// ---- Authentic Block of Pepper Vines (Vine Cluster) ----

/**
 * Depicts a BLOCK (parcel of vines) rather than a single lone vine:
 *   - Raised circular agricultural soil bed (mound)
 *   - 5 wooden tiang climbing poles (4 perimeter + 1 center)
 *   - Bushy pepper foliage wrapping each pole, tinted by state
 *   - Translucent soil-core cylinder beneath representing root-zone health
 *   - Top badge indicator for elevation rank
 */
function VineClusterBlock({
  position,
  state,
  rank,
  onPress,
}: {
  position: THREE.Vector3;
  state: string;
  rank: number;
  onPress: () => void;
}) {
  const colour = STATE_COLOR[state] ?? STATE_COLOR.protected;

  const foliageMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: colour, flatShading: true, roughness: 0.9 }),
    [colour]
  );

  const postMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: 0x6e4e37, flatShading: true, roughness: 1.0 }),
    [colour]
  );

  const soilMoundMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: 0x4a3b2c, roughness: 0.92, flatShading: true }),
    []
  );

  const coreMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: colour,
        transparent: true,
        opacity: 0.28,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    [colour]
  );

  // 5 Tiang poles arrangement within the agricultural block
  const TIANG_POSITIONS: [number, number, number][] = [
    [0, 0, 0],          // center pole
    [-0.34, 0, -0.34],  // NW pole
    [0.34, 0, -0.34],   // NE pole
    [-0.34, 0, 0.34],   // SW pole
    [0.34, 0, 0.34],    // SE pole
  ];

  return (
    <group position={[position.x, position.y, position.z]}>
      {/* Translucent subterranean disease/soil core */}
      <mesh position={[0, -1.1, 0]} material={coreMat}>
        <cylinderGeometry args={[0.7, 0.7, 2.2, 20, 1, true]} />
      </mesh>

      {/* Raised circular agricultural planting mound */}
      <mesh position={[0, 0.1, 0]} material={soilMoundMat}>
        <cylinderGeometry args={[0.75, 0.88, 0.22, 16]} />
      </mesh>

      {/* 5 Pepper Tiangs (posts) with climbing bushy vine foliage */}
      {TIANG_POSITIONS.map(([tx, _, tz], idx) => (
        <group key={idx} position={[tx, 0.2, tz]}>
          {/* Wooden tiang post */}
          <mesh position={[0, 0.6, 0]} material={postMat}>
            <cylinderGeometry args={[0.032, 0.042, 1.2, 6]} />
          </mesh>

          {/* Lower vine foliage */}
          <mesh position={[0, 0.45, 0]} material={foliageMat}>
            <dodecahedronGeometry args={[0.18]} />
          </mesh>

          {/* Mid vine foliage */}
          <mesh position={[0.04, 0.75, -0.03]} material={foliageMat}>
            <dodecahedronGeometry args={[0.22]} />
          </mesh>

          {/* Top vine canopy */}
          <mesh position={[-0.02, 1.05, 0.02]} material={foliageMat}>
            <dodecahedronGeometry args={[0.24]} />
          </mesh>
        </group>
      ))}

      {/* Floating elevation rank beacon */}
      <mesh position={[0, 1.7, 0]}>
        <cylinderGeometry args={[0.16, 0.16, 0.06, 12]} />
        <meshStandardMaterial color={colour} />
      </mesh>

      {/* Tap target sphere for smooth interaction */}
      <mesh
        position={[0, 0.9, 0]}
        onPointerDown={(e) => {
          e.stopPropagation();
          onPress();
        }}
      >
        <sphereGeometry args={[1.0, 8, 8]} />
        <meshBasicMaterial visible={false} />
      </mesh>
    </group>
  );
}

// ---- Directional 3D Water Drainage Flow Vector ----

/**
 * Visualizes water drainage flow with clear directional arrows pointing
 * downhill from high elevation to low elevation.
 */
function DrainageFlowVector({
  from,
  to,
  weight,
  barrier,
}: {
  from: THREE.Vector3;
  to: THREE.Vector3;
  weight: number;
  barrier: boolean;
}) {
  const lift = 0.2;
  const start = useMemo(() => new THREE.Vector3(from.x, from.y + lift, from.z), [from.x, from.y, from.z]);
  const end = useMemo(() => new THREE.Vector3(to.x, to.y + lift, to.z), [to.x, to.y, to.z]);

  const dir = useMemo(() => new THREE.Vector3().subVectors(end, start), [start, end]);
  const length = useMemo(() => dir.length(), [dir]);
  const normDir = useMemo(() => dir.clone().normalize(), [dir]);

  // Orientation quaternion for aligning arrow cones along the flow vector
  const quaternion = useMemo(() => {
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    q.setFromUnitVectors(up, normDir);
    return q;
  }, [normDir]);

  const flowColor = barrier ? 0x94a3b8 : 0x2563eb; // Slate grey if barrier, bright water blue if active flow
  const arrowColor = barrier ? 0x64748b : 0x3b82f6;

  // Arrow position at 62% along the vector towards downstream
  const arrowPos = useMemo(() => {
    return new THREE.Vector3().lerpVectors(start, end, 0.62);
  }, [start, end]);

  // Cylinder line midpoint
  const lineMid = useMemo(() => {
    return new THREE.Vector3().lerpVectors(start, end, 0.5);
  }, [start, end]);

  return (
    <group>
      {/* 3D Flow Channel (visible on all mobile screens, not 1px WebGL line) */}
      <mesh position={lineMid} quaternion={quaternion}>
        <cylinderGeometry args={[0.045, 0.045, Math.max(0.1, length - 0.5), 8]} />
        <meshStandardMaterial
          color={flowColor}
          transparent
          opacity={barrier ? 0.35 : Math.max(0.5, weight)}
          roughness={0.3}
        />
      </mesh>

      {/* Prominent Directional Arrowhead pointing downhill */}
      <mesh position={arrowPos} quaternion={quaternion}>
        <coneGeometry args={[0.18, 0.42, 10]} />
        <meshStandardMaterial color={arrowColor} roughness={0.3} />
      </mesh>

      {/* Barrier crossbar marker if water drainage is blocked */}
      {barrier && (
        <mesh position={arrowPos}>
          <boxGeometry args={[0.4, 0.25, 0.08]} />
          <meshStandardMaterial color={0xef4444} roughness={0.6} />
        </mesh>
      )}
    </group>
  );
}
