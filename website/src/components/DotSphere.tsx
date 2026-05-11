import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import styles from './DotSphere.module.css';

// ── Cube geometry (6-face 17×17 grid) ────────────────────────────────────────

const FACE_N = 43;
const VALS   = Array.from({ length: FACE_N }, (_, i) => -1 + (2 * i) / (FACE_N - 1));

const FACES = [
  { nx:  0, ny:  0, nz:  1, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: v, z:  1 }))) },
  { nx:  0, ny:  0, nz: -1, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: v, z: -1 }))) },
  { nx:  1, ny:  0, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x:  1, y: u, z: v }))) },
  { nx: -1, ny:  0, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: -1, y: u, z: v }))) },
  { nx:  0, ny:  1, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y:  1, z: v }))) },
  { nx:  0, ny: -1, nz:  0, pts: VALS.flatMap(u => VALS.map(v => ({ x: u, y: -1, z: v }))) },
];

export const DOT_CUBE_FOV        = 3.5;
export const DOT_CUBE_R          = 128;
export const DOT_CUBE_BASE_ROT_X = 0;
export const DOT_CUBE_BASE_ROT_Y = 0.05;

export type DotFieldPointer = { x: number; y: number; active: boolean };

// ── Pre-flattened cube point list ─────────────────────────────────────────────

type CubePt = {
  x: number; y: number; z: number;
  nx: number; ny: number; nz: number;
  isFront: boolean;
};

const CUBE_PTS: CubePt[] = [];
for (const face of FACES)
  for (const p of face.pts)
    CUBE_PTS.push({ x: p.x, y: p.y, z: p.z, nx: face.nx, ny: face.ny, nz: face.nz, isFront: face.nz === 1 });
const CUBE_N = CUBE_PTS.length; // 1734

// Static per-point attributes (position, normal, eye proximity) — uploaded once
const CUBE_POS_STATIC  = new Float32Array(CUBE_N * 3);
const CUBE_NORM_STATIC = new Float32Array(CUBE_N * 3);
const CUBE_EYE_STATIC  = new Float32Array(CUBE_N); // eye proximity [0..1]

const EYE_CTRS = [{ x: -0.44, y: -0.125 }, { x: 0.44, y: -0.125 }];
const EYE_R    = 0.34;

for (let i = 0; i < CUBE_N; i++) {
  const p = CUBE_PTS[i];
  CUBE_POS_STATIC[i*3]     = p.x;
  CUBE_POS_STATIC[i*3 + 1] = p.y;
  CUBE_POS_STATIC[i*3 + 2] = p.z;
  CUBE_NORM_STATIC[i*3]     = p.nx;
  CUBE_NORM_STATIC[i*3 + 1] = p.ny;
  CUBE_NORM_STATIC[i*3 + 2] = p.nz;
  CUBE_EYE_STATIC[i] = p.isFront
    ? EYE_CTRS.reduce((best, e) => Math.max(best, Math.max(0, 1 - Math.hypot(p.x - e.x, p.y - e.y) / EYE_R) ** 2), 0)
    : 0;
}

// ── Interior dust ─────────────────────────────────────────────────────────────

const INTERIOR_DUST_N = 1500;
const INTERIOR_DUST_INIT = Array.from({ length: INTERIOR_DUST_N }, () => ({
  x: (Math.random() - 0.5) * 1.82,
  y: (Math.random() - 0.5) * 1.82,
  z: (Math.random() - 0.5) * 1.82,
  size: 0.22 + Math.random() * 0.72,
  op: 0.018 + Math.random() * 0.075,
  phase: Math.random() * Math.PI * 2,
  speed: 0.002 + Math.random() * 0.009,
}));

// ── Occult ring definitions ───────────────────────────────────────────────────

const GAP_HALF = 0.058;

const RING_DEFS = [
  // Near-horizontal equatorial ring — most visible, saturn-like
  { count: 480, radius: 2.4, tiltX: Math.PI * 0.08, tiltZ: 0,              gapN: 10, orbitSpeed:  0.00038, op: 0.60 },
  // Tilted ~45° — diagonal orbital plane
  { count: 360, radius: 2.8, tiltX: Math.PI * 0.28, tiltZ: Math.PI * 0.15, gapN:  7, orbitSpeed: -0.00028, op: 0.40 },
  // Near-vertical polar orbit
  { count: 300, radius: 2.2, tiltX: Math.PI * 0.48, tiltZ: Math.PI * 0.30, gapN:  5, orbitSpeed:  0.00048, op: 0.28 },
  // Wide slow outer ring, strongly tilted
  { count: 260, radius: 3.0, tiltX: Math.PI * 0.38, tiltZ: Math.PI * 0.50, gapN:  6, orbitSpeed: -0.00018, op: 0.20 },
] as const;

