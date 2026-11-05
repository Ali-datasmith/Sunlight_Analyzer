/**
 * Building and Scenario models in TypeScript.
 */

import { Vec3 } from './geometry';

export const CELL_SIZE_M = 2.0;
export const GROUND_CELLS: [number, number] = [30, 30]; // 60x60m
export const MAX_BUILDINGS = 15;

export const BUILDING_PALETTE = [
  '#D98E73',
  '#8FB8DE',
  '#E6C65C',
  '#9CC59A',
  '#B7A1D1',
  '#C9C9C9',
];

export const CITY_PRESETS: Record<string, [number, number, number]> = {
  Lahore: [31.5204, 74.3587, 5.0],
  Karachi: [24.8607, 67.0011, 5.0],
  Islamabad: [33.6844, 73.0479, 5.0],
  London: [51.5074, -0.1278, 0.0],
  'New York': [40.7128, -74.006, -5.0],
  Sydney: [-33.8688, 151.2093, 10.0],
};

export interface BuildingData {
  id: number;
  label: string;
  position: Vec3;
  size: Vec3;
  color: string;
}

export class ScenarioState {
  name: string;
  groundSize: [number, number];
  lat: number;
  lon: number;
  tzOffset: number;
  cellSizeM: number;
  buildings: BuildingData[];
  nextId: number;
  revision: number;

  constructor(
    name = 'A',
    groundSize: [number, number] = [30, 30],
    lat = 31.5204,
    lon = 74.3587,
    tzOffset = 5.0,
    cellSizeM = 2.0
  ) {
    this.name = name;
    this.groundSize = groundSize;
    this.lat = lat;
    this.lon = lon;
    this.tzOffset = tzOffset;
    this.cellSizeM = cellSizeM;
    this.buildings = [];
    this.nextId = 1;
    this.revision = 0;
  }

  get groundWidthM(): number {
    return this.groundSize[0] * this.cellSizeM;
  }

  get groundDepthM(): number {
    return this.groundSize[1] * this.cellSizeM;
  }

  touch(): void {
    this.revision++;
  }

  canPlace(pos: Vec3, size: Vec3, excludeId?: number): boolean {
    if (pos.x < -1e-6 || pos.y < -1e-6) return false;
    if (pos.x + size.x > this.groundWidthM + 1e-6) return false;
    if (pos.y + size.y > this.groundDepthM + 1e-6) return false;

    const bx1 = pos.x;
    const by1 = pos.y;
    const bx2 = pos.x + size.x;
    const by2 = pos.y + size.y;

    for (const b of this.buildings) {
      if (excludeId !== undefined && b.id === excludeId) continue;
      const ox1 = b.position.x;
      const oy1 = b.position.y;
      const ox2 = b.position.x + b.size.x;
      const oy2 = b.position.y + b.size.y;

      const overlapX = Math.min(bx2, ox2) - Math.max(bx1, ox1);
      const overlapY = Math.min(by2, oy2) - Math.max(by1, oy1);
      if (overlapX > 1e-6 && overlapY > 1e-6) return false;
    }

    return true;
  }

  findFreeSpot(size: Vec3): Vec3 | null {
    const cs = this.cellSizeM;
    const gw = this.groundSize[0];
    const gd = this.groundSize[1];
    const reqW = Math.round(size.x / cs);
    const reqD = Math.round(size.y / cs);

    for (let y = 0; y <= gd - reqD; y++) {
      for (let x = 0; x <= gw - reqW; x++) {
        const testPos = new Vec3(x * cs, y * cs, 0);
        if (this.canPlace(testPos, size)) return testPos;
      }
    }
    return null;
  }

  addBuilding(b: BuildingData): boolean {
    if (this.buildings.length >= MAX_BUILDINGS) return false;
    if (!this.canPlace(b.position, b.size, b.id)) return false;
    this.buildings.push(b);
    if (b.id >= this.nextId) this.nextId = b.id + 1;
    this.touch();
    return true;
  }

  removeBuilding(id: number): boolean {
    const lenBefore = this.buildings.length;
    this.buildings = this.buildings.filter((b) => b.id !== id);
    if (this.buildings.length !== lenBefore) {
      this.touch();
      return true;
    }
    return false;
  }

  moveBuilding(id: number, newPos: Vec3): boolean {
    const b = this.buildings.find((item) => item.id === id);
    if (!b) return false;
    const sx = Math.round(newPos.x / this.cellSizeM) * this.cellSizeM;
    const sy = Math.round(newPos.y / this.cellSizeM) * this.cellSizeM;
    const snapped = new Vec3(sx, sy, 0);
    if (!this.canPlace(snapped, b.size, id)) return false;
    b.position = snapped;
    this.touch();
    return true;
  }

  setBuildingHeight(id: number, height: number): boolean {
    const b = this.buildings.find((item) => item.id === id);
    if (!b) return false;
    b.size.z = Math.max(3, Math.min(45, height));
    this.touch();
    return true;
  }

  clone(newName?: string): ScenarioState {
    const sc = new ScenarioState(
      newName ?? this.name,
      [...this.groundSize],
      this.lat,
      this.lon,
      this.tzOffset,
      this.cellSizeM
    );
    sc.nextId = this.nextId;
    sc.revision = this.revision;
    sc.buildings = this.buildings.map((b) => ({
      id: b.id,
      label: b.label,
      position: new Vec3(b.position.x, b.position.y, b.position.z),
      size: new Vec3(b.size.x, b.size.y, b.size.z),
      color: b.color,
    }));
    return sc;
  }
}

export function createDemoScenario(name = 'A'): ScenarioState {
  const sc = new ScenarioState(name);
  sc.addBuilding({
    id: 1,
    label: 'Tower',
    position: new Vec3(8, 8, 0),
    size: new Vec3(8, 10, 18),
    color: BUILDING_PALETTE[0],
  });
  sc.addBuilding({
    id: 2,
    label: 'Block',
    position: new Vec3(30, 12, 0),
    size: new Vec3(10, 8, 9),
    color: BUILDING_PALETTE[1],
  });
  sc.addBuilding({
    id: 3,
    label: 'Annex',
    position: new Vec3(14, 34, 0),
    size: new Vec3(12, 8, 6),
    color: BUILDING_PALETTE[2],
  });
  sc.nextId = 4;
  sc.revision = 1;
  return sc;
}
