import React, { useEffect, useRef } from 'react';
import styles from './DotSphere.module.css';

// ── Geometry ──────────────────────────────────────────────────────────────────
// 6 faces of a unit cube, each as a flat NxN grid.
// Edge dots overlap between adjacent faces — they render at double weight,
// giving the cube crisp, naturally heavier edges.

const FACE_N = 11; // 11×11 = 121 pts per face × 6 faces = 726 pts total
const VALS = Array.from({ length: FACE_N }, (_, i) => -1 + (2 * i) / (FACE_N - 1));

const FACES = [
  // [outward normal]  [point grid]
  { nx:  0, ny:  0, nz:  1, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: v, z:  1 }))) }, // +Z front
  { nx:  0, ny:  0, nz: -1, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: v, z: -1 }))) }, // -Z back
  { nx:  1, ny:  0, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x:  1, y: u, z: v }))) }, // +X right
  { nx: -1, ny:  0, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: -1, y: u, z: v }))) }, // -X left
  { nx:  0, ny:  1, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y:  1, z: v }))) }, // +Y top
  { nx:  0, ny: -1, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: -1, z: v }))) }, // -Y bottom
];

// ── Camera: sits at z = +FOV, looks toward –z.
// Perspective: sc = FOV / (FOV – z2)  →  higher z2 = closer = appears larger.
// Painter's sort: ascending z2 (draw far first).
// Back-face cull: a face is visible when its rotated normal has nz2 > 0
//   (normal points toward +z = toward the camera).
const FOV = 3.5;
const R   = 128; // half-edge in canvas logical pixels
export const DOT_CUBE_FOV = FOV;
export const DOT_CUBE_R = R;
export const DOT_CUBE_BASE_ROT_X = 0.22;
export const DOT_CUBE_BASE_ROT_Y = 0.1;

// ── Ash particles ─────────────────────────────────────────────────────────────

const ASH_COUNT = 110;

type AshParticle = {
  x: number; y: number;
  vx: number; vy: number;
  r: number;
  baseA: number;
  phase: number;
  wobble: number;
};

function makeAsh(L: number, randomY = false): AshParticle {
  return {
    x: Math.random() * L,
    y: randomY ? Math.random() * L : L + Math.random() * 40,
    vx: (Math.random() - 0.5) * 0.03,
    vy: -(0.018 + Math.random() * 0.055),
    r: 0.3 + Math.random() * 0.95,
    baseA: 0.05 + Math.random() * 0.28,
    phase: Math.random() * Math.PI * 2,
    wobble: 0.002 + Math.random() * 0.005,
  };
}

function initAsh(L: number): AshParticle[] {
  return Array.from({ length: ASH_COUNT }, () => makeAsh(L, true));
}

// ── Star dust field ───────────────────────────────────────────────────────────

const STAR_COUNT = 480;

type StarDust = {
  angle: number;        // base angle in disc plane
  r: number;            // normalized disc radius 0..1 (biased toward center)
  dotR: number;         // base dot radius
  baseA: number;        // base opacity
  zOff: number;         // vertical scatter above/below disc plane (canvas px)
  twinklePhase: number;
  twinkleSpeed: number;
};

function initStars(): StarDust[] {
  return Array.from({ length: STAR_COUNT }, () => {
    // 40% tight galactic bulge, 60% spread disc body
    const isCore = Math.random() < 0.40;
    const r      = isCore
      ? Math.pow(Math.random(), 0.12) * 0.28
      : Math.pow(Math.random(), 0.62);
    return {
      angle:        Math.random() * Math.PI * 2,
      r,
      dotR:         isCore ? 0.8 + Math.random() * 1.4 : 0.5 + Math.random() * 2.2,
      baseA:        isCore ? 0.18 + Math.random() * 0.46 : 0.07 + Math.random() * 0.32,
      zOff:         isCore
        ? (Math.random() - 0.5) * 10
        : (Math.random() - 0.5) * 28,
      twinklePhase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.007 + Math.random() * 0.02,
    };
  });
}

export type DotFieldPointer = {
  x: number;
  y: number;
  active: boolean;
};

type DotCubeProps = {
  pointer?: DotFieldPointer;
};


