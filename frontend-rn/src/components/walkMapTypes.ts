/** Split out from WalkMapView.tsx so SafeWalkMapView.tsx can import these
 * types without pulling in expo-maps at module-eval time. */
export interface WalkMapBlock {
  block_id: string;
  label: string;
  lat: number;
  lon: number;
  rank?: number;
}

export interface WalkMapViewProps {
  track: { lat: number; lon: number }[];
  blocks: WalkMapBlock[];
  current: { lat: number; lon: number } | null;
}
