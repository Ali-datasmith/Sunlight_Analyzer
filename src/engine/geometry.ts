/**
 * Geometry engine in TypeScript for Sunlight & Shadow Analyzer.
 * Matches geometry.py algorithms (Kay-Kajiya Ray-AABB, Andrew's monotone chain,
 * Sutherland-Hodgman clipping, and isometric axonometric projection).
 */

export const EPS = 1e-9;
export const T_MIN = 1e-4;
export const EL_MIN_DEG = 2.0;

export class Vec3 {
  x: number;
  y: number;
  z: number;

  constructor(x = 0, y = 0, z = 0) {
    this.x = x;
    this.y = y;
    this.z = z;
  }

  add(other: Vec3): Vec3 {
    return new Vec3(this.x + other.x, this.y + other.y, this.z + other.z);
  }

  sub(other: Vec3): Vec3 {
    return new Vec3(this.x - other.x, this.y - other.y, this.z - other.z);
  }

  mul(scalar: number): Vec3 {
    return new Vec3(this.x * scalar, this.y * scalar, this.z * scalar);
  }

  dot(other: Vec3): number {
    return this.x * other.x + this.y * other.y + this.z * other.z;
  }

  lengthSq(): number {
    return this.x * this.x + this.y * this.y + this.z * this.z;
  }

  length(): number {
    return Math.sqrt(this.lengthSq());
  }

  normalized(): Vec3 {
    const len = this.length();
    if (len < EPS) return new Vec3(0, 0, 0);
    return new Vec3(this.x / len, this.y / len, this.z / len);
  }
}

export class ViewParams {
  yawDeg: number;
  pitchDeg: number;
  scalePxPerM: number;
  originPx: [number, number];
  cosYaw: number;
  sinYaw: number;
  cosPitch: number;
  sinPitch: number;

  constructor(
    yawDeg = 45.0,
    pitchDeg = 35.264,
    scalePxPerM = 10.0,
    originPx: [number, number] = [300, 300]
  ) {
    this.yawDeg = yawDeg;
    this.pitchDeg = pitchDeg;
    this.scalePxPerM = scalePxPerM;
    this.originPx = originPx;

    const radYaw = (yawDeg * Math.PI) / 180.0;
    const radPitch = (pitchDeg * Math.PI) / 180.0;
    this.cosYaw = Math.cos(radYaw);
    this.sinYaw = Math.sin(radYaw);
    this.cosPitch = Math.cos(radPitch);
    this.sinPitch = Math.sin(radPitch);
  }
}

export function project(p: Vec3, view: ViewParams): [number, number] {
  const xr = p.x * view.cosYaw - p.y * view.sinYaw;
  const yr = p.x * view.sinYaw + p.y * view.cosYaw;
  const k = view.scalePxPerM;
  const [ox, oy] = view.originPx;
  const sx = ox + k * xr;
  const sy = oy - k * (yr * view.sinPitch + p.z * view.cosPitch);
  return [sx, sy];
}

export function unprojectGround(sx: number, sy: number, view: ViewParams): [number, number] {
  const k = view.scalePxPerM;
  if (Math.abs(k) < EPS || Math.abs(view.sinPitch) < EPS) return [0, 0];
  const [ox, oy] = view.originPx;
  const xr = (sx - ox) / k;
  const yr = -(sy - oy) / (k * view.sinPitch);
  const x = xr * view.cosYaw + yr * view.sinYaw;
  const y = -xr * view.sinYaw + yr * view.cosYaw;
  return [x, y];
}

export function depthKey(p: Vec3, view: ViewParams): number {
  const yr = p.x * view.sinYaw + p.y * view.cosYaw;
  return yr * view.cosPitch - p.z * view.sinPitch;
}

export function fitView(
  canvasW: number,
  canvasH: number,
  groundW: number,
  groundD: number,
  maxH: number,
  yawDeg = 45.0,
  pitchDeg = 35.264
): ViewParams {
  const unitView = new ViewParams(yawDeg, pitchDeg, 1.0, [0, 0]);
  const corners = [
    new Vec3(0, 0, 0),
    new Vec3(groundW, 0, 0),
    new Vec3(groundW, groundD, 0),
    new Vec3(0, groundD, 0),
    new Vec3(0, 0, maxH),
    new Vec3(groundW, 0, maxH),
    new Vec3(groundW, groundD, maxH),
    new Vec3(0, groundD, maxH),
  ];

  const projs = corners.map((c) => project(c, unitView));
  const minX = Math.min(...projs.map((p) => p[0]));
  const maxX = Math.max(...projs.map((p) => p[0]));
  const minY = Math.min(...projs.map((p) => p[1]));
  const maxY = Math.max(...projs.map((p) => p[1]));

  const spanX = Math.max(1.0, maxX - minX);
  const spanY = Math.max(1.0, maxY - minY);

  const pad = 0.88;
  const kX = (canvasW * pad) / spanX;
  const kY = (canvasH * pad) / spanY;
  const scale = Math.min(kX, kY);

  const scaledView = new ViewParams(yawDeg, pitchDeg, scale, [0, 0]);
  const projsScaled = corners.map((c) => project(c, scaledView));
  const sMinX = Math.min(...projsScaled.map((p) => p[0]));
  const sMaxX = Math.max(...projsScaled.map((p) => p[0]));
  const sMinY = Math.min(...projsScaled.map((p) => p[1]));
  const sMaxY = Math.max(...projsScaled.map((p) => p[1]));

  const centerX = (sMinX + sMaxX) * 0.5;
  const centerY = (sMinY + sMaxY) * 0.5;

  const ox = canvasW * 0.5 - centerX;
  const oy = canvasH * 0.5 - centerY;

  return new ViewParams(yawDeg, pitchDeg, scale, [ox, oy]);
}

