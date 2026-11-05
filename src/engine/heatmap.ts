/**
 * Heatmap calculation and comparison engine in TypeScript.
 */

import { Vec3, rayAabb, EL_MIN_DEG } from './geometry';
import { ScenarioState } from './scenario';
import { solarPosition, sunVector } from './solar';

export interface HeatmapGridData {
  resolution: [number, number];
  cellSizeM: number;
  hoursArray: number[][]; // -1 indicates footprint
  maxHours: number;
  scenarioRevision: number;
}

export function computeHeatmapSync(
  scenario: ScenarioState,
  year: number,
  month: number,
  day: number,
  tStartMin: number,
  tEndMin: number,
  stepMin = 15,
  onProgress?: (progress: number) => void
): HeatmapGridData {
  const [nx, ny] = scenario.groundSize;
  const cs = scenario.cellSizeM;
  const hoursArray: number[][] = Array.from({ length: ny }, () => Array(nx).fill(0.0));

  // Identify footprint cells
  const groundSamples: Array<{ i: number; j: number; pt: Vec3 }> = [];
  for (let j = 0; j < ny; j++) {
    const cy = (j + 0.5) * cs;
    for (let i = 0; i < nx; i++) {
      const cx = (i + 0.5) * cs;
      let occupied = false;
      for (const b of scenario.buildings) {
        if (
          cx >= b.position.x &&
          cx <= b.position.x + b.size.x &&
          cy >= b.position.y &&
          cy <= b.position.y + b.size.y
        ) {
          occupied = true;
          break;
        }
      }

      if (occupied) {
        hoursArray[j][i] = -1.0;
      } else {
        groundSamples.push({ i, j, pt: new Vec3(cx, cy, 0.001) });
      }
    }
  }

  const span = Math.max(0, tEndMin - tStartMin);
  const numSamples = Math.max(1, Math.ceil(span / stepMin));
  const w = stepMin / 60.0;

  const boxes = scenario.buildings.map((b) => ({
    bMin: b.position,
    bMax: new Vec3(b.position.x + b.size.x, b.position.y + b.size.y, b.position.z + b.size.z),
  }));

  for (let s = 0; s < numSamples; s++) {
    const tK = tStartMin + (s + 0.5) * stepMin;
    const minute = Math.round(tK);
    const sun = solarPosition(scenario.lat, scenario.lon, year, month, day, minute, scenario.tzOffset);

    if (sun.elevationDeg >= EL_MIN_DEG) {
      const sVec = sunVector(sun.azimuthDeg, sun.elevationDeg);
      for (const sample of groundSamples) {
        let occluded = false;
        for (const box of boxes) {
          if (rayAabb(sample.pt, sVec, box.bMin, box.bMax) !== null) {
            occluded = true;
            break;
          }
        }
        if (!occluded) {
          hoursArray[sample.j][sample.i] += w;
        }
      }
    }

    if (onProgress && s % 5 === 0) {
      onProgress((s + 1) / numSamples);
    }
  }

  let maxH = 0.0;
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      if (hoursArray[j][i] > maxH) maxH = hoursArray[j][i];
    }
  }

  return {
    resolution: [nx, ny],
    cellSizeM: cs,
    hoursArray,
    maxHours: maxH,
    scenarioRevision: scenario.revision,
  };
}

export function compareHeatmaps(
  gridA: HeatmapGridData,
  gridB: HeatmapGridData,
  targetHours = 2.0
) {
  const [nx, ny] = gridA.resolution;
  const cs = gridA.cellSizeM;
  const diffArray: number[][] = Array.from({ length: ny }, () => Array(nx).fill(-999.0));

  let commonCells = 0;
  let sumHoursA = 0.0;
  let sumHoursB = 0.0;
  let cellsGained = 0;
  let cellsLost = 0;
  let targetPassA = 0;
  let targetPassB = 0;
  const tau = 0.25;

  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const a = gridA.hoursArray[j][i];
      const b = gridB.hoursArray[j][i];
      if (a >= 0.0 && b >= 0.0) {
        commonCells++;
        sumHoursA += a;
        sumHoursB += b;
        const diff = b - a;
        diffArray[j][i] = diff;
        if (diff > tau) cellsGained++;
        else if (diff < -tau) cellsLost++;

        if (a >= targetHours) targetPassA++;
        if (b >= targetHours) targetPassB++;
      }
    }
  }

  const deltaHours = sumHoursB - sumHoursA;
  const areaHours = deltaHours * (cs * cs);
  const pctChange = sumHoursA > 1e-6 ? (100.0 * deltaHours) / sumHoursA : 0.0;
  const targetFracA = commonCells > 0 ? targetPassA / commonCells : 0;
  const targetFracB = commonCells > 0 ? targetPassB / commonCells : 0;

  return {
    commonCells,
    sumHoursA,
    sumHoursB,
    deltaHours,
    areaHours,
    pctChange,
    cellsGained,
    cellsLost,
    targetHours,
    targetFracA,
    targetFracB,
    diffArray,
  };
}