// Points generated once at phase=0 in ring-local XZ plane; rotation handled by Group
function genRingPts(def: (typeof RING_DEFS)[number]): number[] {
  const TWO_PI    = Math.PI * 2;
  const gapAngles = Array.from({ length: def.gapN }, (_, i) => (i / def.gapN) * TWO_PI);
  const pts: number[] = [];
  for (let i = 0; i < def.count; i++) {
    const a = (i / def.count) * TWO_PI;
    const inGap = gapAngles.some(g => {
      let d = ((a - g) % TWO_PI + TWO_PI) % TWO_PI;
      if (d > Math.PI) d = TWO_PI - d;
      return d < GAP_HALF;
    });
    if (inGap) continue;
    // Flat ring in XZ plane — tilt applied via Group Euler rotation
    pts.push(Math.cos(a) * def.radius, 0, Math.sin(a) * def.radius);
  }
  return pts;
}

function isRingGap(a: number, gapN: number): boolean {
  const TWO_PI = Math.PI * 2;
  const gapAngles = Array.from({ length: gapN }, (_, i) => (i / gapN) * TWO_PI);
  return gapAngles.some(g => {
    let d = ((a - g) % TWO_PI + TWO_PI) % TWO_PI;
    if (d > Math.PI) d = TWO_PI - d;
    return d < GAP_HALF;
  });
}

function genRingArcSegments(def: (typeof RING_DEFS)[number]): number[] {
  const TWO_PI = Math.PI * 2;
  const segN = Math.max(96, Math.floor(def.count / 2));
  const pts: number[] = [];

  for (let i = 0; i < segN; i++) {
    const a0 = i / segN * TWO_PI;
    const a1 = (i + 0.56) / segN * TWO_PI;
    const dashGate = (i + Math.floor(i / 9)) % 5 !== 0;
    if (!dashGate || isRingGap(a0, def.gapN) || isRingGap(a1, def.gapN)) continue;

    pts.push(
      Math.cos(a0) * def.radius, 0, Math.sin(a0) * def.radius,
      Math.cos(a1) * def.radius, 0, Math.sin(a1) * def.radius,
    );
  }

  return pts;
}

// ── Ash particle ──────────────────────────────────────────────────────────────

type Ash = { x: number; y: number; z: number; vx: number; vy: number; vz: number; size: number; baseOp: number; phase: number; wobble: number };
function spawnAsh(): Ash {
  const a = Math.random() * Math.PI * 2, r = 0.8 + Math.random() * 1.6;
  return {
    x: Math.cos(a) * r, y: -2.8 - Math.random() * 0.8, z: Math.sin(a) * r,
    vx: (Math.random() - 0.5) * 0.003, vy: 0.006 + Math.random() * 0.016, vz: (Math.random() - 0.5) * 0.003,
    size: 0.5 + Math.random() * 1.6, baseOp: 0.05 + Math.random() * 0.20,
    phase: Math.random() * Math.PI * 2, wobble: 0.006 + Math.random() * 0.016,
  };
}

// ── Star field ────────────────────────────────────────────────────────────────

type Star = { angle: number; r: number; zOff: number; phase: number; speed: number };
const STAR_N = 480;
const STAR_INIT: Star[] = Array.from({ length: STAR_N }, () => ({
  angle: Math.random() * Math.PI * 2, r: Math.pow(Math.random(), 0.7),
  zOff:  (Math.random() - 0.5) * 0.7, phase: Math.random() * Math.PI * 2,
  speed: 0.006 + Math.random() * 0.018,
}));

// ── Deep field ───────────────────────────────────────────────────────────────

type DeepPoint = {
  angle: number;
  radius: number;
  y: number;
  z: number;
  phase: number;
  speed: number;
  size: number;
  baseOp: number;
};

const DEEP_FIELD_INIT: DeepPoint[] = (() => {
  const pts: DeepPoint[] = [];
  const TWO_PI = Math.PI * 2;

  for (let shell = 0; shell < 9; shell++) {
    const n = 180 + shell * 24;
    const radius = 2.0 + shell * 0.28;
    const wave = 2 + (shell % 4);
    for (let i = 0; i < n; i++) {
      const t = i / n;
      const a = t * TWO_PI + shell * 0.31;
      const jitter = (Math.random() - 0.5) * 0.055;
      pts.push({
        angle: a + jitter,
        radius: radius + Math.sin(t * TWO_PI * wave + shell) * 0.18 + (Math.random() - 0.5) * 0.08,
        y: Math.sin(t * TWO_PI * wave + shell * 0.7) * (0.58 + shell * 0.09) + (Math.random() - 0.5) * 0.08,
        z: -1.2 + shell * 0.12 + Math.cos(t * TWO_PI * 2 + shell) * 0.22,
        phase: Math.random() * TWO_PI,
        speed: 0.0012 + Math.random() * 0.0035,
        size: 0.58 + Math.random() * 0.82,
        baseOp: 0.065 + Math.random() * 0.105,
      });
    }
  }

  for (let arm = 0; arm < 7; arm++) {
    const n = 170;
    for (let i = 0; i < n; i++) {
      const t = i / (n - 1);
      const a = arm / 7 * TWO_PI + t * 1.25 + Math.sin(t * TWO_PI) * 0.18;
      pts.push({
        angle: a,
        radius: 1.9 + t * 3.15 + (Math.random() - 0.5) * 0.09,
        y: (t - 0.5) * 2.35 + Math.sin(t * TWO_PI * 2 + arm) * 0.22,
        z: -1.35 + Math.cos(t * TWO_PI + arm) * 0.42,
        phase: Math.random() * TWO_PI,
        speed: 0.001 + Math.random() * 0.0025,
        size: 0.5 + Math.random() * 0.72,
        baseOp: 0.05 + Math.random() * 0.085,
      });
    }
  }

  return pts;
})();
const DEEP_FIELD_N = DEEP_FIELD_INIT.length;

