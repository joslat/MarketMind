import { feature } from "topojson-client";
import landTopo from "world-atlas/land-110m.json";

// Equirectangular projection: degrees -> graph-coordinate units (shared by nodes + basemap so they align).
const K = 4.2;
export function project(lng: number, lat: number): [number, number] {
  return [lng * K, -lat * K];
}

// decode the world landmass once into a flat list of polygons (each = array of rings),
// robust to Feature / FeatureCollection / Polygon / MultiPolygon shapes.
function polysFrom(geom: any): number[][][][] {
  if (!geom) return [];
  if (geom.type === "Polygon") return [geom.coordinates];
  if (geom.type === "MultiPolygon") return geom.coordinates;
  return [];
}
const decoded: any = feature(landTopo as any, (landTopo as any).objects.land);
const LAND_POLYS: number[][][][] =
  decoded.type === "FeatureCollection"
    ? decoded.features.flatMap((f: any) => polysFrom(f.geometry))
    : polysFrom(decoded.geometry);

/** Draw the dark world basemap + graticule in graph coordinates (call from onRenderFramePre). */
export function drawBasemap(ctx: CanvasRenderingContext2D) {
  ctx.save();
  // landmass fill
  ctx.beginPath();
  for (const poly of LAND_POLYS) {
    for (const ring of poly) {
      ring.forEach(([lng, lat], i) => {
        const [x, y] = project(lng, lat);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.closePath();
    }
  }
  ctx.fillStyle = "rgba(24,34,50,0.62)";
  ctx.fill();
  ctx.strokeStyle = "rgba(70,100,140,0.30)";
  ctx.lineWidth = 0.45;
  ctx.stroke();

  // graticule
  ctx.strokeStyle = "rgba(40,55,78,0.35)";
  ctx.lineWidth = 0.22;
  for (let lng = -180; lng <= 180; lng += 30) {
    ctx.beginPath();
    for (let lat = -82; lat <= 82; lat += 2) {
      const [x, y] = project(lng, lat);
      lat === -82 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  for (let lat = -60; lat <= 80; lat += 30) {
    ctx.beginPath();
    for (let lng = -180; lng <= 180; lng += 2) {
      const [x, y] = project(lng, lat);
      lng === -180 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();
}

// region labels for the geo-biased read (drawn faintly)
export const REGIONS: { label: string; lng: number; lat: number }[] = [
  { label: "US · WEST TECH", lng: -120, lat: 42 },
  { label: "EU", lng: 8, lat: 54 },
  { label: "EAST-ASIA CHIP BELT", lng: 122, lat: 38 },
];
