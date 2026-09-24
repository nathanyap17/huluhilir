/**
 * International barometric formula, relative to a session baseline pressure
 * rather than sea level -- only the DIFFERENCE between blocks matters here,
 * never an absolute altitude (docs/DATA_MODEL.md §3 baseline_pressure_hpa is
 * "reference for all relative altitude").
 *
 * Sign convention must match backend/app/tools/graph.py's
 * resolve_elevation_ranks: it sorts by baro_rel_m DESCENDING for rank 1 =
 * highest, so a higher baro_rel_m must mean higher elevation. Pressure drops
 * as altitude rises, so this returns a POSITIVE value when currentHpa is
 * below baselineHpa.
 */
export function relativeAltitudeM(currentHpa: number, baselineHpa: number): number {
  return 44330 * (1 - Math.pow(currentHpa / baselineHpa, 1 / 5.255));
}