export function DotCube({ pointer }: DotCubeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef<DotFieldPointer>({ x: 0, y: 0, active: false });
  const ashRef    = useRef<AshParticle[]>([]);
  const starRef   = useRef<StarDust[]>([]);
  const stateRef  = useRef({
    phase:       0,
    rotY:        DOT_CUBE_BASE_ROT_Y,
    rotX:        DOT_CUBE_BASE_ROT_X,
    focus:       0,
    galaxyPhase: 0,
  });

  useEffect(() => {
    pointerRef.current = pointer ?? { x: 0, y: 0, active: false };
  }, [pointer]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const dpr    = Math.min(window.devicePixelRatio || 1, 2);
    const L      = 480;
    canvas.width  = L * dpr;
    canvas.height = L * dpr;
    const ctx = canvas.getContext('2d')!;
    ctx.scale(dpr, dpr);

    ashRef.current  = initAsh(L);
    starRef.current = initStars();

    let raf: number;

    function tick() {
      ctx.clearRect(0, 0, L, L);
      const s = stateRef.current;
      const pointer = pointerRef.current;
      s.focus += ((pointer.active ? 1 : 0) - s.focus) * 0.08;
      s.phase += 0.008 - s.focus * 0.0035;            // bounded idle motion, steadier when observed

      const idleY = Math.sin(s.phase) * 0.055 * (1 - s.focus);
      const idleX = Math.cos(s.phase * 0.8) * 0.025 * (1 - s.focus);
      const targetY = DOT_CUBE_BASE_ROT_Y + idleY - pointer.x * 0.46 * s.focus;
      const targetX = DOT_CUBE_BASE_ROT_X + idleX - pointer.y * 0.18 * s.focus;
      s.rotY += (targetY - s.rotY) * 0.09;
      s.rotX += (targetX - s.rotX) * 0.09;

      const cy = Math.cos(s.rotY), sy = Math.sin(s.rotY);
      const cx = Math.cos(s.rotX), sx = Math.sin(s.rotX);
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

      const visiblePts: {
        sx: number;
        sy: number;
        z: number;
        localX: number;
        localY: number;
        frontFace: boolean;
        faceAlpha: number;
      }[] = [];

      for (const face of FACES) {
        // Rotate face normal with same Y→X transform as points
        const nz1 =  face.nx * sy + face.nz * cy;
        const nz2 =  face.ny * sx + nz1 * cx;     // Z of rotated normal

        // Soft back-face fade avoids whole planes popping in/out at the silhouette.
        const faceAlpha = Math.max(0, Math.min(1, (nz2 + 0.18) / 0.34));
        if (faceAlpha <= 0.01) continue;

        for (const p of face.pts) {
          const x1 = p.x * cy - p.z * sy;
          const z1 = p.x * sy + p.z * cy;
          const y2 = p.y * cx - z1 * sx;
          const z2 = p.y * sx + z1 * cx;

          // Perspective: camera at z=+FOV; higher z2 → closer → larger
          const sc = FOV / (FOV - z2);

          visiblePts.push({
            sx: L / 2 + x1 * R * sc,
            sy: L / 2 + y2 * R * sc,
            z:  z2,
            localX: p.x,
            localY: p.y,
            frontFace: face.nz === 1,
            faceAlpha,
          });
        }
      }

      // Painter's algorithm: draw far (low z2) first
      visiblePts.sort((a, b) => a.z - b.z);

      const [dr, dg, db] = isDark ? [240, 237, 232] : [10, 10, 10];
      const [ar, ag, ab] = isDark ? [176, 0, 32] : [120, 0, 18];
      const eyeCenters = [
        { x: -0.44, y: -0.125 },
        { x: 0.44, y: -0.125 },
      ];
      const pointerCenter = {
        x: L / 2 + pointer.x * 120,
        y: L / 2 + pointer.y * 120,
      };

      for (const pt of visiblePts) {
        // Map z2 range [−0.3 … 1.3] → depth [0 … 1]
        const depth   = Math.max(0, Math.min(1, (pt.z + 0.3) / 1.6));
        const eyeInfluence = pt.frontFace ? eyeCenters.reduce((closest, eye) => {
          const dx = pt.localX - eye.x;
          const dy = pt.localY - eye.y;
          const dist = Math.hypot(dx, dy);
          return Math.max(closest, Math.max(0, 1 - dist / 0.34) ** 2);
        }, 0) : 0;

        const pointerDist = Math.hypot(pt.sx - pointerCenter.x, pt.sy - pointerCenter.y);
        const pointerInfluence = pointer.active ? Math.max(0, 1 - pointerDist / 130) ** 2 : 0;

        const opacity = Math.min(
          0.96,
          ((isDark ? depth * 0.78 + 0.08 : depth * 0.62 + 0.07)
            + eyeInfluence * (0.04 + s.focus * 0.12)
            + pointerInfluence * s.focus * 0.14) * (0.18 + pt.faceAlpha * 0.82),
        );
        const r = Math.max(
          0.6,
          depth * 2.0 + 0.5 + eyeInfluence * (0.28 + s.focus * 0.52) + pointerInfluence * s.focus * 0.9,
        );
        const accent = s.focus * eyeInfluence * 0.18;
        const fillR = Math.round(dr + (ar - dr) * accent);
        const fillG = Math.round(dg + (ag - dg) * accent);
        const fillB = Math.round(db + (ab - db) * accent);
        ctx.beginPath();
        ctx.arc(pt.sx, pt.sy, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${fillR},${fillG},${fillB},${opacity})`;
        ctx.fill();
      }

      // ── Ash particles ──────────────────────────────────────────────────────
      const ash = ashRef.current;
      const mx = L / 2 + pointer.x * 120;
      const my = L / 2 + pointer.y * 120;

      for (let i = 0; i < ash.length; i++) {
        const p = ash[i];

        p.phase += p.wobble;
        p.vx += Math.sin(p.phase * 1.7) * 0.0006;
        p.vx *= 0.988;
        p.vy *= 0.994;

        if (pointer.active) {
          const dx = p.x - mx;
          const dy = p.y - my;
          const dist = Math.hypot(dx, dy);
          if (dist < 160 && dist > 0) {
            const pull = s.focus * (1 - dist / 160) * 0.014;
            p.vx -= (dx / dist) * pull;
            p.vy -= (dy / dist) * pull;
            p.vx += (-dy / dist) * pull * 0.5;
            p.vy += ( dx / dist) * pull * 0.5;
          }
        }

        p.x += p.vx;
        p.y += p.vy;

        if (p.y < -10 || p.x < -20 || p.x > L + 20) {
          ash[i] = makeAsh(L, false);
          continue;
        }

        const fadeTop    = Math.min(1, p.y / 50);
        const fadeBottom = Math.min(1, (L - p.y) / 30);
        const opacity    = p.baseA * fadeTop * fadeBottom;
        if (opacity < 0.01) continue;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${dr},${dg},${db},${opacity})`;
        ctx.fill();
      }

      // ── Star dust field (galaxy plane below cube) ───────────────────────────
      // destination-over paints behind everything already drawn this frame.
      //
      // The cube's front-bottom corner projects to ~y=387 in screen space.
      // GCY=425 + YCLIP=392 guarantees the entire field lives below the cube.
      //
      // Mouse reaction (different from ash scatter):
      //   pointer.x  → drifts the whole disc laterally
      //   pointer.y  → widens/narrows GA (disc appears to lean toward viewer)
      //   focus      → spins faster when observed
      s.galaxyPhase += 0.00022 + s.focus * 0.00065;

      const GCX   = L / 2;
      const GCY   = 425;
      const GA    = 215;
      const GB    = 28;
      const YCLIP = 392;                                          // hard floor below cube

      ctx.globalCompositeOperation = 'destination-over';

      // Galactic core glow — ellipse-shaped via scale trick
      ctx.save();
      ctx.translate(GCX, GCY);
      ctx.scale(1, GB / 72);
      const coreGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 72);
      coreGrad.addColorStop(0,   `rgba(${dr},${dg},${db},${isDark ? 0.09 : 0.03})`);
      coreGrad.addColorStop(0.45,`rgba(${dr},${dg},${db},${isDark ? 0.03 : 0.01})`);
      coreGrad.addColorStop(1,   `rgba(${dr},${dg},${db},0)`);
      ctx.beginPath();
      ctx.arc(0, 0, 72, 0, Math.PI * 2);
      ctx.fillStyle = coreGrad;
      ctx.fill();
      ctx.restore();

      // Compute star screen positions
      const stars = starRef.current;
      type StarPt = { x: number; y: number; depth: number; opacity: number; r: number };
      const starPts: StarPt[] = [];

      for (const star of stars) {
        star.twinklePhase += star.twinkleSpeed;
        const angle  = star.angle + s.galaxyPhase;
        const cosA   = Math.cos(angle);
        const sinA   = Math.sin(angle);
        const depth  = sinA;              // -1 = back, +1 = front
        const depthF = (depth + 1) * 0.5;
        const twinkle = 0.82 + Math.sin(star.twinklePhase) * 0.18;
        const persp   = 0.72 + depthF * 0.28;

        const sx = GCX + star.r * GA * cosA;
        const sy = GCY + star.r * GB * sinA + star.zOff;

        // soft fade above YCLIP over 20px — nothing above the cube
        const yFade = Math.max(0, Math.min(1, (sy - YCLIP) / 20));
        if (yFade < 0.01) continue;

        // stars closer to the disc plane (small |zOff|) are sharper and brighter;
        // stars far above/below the plane are dimmer and slightly smaller
        const zDepth = 1 - Math.abs(star.zOff) / 28;

        starPts.push({
          x:       sx,
          y:       sy,
          depth:   depth + star.zOff * 0.01,  // z-layer feeds into painter sort
          opacity: star.baseA * twinkle * (0.08 + depthF * 0.92) * yFade * (0.4 + zDepth * 0.6),
          r:       Math.max(0.2, star.dotR * persp * (0.4 + star.r * 0.6) * (0.7 + zDepth * 0.3)),
        });
      }

      starPts.sort((a, b) => a.depth - b.depth); // back-to-front

      for (const sp of starPts) {
        if (sp.opacity < 0.01) continue;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, sp.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${dr},${dg},${db},${sp.opacity})`;
        ctx.fill();
      }

      ctx.globalCompositeOperation = 'source-over';

      raf = requestAnimationFrame(tick);
    }
    tick();

    return () => {
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvasRef} className={styles.canvas} />;
}