// ── GLSL ──────────────────────────────────────────────────────────────────────

// Cube shader: back-face cull via gl_FrontFacing on the face normal,
// depth/opacity/size computed in view space — no CPU rotation needed.
const VERT_CUBE = /* glsl */`
attribute vec3  aNormal;
attribute float aEye;       // eye-proximity [0..1], static
attribute float aFocus;     // interaction focus, uniform-like but passed as attrib for simplicity
uniform   float uDPR;
uniform   float uFocus;
uniform   float uPtrX;      // pointer NDC x [-1..1]
uniform   float uPtrY;
uniform   float uPtrActive; // 0 or 1
uniform   float uIsDark;
uniform   float uTime;
uniform   float uEntry;
varying   float vAlpha;
varying   float vSize;

void main() {
  vec4 mvOrig = modelViewMatrix * vec4(position, 1.0);
  vec4 clipOrig = projectionMatrix * mvOrig;
  vec2 ndc = clipOrig.xy / clipOrig.w;
  float pDist = length(ndc - vec2(uPtrX, uPtrY));
  float lensCore = 1.0 - smoothstep(0.00, 0.32, pDist);
  float lensHalo = 1.0 - smoothstep(0.20, 0.72, pDist);
  float lensRing = 1.0 - smoothstep(0.02, 0.0, abs(pDist - 0.32));
  lensCore = lensCore * lensCore * (3.0 - 2.0 * lensCore);
  lensHalo = lensHalo * lensHalo * (3.0 - 2.0 * lensHalo);
  float pInfl = uPtrActive * (lensCore * 0.42 + lensHalo * 0.24 + lensRing * 0.18);

  float h1 = fract(sin(dot(position.xyz, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
  float h2 = fract(sin(dot(position.xyz, vec3(39.3467, 11.135, 83.155))) * 24634.6345);
  float h3 = fract(sin(dot(position.xyz, vec3(73.156, 52.235, 9.151))) * 12414.7711);
  float h4 = fract(sin(dot(position.xyz, vec3(17.913, 63.721, 29.377))) * 32719.171);
  float dirt = fract(sin(dot(position.xyz, vec3(91.733, 21.133, 47.911))) * 15973.621);
  float dirtFleck = step(0.966, dirt);
  float dirtFade = mix(0.58, 1.12, h2);
  float shimmer = 0.90 + sin(uTime * (1.15 + h3 * 1.6) + h1 * 6.2831853) * 0.10;
  vec3 tangentA = normalize(cross(aNormal, vec3(0.0, 1.0, 0.37)));
  vec3 tangentB = normalize(cross(aNormal, tangentA));
  float ripple = sin((pDist * 30.0) + h1 * 6.2831853 + uTime * (0.9 + h2 * 0.4));
  float ritePhase = uTime * (0.42 + h2 * 0.38) + h1 * 6.2831853;
  float riteBreath = sin(ritePhase) * 0.5 + sin(ritePhase * 0.37 + h3 * 6.2831853) * 0.5;
  vec3 riteDir = normalize(
    aNormal * (0.46 + h1 * 0.24)
    + tangentA * sin(ritePhase * 0.73) * 0.34
    + tangentB * cos(ritePhase * 0.61) * 0.34
  );
  vec3 lensDir = normalize(
    aNormal * (0.10 + lensCore * 0.18)
    + tangentA * ((h2 - 0.5) * 0.62 + ripple * 0.22)
    + tangentB * ((h3 - 0.5) * 0.62 - ripple * 0.18)
  );
  float mouseVeil = 1.0 - uFocus * 0.10;
  vec3 localPos = position
    + riteDir * riteBreath * mouseVeil * (0.012 + h3 * 0.016)
    + tangentA * sin(uTime * 0.52 + h4 * 6.2831853) * (0.004 + h2 * 0.004)
    + tangentB * cos(uTime * 0.47 + h1 * 6.2831853) * (0.004 + h3 * 0.004)
    + lensDir * pInfl * uFocus * (0.08 + h1 * 0.16);

  float tEase = clamp(1.0 - uEntry, 0.0, 1.0);
  float ease = 1.0 - (tEase * tEase * tEase * tEase * tEase); // Quintic ease out for a longer settling tail
  // Increased scatter magnitude for a more dramatic, wide-spread "starburst" gathering
  vec3 scatterPos = position * (1.0 + (1.0 - ease) * 3.5) + vec3(h1 - 0.5, h2 - 0.5, h3 - 0.5) * 18.0 * (1.0 - ease);
  localPos = mix(scatterPos, localPos, ease);

  vec4 mvPos  = modelViewMatrix * vec4(localPos, 1.0);
  vec3 worldNorm = normalize(mat3(modelMatrix) * aNormal);
  vec3 worldPos3 = (modelMatrix * vec4(localPos, 1.0)).xyz;
  vec3 toCamera  = normalize(cameraPosition - worldPos3);
  float facing   = dot(worldNorm, toCamera);
  float fAlpha   = clamp(facing / 0.15, 0.0, 1.0);

  // Back-face: fully discard when fAlpha == 0
  if (fAlpha <= 0.0) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0); // clip to outside NDC — invisible
    vAlpha = 0.0; vSize = 0.0;
    return;
  }

  // Depth: mvPos.z ≈ -2.5 (front/near) to -4.5 (back/far) — invert so near = 1, far = 0
  float depth = clamp((mvPos.z + 4.5) / 2.5, 0.0, 1.0);

  // Pointer influence: NDC position of this vertex
  vec4 clip = projectionMatrix * mvPos;

  float base = uIsDark > 0.5 ? depth * 0.72 + 0.06 : depth * 0.88 + 0.14;
  vAlpha = clamp(
    (base + aEye * (0.12 + uFocus * 0.20) + pInfl * uFocus * 0.34) * fAlpha * dirtFade * shimmer
      + dirtFleck * (uIsDark > 0.5 ? 0.06 : 0.10),
    0.0, uIsDark > 0.5 ? 0.88 : 0.96
  ) * ease; // Fade in based on entry

  vSize = max(0.34, depth * 0.72 + 0.42
    + aEye  * (0.10 + uFocus * 0.18)
    + pInfl *  uFocus * 0.68
    + dirtFleck * 0.30
    + abs(riteBreath) * 0.055);

  float themeSize = uIsDark > 0.5 ? 1.55 : 2.35;
  gl_PointSize = vSize * themeSize * uDPR;
  gl_Position  = clip;
}`;

