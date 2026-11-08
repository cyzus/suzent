import scanLayers from '../../../../config/assembly_scan.json';

type Vector = [number, number, number];
type Point = [number, number];
export interface AssemblyMark {
  points: Point[];
  color: string;
  alpha: number;
  stroke?: boolean;
  width?: number;
}
const clamp = (v: number): number => Math.min(1, Math.max(0, v));
const ease = (v: number): number => {
  const p = clamp(v);
  return p * p * (3 - 2 * p);
};
const rotate = ([x, y, z]: Vector): Vector => {
  const a = x * Math.cos(-0.48) + z * Math.sin(-0.48);
  const b = -x * Math.sin(-0.48) + z * Math.cos(-0.48);
  return [a, y * Math.cos(0.32) - b * Math.sin(0.32), y * Math.sin(0.32) + b * Math.cos(0.32)];
};
const random = (cycle: number, block: number, salt: number): number => {
  const v = Math.sin(1729 + cycle * 127.1 + block * 311.7 + salt * 74.7) * 43758.5453;
  return v - Math.floor(v);
};

// Keep projection, timing, and draw order aligned with the native mobile scenes.
export function assemblyFrame(seconds: number, reduced = false): AssemblyMark[] {
  const t = reduced ? 3.2 : Math.max(0, seconds) * 1.45;
  const cycle = t % 5.5;
  const cycleId = Math.floor(t / 5.5);
  const marks: AssemblyMark[] = [];
  const advance = ease((cycle - 4.3) / 1.2) * 76;
  const shell = ease((cycle - 1.5) / 0.28);
  const awake = ease((cycle - 2.7) / 0.3);
  const project = (v: Vector, center: number): Point => {
    const q = rotate(v);
    return [center + q[0], 56 - q[1]];
  };
  const cube = (
    center: number,
    size: number,
    offset: Vector = [0, 0, 0],
    alpha = 1,
    eyes = 0
  ): void => {
    if (alpha <= 0) return;
    const coordinates: Vector[] = [
      [-1, -1, -1],
      [1, -1, -1],
      [1, 1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
      [1, -1, 1],
      [1, 1, 1],
      [-1, 1, 1],
    ];
    const vertices = coordinates.map(([x, y, z]) =>
      project([x * size + offset[0], y * size + offset[1], z * size + offset[2]], center)
    );
    const faces: [number[], number][] = [
      [[3, 2, 6, 7], 51],
      [[1, 5, 6, 2], 25],
      [[4, 7, 6, 5], 9],
    ];
    for (const [indices, shade] of faces) {
      const points = indices.map((i) => vertices[i]);
      marks.push({ points, color: `rgb(${shade},${shade + 1},${shade + 2})`, alpha });
      marks.push({ points, color: '#454749', alpha, stroke: true });
    }
    if (eyes > 0)
      for (const x of [-0.43, 0.43]) {
        const positions: Point[] = [
          [x - 0.16, 0.23 - eyes / 2],
          [x + 0.16, 0.23 - eyes / 2],
          [x + 0.16, 0.23 + eyes / 2],
          [x - 0.16, 0.23 + eyes / 2],
        ];
        marks.push({
          points: positions.map(([px, py]) =>
            project([px * size, py * size, 1.012 * size], center)
          ),
          color: '#e8eceb',
          alpha,
        });
      }
  };
  const scan = (back: boolean): void => {
    if (cycle <= 1.85 || cycle >= 2.7) return;
    const progress = clamp((cycle - 1.85) / 0.85);
    const r = 15.05,
      y = (r - 0.3) * (1 - 2 * progress);
    const corners: Vector[] = [
      [-r, y, r],
      [r, y, r],
      [r, y, -r],
      [-r, y, -r],
    ];
    const points = corners.map((v) => project(v, 160));
    for (let i = 0; i < 4; i++) {
      if (i < 2 === back) continue;
      const edge = [points[i], points[(i + 1) % 4]];
      const alpha = Math.sin(progress * Math.PI) * (back ? 0.24 : 0.95);
      for (const layer of back ? scanLayers.back : scanLayers.front) {
        marks.push({
          points: edge,
          color: `#${layer.color}`,
          alpha: alpha * layer.opacity,
          stroke: true,
          width: layer.width,
        });
      }
    }
  };
  for (let slot = -3; slot <= 2; slot++) {
    const center = 160 + slot * 76 + advance;
    if (center < -35 || center > 355) continue;
    marks.push({
      points: Array.from(
        { length: 24 },
        (_, i) =>
          [
            center + 18 * Math.cos((i * Math.PI) / 12),
            81 + 2 * Math.sin((i * Math.PI) / 12),
          ] as Point
      ),
      color: '#000',
      alpha: 0.09,
    });
    if (slot > 0) {
      cube(center, 14.65, [0, 0, 0], 1, 0.22);
      continue;
    }
    if (slot === 0) scan(true);
    const parts: { offset: Vector; alpha: number }[] = [];
    for (let a = -1; a <= 1; a++)
      for (let b = -1; b <= 1; b++)
        for (let c = -1; c <= 1; c++) {
          if (slot < 0 && b !== -1) continue;
          const block = (a + 1) * 3 + c + 1;
          const start =
            0.4 +
            random(cycleId, block, 0) * 0.28 +
            (b === 1 ? 0.18 + random(cycleId, block, 1) * 0.08 : 0);
          const length = 0.3 + random(cycleId, block + b * 9, 2) * 0.12;
          const upper = b !== -1,
            fall = clamp((cycle - start - 0.08) / length);
          const drop = upper ? (1 - fall ** 3) * (22 + random(cycleId, block + b * 9, 3) * 10) : 0;
          parts.push({
            offset: [a * 9.85, b * 9.85 + drop, c * 9.85],
            alpha: (upper ? ease((cycle - start) / 0.09) : 1) * (slot === 0 ? 1 - shell : 1),
          });
        }
    parts.sort((a, b) => rotate(a.offset)[2] - rotate(b.offset)[2]);
    for (const part of parts) cube(center, 4.8, part.offset, part.alpha);
    if (slot === 0) {
      cube(center, 14.65, [0, 0, 0], shell, 0.22 * awake);
      scan(false);
    }
  }
  return marks;
}