export function rayAabb(origin: Vec3, direction: Vec3, boxMin: Vec3, boxMax: Vec3): number | null {
  let tNear = -1e30;
  let tFar = 1e30;

  const origCoords = [origin.x, origin.y, origin.z];
  const dirCoords = [direction.x, direction.y, direction.z];
  const bMinCoords = [boxMin.x, boxMin.y, boxMin.z];
  const bMaxCoords = [boxMax.x, boxMax.y, boxMax.z];

  for (let a = 0; a < 3; a++) {
    const oa = origCoords[a];
    const da = dirCoords[a];
    const bMin = bMinCoords[a];
    const bMax = bMaxCoords[a];

    if (Math.abs(da) < EPS) {
      if (oa < bMin || oa > bMax) return null;
    } else {
      const invD = 1.0 / da;
      const t1 = (bMin - oa) * invD;
      const t2 = (bMax - oa) * invD;
      const lo = Math.min(t1, t2);
      const hi = Math.max(t1, t2);
      if (lo > tNear) tNear = lo;
      if (hi < tFar) tFar = hi;
      if (tNear > tFar || tFar < T_MIN) return null;
    }
  }

  if (tNear > tFar || tFar < T_MIN) return null;
  return Math.max(tNear, T_MIN);
}

function cross2d(o: [number, number], a: [number, number], b: [number, number]): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}

export function convexHull2d(points: [number, number][]): [number, number][] {
  const pts = Array.from(new Set(points.map((p) => `${p[0]},${p[1]}`)))
    .map((s) => s.split(',').map(Number) as [number, number])
    .sort((a, b) => (a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]));

  if (pts.length <= 1) return pts;

  const lower: [number, number][] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross2d(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }

  const upper: [number, number][] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross2d(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }

  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

export function clipPolygonToRect(
  poly: [number, number][],
  xMin: number,
  yMin: number,
  xMax: number,
  yMax: number
): [number, number][] {
  if (poly.length === 0) return [];
  let output = [...poly];

  const edges: Array<{ type: string; boundary: number }> = [
    { type: 'left', boundary: xMin },
    { type: 'right', boundary: xMax },
    { type: 'bottom', boundary: yMin },
    { type: 'top', boundary: yMax },
  ];

  for (const edge of edges) {
    const inputList = output;
    output = [];
    if (inputList.length === 0) break;

    let s = inputList[inputList.length - 1];
    for (const e of inputList) {
      let insideE = false;
      let insideS = false;
      if (edge.type === 'left') {
        insideE = e[0] >= edge.boundary;
        insideS = s[0] >= edge.boundary;
      } else if (edge.type === 'right') {
        insideE = e[0] <= edge.boundary;
        insideS = s[0] <= edge.boundary;
      } else if (edge.type === 'bottom') {
        insideE = e[1] >= edge.boundary;
        insideS = s[1] >= edge.boundary;
      } else if (edge.type === 'top') {
        insideE = e[1] <= edge.boundary;
        insideS = s[1] <= edge.boundary;
      }

      if (insideE) {
        if (insideS) {
          output.push(e);
        } else {
          const inter = lineIntersectEdge(s, e, edge.type, edge.boundary);
          if (inter) output.push(inter);
          output.push(e);
        }
      } else if (insideS) {
        const inter = lineIntersectEdge(s, e, edge.type, edge.boundary);
        if (inter) output.push(inter);
      }
      s = e;
    }
  }

  return output;
}

function lineIntersectEdge(
  p1: [number, number],
  p2: [number, number],
  edgeType: string,
  boundary: number
): [number, number] | null {
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  if (edgeType === 'left' || edgeType === 'right') {
    if (Math.abs(dx) < EPS) return null;
    const t = (boundary - p1[0]) / dx;
    return [boundary, p1[1] + t * dy];
  } else {
    if (Math.abs(dy) < EPS) return null;
    const t = (boundary - p1[1]) / dy;
    return [p1[0] + t * dx, boundary];
  }
}

export function pointInConvexPolygon(px: number, py: number, poly: [number, number][]): boolean {
  const n = poly.length;
  if (n < 3) return false;
  let sign = 0;
  const p: [number, number] = [px, py];

  for (let i = 0; i < n; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % n];
    const c = cross2d(a, b, p);
    if (Math.abs(c) < EPS) continue;
    const curSign = c > 0 ? 1 : -1;
    if (sign === 0) sign = curSign;
    else if (sign !== curSign) return false;
  }
  return true;
}

export function shadowPolygon(
  bMin: Vec3,
  bMax: Vec3,
  sunVec: Vec3,
  groundW: number,
  groundD: number
): [number, number][] {
  if (sunVec.z < Math.sin((EL_MIN_DEG * Math.PI) / 180.0)) return [];

  const corners: Vec3[] = [
    new Vec3(bMin.x, bMin.y, bMin.z),
    new Vec3(bMax.x, bMin.y, bMin.z),
    new Vec3(bMax.x, bMax.y, bMin.z),
    new Vec3(bMin.x, bMax.y, bMin.z),
    new Vec3(bMin.x, bMin.y, bMax.z),
    new Vec3(bMax.x, bMin.y, bMax.z),
    new Vec3(bMax.x, bMax.y, bMax.z),
    new Vec3(bMin.x, bMax.y, bMax.z),
  ];

  const sz = sunVec.z;
  const projPts: [number, number][] = corners.map((c) => [
    c.x - c.z * (sunVec.x / sz),
    c.y - c.z * (sunVec.y / sz),
  ]);

  const hull = convexHull2d(projPts);
  return clipPolygonToRect(hull, 0, 0, groundW, groundD);
}