const FRAG_CUBE = /* glsl */`
uniform vec3  uColor;
varying float vAlpha;
varying float vSize;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.32, d) * vAlpha;
  if (a < 0.01) discard;
  float glow = smoothstep(0.20, 0.0, d) * vAlpha;
  gl_FragColor = vec4(uColor + glow * 0.6, a);
}`;

// Rings + atmosphere: depth-shaded point sprites
const VERT_COLORED = /* glsl */`
attribute vec4  aColor;
attribute float aSize;
varying vec4    vColor;
uniform float   uDPR;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  // mv.z: near ≈ -0.5, far ≈ -6.5 (camera z=3.5, ring radius up to 3)
  float depth = clamp((-mv.z - 0.5) / 6.0, 0.0, 1.0); // 0=near 1=far
  float depthAlpha = mix(1.0, 0.12, depth);
  float depthSize  = mix(2.2, 0.7, depth);
  vColor = vec4(aColor.rgb, aColor.a * depthAlpha);
  gl_PointSize = aSize * depthSize * uDPR;
  gl_Position  = projectionMatrix * mv;
}`;

const FRAG_COLORED = /* glsl */`
varying vec4 vColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.32, d) * vColor.a;
  if (a < 0.01) discard;
  float glow = smoothstep(0.20, 0.0, d) * vColor.a;
  gl_FragColor = vec4(vColor.rgb + glow * 0.5, a);
}`;

const VERT_ATMO = /* glsl */`
attribute float aSize;
attribute float aOpacity;
varying float   vOpacity;
uniform float   uDPR;
void main() {
  vOpacity = aOpacity;
  vec4 mv  = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = aSize * 2.0 * uDPR;
  gl_Position  = projectionMatrix * mv;
}`;

const FRAG_ATMO = /* glsl */`
uniform vec3  uColor;
varying float vOpacity;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.1, d) * vOpacity;
  float glow = smoothstep(0.15, 0.0, d) * vOpacity;
  gl_FragColor = vec4(uColor + glow * 0.5
  gl_FragColor = vec4(uColor, a);
}`;

// ── Component ──────────────────────────────────────────────────────────────────

type DotCubeProps = { pointer?: DotFieldPointer };

