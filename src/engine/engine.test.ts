/**
 * Fast-feedback unit tests for TypeScript SSA Engine using node:test.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { Vec3, ViewParams, project, unprojectGround, rayAabb } from './geometry';
import { solarPosition, sunVector } from './solar';
import { ScenarioState, createDemoScenario } from './scenario';
import { computeHeatmapSync, compareHeatmaps } from './heatmap';

test('Solar: S1 Equinox noon (Lahore 2024-03-21 12:00)', () => {
  const sun = solarPosition(31.5204, 74.3587, 2024, 3, 21, 720, 5.0);
  assert.ok(Math.abs(sun.azimuthDeg - 175.0) <= 2.0, `Azimuth ${sun.azimuthDeg} out of 175±2`);
  assert.ok(Math.abs(sun.elevationDeg - 58.8) <= 1.0, `Elevation ${sun.elevationDeg} out of 58.8±1`);
});

test('Solar: S4 Night check (Lahore 2024-03-21 02:00)', () => {
  const sun = solarPosition(31.5204, 74.3587, 2024, 3, 21, 120, 5.0);
  assert.ok(sun.elevationDeg < 0.0);
  assert.equal(sun.isDaytime, false);
  assert.equal(sun.shadowsActive, false);
});

test('Solar: Sun vector East check', () => {
  const s = sunVector(90.0, 0.0);
  assert.ok(Math.abs(s.x - 1.0) < 1e-6);
  assert.ok(Math.abs(s.y) < 1e-6);
  assert.ok(Math.abs(s.z) < 1e-6);
});

test('Geometry: Isometric projection matrix', () => {
  const view = new ViewParams(45.0, 35.264, 1.0, [0, 0]);
  const p100 = project(new Vec3(1, 0, 0), view);
  const p001 = project(new Vec3(0, 0, 1), view);

  assert.ok(Math.abs(p100[0] - 0.7071) < 1e-3);
  assert.ok(Math.abs(p100[1] - -0.4082) < 1e-3);
  assert.ok(Math.abs(p001[0] - 0.0) < 1e-3);
  assert.ok(Math.abs(p001[1] - -0.8165) < 1e-3);
});

test('Geometry: Ground unproject invertibility', () => {
  const view = new ViewParams(45.0, 35.264, 12.0, [300, 250]);
  const pt = new Vec3(18.5, 24.2, 0.0);
  const screen = project(pt, view);
  const unproj = unprojectGround(screen[0], screen[1], view);
  assert.ok(Math.abs(unproj[0] - pt.x) < 1e-6);
  assert.ok(Math.abs(unproj[1] - pt.y) < 1e-6);
});

test('Geometry: Ray-AABB slab intersection', () => {
  const bMin = new Vec3(10, 10, 0);
  const bMax = new Vec3(14, 14, 10);
  const s = sunVector(225, 45); // pointing southwest & up

  const hit1 = rayAabb(new Vec3(16, 16, 0.001), s, bMin, bMax);
  const hit2 = rayAabb(new Vec3(16, 8, 0.001), s, bMin, bMax);

  assert.ok(hit1 !== null && Math.abs(hit1 - 4.0) < 0.1);
  assert.equal(hit2, null);
});

test('Scenario: canPlace rejects overlap & out of bounds', () => {
  const sc = new ScenarioState();
  sc.addBuilding({
    id: 1,
    label: 'B1',
    position: new Vec3(10, 10, 0),
    size: new Vec3(10, 10, 10),
    color: '#D98E73',
  });

  assert.equal(sc.canPlace(new Vec3(15, 15, 0), new Vec3(6, 6, 5)), false);
  assert.equal(sc.canPlace(new Vec3(55, 55, 0), new Vec3(10, 10, 5)), false);
  assert.equal(sc.canPlace(new Vec3(30, 30, 0), new Vec3(10, 10, 5)), true);
});

test('Heatmap: Identity compare(A, A) and antisymmetry', () => {
  const sc = createDemoScenario('A');
  const gridA = computeHeatmapSync(sc, 2024, 3, 21, 500, 700, 30);
  const cmpSelf = compareHeatmaps(gridA, gridA);
  assert.equal(cmpSelf.deltaHours, 0);

  const scB = sc.clone('B');
  scB.setBuildingHeight(1, 35);
  const gridB = computeHeatmapSync(scB, 2024, 3, 21, 500, 700, 30);
  const cmpAB = compareHeatmaps(gridA, gridB);
  const cmpBA = compareHeatmaps(gridB, gridA);

  assert.ok(Math.abs(cmpAB.deltaHours + cmpBA.deltaHours) < 1e-6);
});