export function DotCube({ pointer }: DotCubeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ptrRef    = useRef<DotFieldPointer>({ x: 0, y: 0, active: false });

  useEffect(() => { ptrRef.current = pointer ?? { x: 0, y: 0, active: false }; }, [pointer]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const dpr    = Math.min(window.devicePixelRatio || 1, 2);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(dpr);
    renderer.setClearColor(0x000000, 0);

    // Size the renderer to the canvas's actual CSS size so the viewport matches
    function resize() {
      const w = canvas.clientWidth || 480;
      renderer.setSize(w, w, false);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(90, 1, 0.1, 50);
    camera.position.z = DOT_CUBE_FOV;

    // ── Cube ──────────────────────────────────────────────────────────────
    const cubeGeo = new THREE.BufferGeometry();
    cubeGeo.setAttribute('position', new THREE.BufferAttribute(CUBE_POS_STATIC.slice(),  3));
    cubeGeo.setAttribute('aNormal',  new THREE.BufferAttribute(CUBE_NORM_STATIC.slice(), 3));
    cubeGeo.setAttribute('aEye',     new THREE.BufferAttribute(CUBE_EYE_STATIC.slice(),  1));

    const cubeMat = new THREE.ShaderMaterial({
      vertexShader:   VERT_CUBE,
      fragmentShader: FRAG_CUBE,
      uniforms: {
        uDPR:       { value: dpr },
        uFocus:     { value: 0 },
        uPtrX:      { value: 0 },
        uPtrY:      { value: 0 },
        uPtrActive: { value: 0 },
        uIsDark:    { value: 1 },
        uTime:      { value: 0 },
        uEntry:     { value: 0 }, // Will animate 0 -> 1
        uColor:     { value: new THREE.Color() },
      },
      transparent: true, depthWrite: false,
    });
    const cubeMesh = new THREE.Points(cubeGeo, cubeMat);

    // ── Scene group: everything rotates together with the cube ────────────
    const sceneGroup = new THREE.Group();
    sceneGroup.rotation.order = 'YXZ'; 
    scene.add(sceneGroup);

    // ── Body group (cube only) ────────────────────────────────────────────
    const bodyGroup = new THREE.Group();
    bodyGroup.renderOrder = 1;
    sceneGroup.add(bodyGroup);
    bodyGroup.add(cubeMesh);

    const dustPos = new Float32Array(INTERIOR_DUST_N * 3);
    const dustSz  = new Float32Array(INTERIOR_DUST_N);
    const dustOp  = new Float32Array(INTERIOR_DUST_N);
    for (let i = 0; i < INTERIOR_DUST_N; i++) {
      const p = INTERIOR_DUST_INIT[i];
      dustPos[i*3]     = p.x;
      dustPos[i*3 + 1] = p.y;
      dustPos[i*3 + 2] = p.z;
      dustSz[i] = p.size;
      dustOp[i] = p.op;
    }
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    dustGeo.setAttribute('aSize',    new THREE.BufferAttribute(dustSz,  1));
    dustGeo.setAttribute('aOpacity', new THREE.BufferAttribute(dustOp,  1).setUsage(THREE.DynamicDrawUsage));
    const dustMat = new THREE.ShaderMaterial({
      vertexShader: VERT_ATMO,
      fragmentShader: FRAG_ATMO,
      uniforms: { uColor: { value: new THREE.Vector3() }, uDPR: { value: dpr } },
      transparent: true,
      depthWrite: false,
    });
    const dustMesh = new THREE.Points(dustGeo, dustMat);
    dustMesh.renderOrder = 1;
    bodyGroup.add(dustMesh);

    function makeColoredMat() {
      return new THREE.ShaderMaterial({
        vertexShader: VERT_COLORED, fragmentShader: FRAG_COLORED,
        uniforms: { uDPR: { value: dpr } },
        transparent: true, depthWrite: false, depthTest: false,
      });
    }

    const ringBufs: Array<{
      n: number;
      colArr: Float32Array;
      geo: THREE.BufferGeometry;
      arcMat: THREE.LineBasicMaterial;
      arcGeo: THREE.BufferGeometry;
      orbitGroup: THREE.Group;
      tiltGroup: THREE.Group;
      orbitSpeed: number;
    }> = [];
    for (let ri = 0; ri < RING_DEFS.length; ri++) {
      const def = RING_DEFS[ri];
      const pts = genRingPts(def);
      const n   = pts.length / 3;
      const posArr = new Float32Array(pts);
      const colArr = new Float32Array(n * 4);
      const szArr  = new Float32Array(n).fill(2.0);
      for (let j = 0; j < n; j++) colArr[j*4+3] = def.op;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(posArr, 3));
      geo.setAttribute('aColor',   new THREE.BufferAttribute(colArr, 4).setUsage(THREE.DynamicDrawUsage));
      geo.setAttribute('aSize',    new THREE.BufferAttribute(szArr,  1));
      geo.setDrawRange(0, n);
      const mesh = new THREE.Points(geo, makeColoredMat());
      mesh.renderOrder = 2;

      const arcGeo = new THREE.BufferGeometry();
      arcGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(genRingArcSegments(def)), 3));
      const arcMat = new THREE.LineBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: def.op * 0.28,
        depthWrite: false,
        depthTest: false,
      });
      const arcMesh = new THREE.LineSegments(arcGeo, arcMat);
      arcMesh.renderOrder = 2;

      // tiltGroup: fixes the orbital plane inclination
      const tiltGroup = new THREE.Group();
      tiltGroup.rotation.set(def.tiltX, 0, def.tiltZ, 'ZXY');
      tiltGroup.add(arcMesh);
      tiltGroup.add(mesh);
      // orbitGroup: rotates around world Y each frame — this is the revolution
      const orbitGroup = new THREE.Group();
      orbitGroup.renderOrder = 2;
      orbitGroup.add(tiltGroup);
      sceneGroup.add(orbitGroup); // 将光环添加到 sceneGroup，使其跟随主体一起倾斜/旋转
      ringBufs.push({ n, colArr, geo, arcMat, arcGeo, orbitGroup, tiltGroup, orbitSpeed: def.orbitSpeed });
    }

    // ── Ash ───────────────────────────────────────────────────────────────
    const ASH_N  = 220;
    const ashes: Ash[] = Array.from({ length: ASH_N }, spawnAsh);
    for (const a of ashes) a.y = -2.8 + Math.random() * 5.5;
    const ashPos = new Float32Array(ASH_N * 3);
    const ashSz  = new Float32Array(ASH_N);
    const ashOp  = new Float32Array(ASH_N);
    const ashGeo = new THREE.BufferGeometry();
    ashGeo.setAttribute('position', new THREE.BufferAttribute(ashPos, 3).setUsage(THREE.DynamicDrawUsage));
    ashGeo.setAttribute('aSize',    new THREE.BufferAttribute(ashSz,  1).setUsage(THREE.DynamicDrawUsage));
    ashGeo.setAttribute('aOpacity', new THREE.BufferAttribute(ashOp,  1).setUsage(THREE.DynamicDrawUsage));
    const ashMat  = new THREE.ShaderMaterial({
      vertexShader: VERT_ATMO, fragmentShader: FRAG_ATMO,
      uniforms: { uColor: { value: new THREE.Vector3() }, uDPR: { value: dpr } },
      transparent: true, depthWrite: false,
    });
    scene.add(new THREE.Points(ashGeo, ashMat));

    // ── Deep field ────────────────────────────────────────────────────────
    const deepField: DeepPoint[] = DEEP_FIELD_INIT.map(p => ({ ...p }));
    const deepPos = new Float32Array(DEEP_FIELD_N * 3);
    const deepSz  = new Float32Array(DEEP_FIELD_N);
    const deepOp  = new Float32Array(DEEP_FIELD_N);
    const deepGeo = new THREE.BufferGeometry();
    deepGeo.setAttribute('position', new THREE.BufferAttribute(deepPos, 3).setUsage(THREE.DynamicDrawUsage));
    deepGeo.setAttribute('aSize',    new THREE.BufferAttribute(deepSz,  1).setUsage(THREE.DynamicDrawUsage));
    deepGeo.setAttribute('aOpacity', new THREE.BufferAttribute(deepOp,  1).setUsage(THREE.DynamicDrawUsage));
    const deepMat = new THREE.ShaderMaterial({
      vertexShader: VERT_ATMO,
      fragmentShader: FRAG_ATMO,
      uniforms: { uColor: { value: new THREE.Vector3() }, uDPR: { value: dpr } },
      transparent: true,
      depthWrite: false,
    });
    const deepMesh = new THREE.Points(deepGeo, deepMat);
    deepMesh.renderOrder = 0;
    scene.add(deepMesh);

    // ── Stars ─────────────────────────────────────────────────────────────
    const stars: Star[] = STAR_INIT.map(s => ({ ...s }));
    const starPos = new Float32Array(STAR_N * 3);
    const starSz  = new Float32Array(STAR_N);
    const starOp  = new Float32Array(STAR_N);
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3).setUsage(THREE.DynamicDrawUsage));
    starGeo.setAttribute('aSize',    new THREE.BufferAttribute(starSz,  1).setUsage(THREE.DynamicDrawUsage));
    starGeo.setAttribute('aOpacity', new THREE.BufferAttribute(starOp,  1).setUsage(THREE.DynamicDrawUsage));
    const starMat = new THREE.ShaderMaterial({
      vertexShader: VERT_ATMO, fragmentShader: FRAG_ATMO,
      uniforms: { uColor: { value: new THREE.Vector3() }, uDPR: { value: dpr } },
      transparent: true, depthWrite: false,
    });
    scene.add(new THREE.Points(starGeo, starMat));

    // ── Animation state ───────────────────────────────────────────────────
    const st = {
      phase: 0, rotY: DOT_CUBE_BASE_ROT_Y, rotX: DOT_CUBE_BASE_ROT_X,
      focus: 0, galaxyPhase: 0, entry: 0,
    };

    let raf: number;
    let lastIsDark: boolean | null = null;

    function tick() {
      raf = requestAnimationFrame(tick);
      const ptr    = ptrRef.current;
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      
      const themeChanged = isDark !== lastIsDark;
      if (themeChanged) lastIsDark = isDark;

      const dotR   = isDark ? 240 / 255 : 10 / 255;
      const dotG   = isDark ? 237 / 255 : 10 / 255;
      const dotB   = isDark ? 232 / 255 : 10 / 255;

      // ── Rotation easing ────────────────────────────────────────────────
      st.entry += (1 - st.entry) * 0.012; // Slower, more epic entry (takes ~4-5s)
      st.focus += ((ptr.active ? 1 : 0) - st.focus) * 0.08;
      st.phase += 0.008 - st.focus * 0.0035;

      const idleMix = 1 - st.focus * 0.68;
      const idleY = Math.sin(st.phase) * 0.12 * idleMix;
      const idleX = Math.cos(st.phase * 0.8) * 0.06 * idleMix;
      // ptr.y negative = mouse up → positive tX = look up (Three.js rotX positive tilts top toward camera)
      const tY = DOT_CUBE_BASE_ROT_Y + idleY - ptr.x * 0.46 * st.focus;
      const tX = DOT_CUBE_BASE_ROT_X + idleX + ptr.y * 0.42 * st.focus;
      st.rotY += (tY - st.rotY) * 0.09;
      st.rotX += (tX - st.rotX) * 0.09;

      // Rotate the whole scene (cube + rings together)
      sceneGroup.rotation.y = -st.rotY;
      sceneGroup.rotation.x = st.rotX;

      // ── Uniforms (Update colors only when theme changes) ───────────────
      if (themeChanged) {
        (cubeMat.uniforms.uColor.value as THREE.Color).setRGB(dotR, dotG, dotB);
        (dustMat.uniforms.uColor.value as THREE.Vector3).set(dotR, dotG, dotB);
        (ashMat.uniforms.uColor.value as THREE.Vector3).set(dotR, dotG, dotB);
        (deepMat.uniforms.uColor.value as THREE.Vector3).set(dotR, dotG, dotB);
        (starMat.uniforms.uColor.value as THREE.Vector3).set(dotR, dotG, dotB);
        cubeMat.uniforms.uIsDark.value = isDark ? 1 : 0;
      }

      // ── Cube uniforms ──────────────────────────────────────────────────
      cubeMat.uniforms.uFocus.value     = st.focus;
      cubeMat.uniforms.uPtrX.value      = ptr.x;
      cubeMat.uniforms.uPtrY.value      = -ptr.y; // flip Y: NDC y+ is up, ptr.y+ is down
      cubeMat.uniforms.uPtrActive.value = ptr.active ? 1 : 0;
      cubeMat.uniforms.uTime.value      = st.phase;
      cubeMat.uniforms.uEntry.value     = st.entry;

      for (let i = 0; i < INTERIOR_DUST_N; i++) {
        const p = INTERIOR_DUST_INIT[i];
        p.phase += p.speed;
        const resonance = Math.sin(st.phase * 1.15 + p.x * 2.1 + p.y * 1.4 + p.z * 1.8);
        dustOp[i] = p.op * (0.72 + Math.sin(p.phase) * 0.16 + Math.cos(p.phase * 0.7) * 0.07 + resonance * 0.07);
      }
      (dustGeo.getAttribute('aOpacity') as THREE.BufferAttribute).needsUpdate = true;

      // ── Rings — orbit around world Y, depth-shading via shader ──────────
      for (let ri = 0; ri < RING_DEFS.length; ri++) {
        const buf = ringBufs[ri];
        // Rotate around world Y so the ring orbits the cube like a planet
        // orbitGroup revolves around world Y; tiltGroup spins in its own plane
        buf.orbitGroup.rotateY(buf.orbitSpeed);
        buf.tiltGroup.rotateY(buf.orbitSpeed * 0.4);
        
        if (themeChanged) {
          for (let j = 0; j < buf.n; j++) {
            buf.colArr[j*4]     = dotR;
            buf.colArr[j*4 + 1] = dotG;
            buf.colArr[j*4 + 2] = dotB;
          }
          buf.arcMat.color.setRGB(dotR, dotG, dotB);
          buf.arcMat.opacity = RING_DEFS[ri].op * (isDark ? 0.34 : 0.28);
          (buf.geo.getAttribute('aColor') as THREE.BufferAttribute).needsUpdate = true;
        }
      }

      // ── Ash ────────────────────────────────────────────────────────────
      const mxW = ptr.x * 2.4, myW = -ptr.y * 2.4;
      for (let i = 0; i < ASH_N; i++) {
        const a = ashes[i];
        a.phase += a.wobble;
        a.vx += Math.sin(a.phase * 1.7) * 0.00005;
        a.vz += Math.cos(a.phase * 1.2) * 0.00004;
        a.vx *= 0.988; a.vy *= 0.994; a.vz *= 0.988;
        if (ptr.active) {
          const dx = a.x - mxW, dy = a.y - myW;
          const dist = Math.hypot(dx, dy);
          if (dist < 2.4 && dist > 0) {
            const pull = st.focus * (1 - dist / 2.4) * 0.0005;
            a.vx -= (dx / dist) * pull; a.vy -= (dy / dist) * pull;
            a.vx += (-dy / dist) * pull * 0.5; a.vy += (dx / dist) * pull * 0.5;
          }
        }
        a.x += a.vx; a.y += a.vy; a.z += a.vz;
        if (a.y > 3.0 || Math.abs(a.x) > 3.5 || Math.abs(a.z) > 3.5) {
          ashes[i] = spawnAsh(); ashOp[i] = 0; continue;
        }
        const fadeT = Math.min(1, (3.0 - a.y) / 0.7);
        const fadeB = Math.min(1, (a.y + 2.8) / 0.5);
        ashPos[i*3] = a.x; ashPos[i*3+1] = a.y; ashPos[i*3+2] = a.z;
        ashSz[i] = a.size; ashOp[i] = a.baseOp * fadeT * fadeB;
      }
      (ashGeo.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
      (ashGeo.getAttribute('aSize')    as THREE.BufferAttribute).needsUpdate = true;
      (ashGeo.getAttribute('aOpacity') as THREE.BufferAttribute).needsUpdate = true;

      // ── Deep field ──────────────────────────────────────────────────────
      const deepDrift = st.galaxyPhase * 0.42;
      for (let i = 0; i < DEEP_FIELD_N; i++) {
        const p = deepField[i];
        p.phase += p.speed;
        const angle = p.angle + deepDrift + Math.sin(p.phase) * 0.012;
        const ca = Math.cos(angle), sa = Math.sin(angle);
        const radiusWobble = p.radius + Math.sin(p.phase * 0.7) * 0.08;
        const z = p.z + sa * 0.62;
        const depth = Math.max(0, Math.min(1, (z + 2.2) / 4.4));
        const centerFade = Math.max(0, Math.min(1, (p.radius - 1.55) / 1.15));
        const twinkle = 0.72 + Math.sin(p.phase * 1.7) * 0.18 + Math.cos(p.phase * 0.8) * 0.10;

        deepPos[i*3]     = ca * radiusWobble;
        deepPos[i*3 + 1] = p.y + Math.cos(p.phase * 0.55) * 0.06;
        deepPos[i*3 + 2] = z;
        deepSz[i] = p.size * (0.68 + depth * 0.24);
        deepOp[i] = p.baseOp * twinkle * centerFade * (0.42 + depth * 0.30);
      }
      (deepGeo.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
      (deepGeo.getAttribute('aSize')    as THREE.BufferAttribute).needsUpdate = true;
      (deepGeo.getAttribute('aOpacity') as THREE.BufferAttribute).needsUpdate = true;

      // ── Stars ──────────────────────────────────────────────────────────
      st.galaxyPhase += 0.00022 + st.focus * 0.00065;
      for (let i = 0; i < STAR_N; i++) {
        const s = stars[i];
        s.phase += s.speed;
        const angle   = s.angle + st.galaxyPhase;
        const ca = Math.cos(angle), sa = Math.sin(angle);
        const depth   = (sa + 1) * 0.5;
        const twinkle = 0.82 + Math.sin(s.phase) * 0.18;
        const y       = -3.5 + sa * s.r * 0.55 + s.zOff;
        const yFade   = Math.max(0, Math.min(1, (-y - 2.2) / 0.4));
        starPos[i*3]   = ca * s.r * 4.5;
        starPos[i*3+1] = y;
        starPos[i*3+2] = -0.5 + sa * s.r * 1.2;
        starSz[i] = (0.5 + s.r * 1.2) * (0.7 + depth * 0.3);
        starOp[i] = (0.06 + depth * 0.28) * twinkle * yFade;
      }
      (starGeo.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
      (starGeo.getAttribute('aSize')    as THREE.BufferAttribute).needsUpdate = true;
      (starGeo.getAttribute('aOpacity') as THREE.BufferAttribute).needsUpdate = true;

      renderer.render(scene, camera);
    }

    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      [cubeGeo, dustGeo, ashGeo, deepGeo, starGeo].forEach(g => g.dispose());
      ringBufs.forEach(b => {
        b.geo.dispose();
        b.arcGeo.dispose();
        b.arcMat.dispose();
        const mesh = b.tiltGroup.children.find(child => child instanceof THREE.Points) as THREE.Points | undefined;
        if (mesh?.material instanceof THREE.Material) mesh.material.dispose();
      });
      cubeMat.dispose();
      dustMat.dispose();
      ashMat.dispose();
      deepMat.dispose();
      starMat.dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className={styles.canvas} />;
}
