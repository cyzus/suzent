// Physics and projection for the GreetingCube orbit rings. Each ring is a real 3D circle,
// projected every frame and split by depth into a far half (drawn behind the cube) and a
// near half (drawn over it). Each ring turns about its own fixed 3D axis, so the three
// tumble in genuinely different directions, and every rotation only ever turns one way:
// engaging the cube boosts its speed and it coasts back down to cruise, the way a flicked
// spinner would. Nothing springs back, since a ring reversing toward a rest pose reads as
// rubber.

export interface OrbitRing {
  radius: number;
  /** Starting rotation of the ring's long axis in the screen plane, degrees. */
  node: number;
  /** Starting angle between the ring plane and the screen, degrees; 90 is edge-on. */
  incline: number;
  /** Axis the whole ring tumbles about, screen space (x right, y down, z toward viewer). */
  axis: [number, number, number];
  /** Cruise speeds, rad/s; the sign fixes each rotation's direction for good. */
  comet: number;
  spin: number;
  /** How hard engaging flicks the tumble; varied so the rings never line up together. */
  spinKick: number;
}

export const ORBIT_RINGS: readonly OrbitRing[] = [
  {
    radius: 86,
    node: -12,
    incline: 78,
    axis: [0.25, 1, 0.15],
    comet: 0.9,
    spin: 0.22,
    spinKick: 3.4,
  },
  {
    radius: 78,
    node: 54,
    incline: 101,
    axis: [1, -0.2, 0.35],
    comet: 0.7,
    spin: -0.17,
    spinKick: 2.4,
  },
  {
    radius: 76,
    node: -58,
    incline: 80,
    axis: [-0.45, 0.35, 1],
    comet: 1.05,
    spin: 0.26,
    spinKick: 4.2,
  },
];

export const COMET_SEGMENTS = 10;
export const REST_SCALE = 0.8;

const PERSPECTIVE = 410;
const RING_SAMPLES = 96;
const DEG = Math.PI / 180;

const COMET_KICK = 17;
// Speed passes through two first-order lags: the boost decays slowly while the speed
// eases toward cruise + boost, so a kick ramps up over a few frames, then coasts down.
const BOOST_DECAY = 0.75;
const SPEED_LAG = 0.14;

export interface Spinner {
  angle: number;
  speed: number;
  boost: number;
}

interface RingState {
  comet: Spinner;
  spin: Spinner;
}

export interface OrbitState {
  visible: number;
  visibleVelocity: number;
  scale: number;
  scaleVelocity: number;
  engaged: boolean;
  rings: RingState[];
}

const spinner = (angle: number, speed: number): Spinner => ({ angle, speed, boost: 0 });

export const createOrbitState = (): OrbitState => ({
  visible: 0,
  visibleVelocity: 0,
  scale: REST_SCALE,
  scaleVelocity: 0,
  engaged: false,
  rings: ORBIT_RINGS.map((ring, i) => ({
    comet: spinner(i * 2.1, ring.comet),
    spin: spinner(0, ring.spin),
  })),
});

const kick = (spin: Spinner, cruise: number, amount: number): void => {
  spin.boost += Math.sign(cruise) * amount;
};

const turn = (spin: Spinner, cruise: number, boostFade: number, speedEase: number, dt: number) => {
  spin.boost *= boostFade;
  spin.speed += (cruise + spin.boost - spin.speed) * speedEase;
  spin.angle += spin.speed * dt;
};

const spring = (
  value: number,
  velocity: number,
  target: number,
  stiffness: number,
  damping: number,
  dt: number
): [number, number] => {
  const nextVelocity = velocity + (-stiffness * (value - target) - damping * velocity) * dt;
  return [value + nextVelocity * dt, nextVelocity];
};

export const stepOrbits = (state: OrbitState, engaged: boolean, dt: number): void => {
  if (engaged && !state.engaged) {
    state.rings.forEach((ring, i) => {
      const config = ORBIT_RINGS[i];
      kick(ring.comet, config.comet, COMET_KICK);
      kick(ring.spin, config.spin, config.spinKick);
    });
  }
  state.engaged = engaged;

  // Critically damped, so neither the fade nor the expansion overshoots and reverses.
  [state.visible, state.visibleVelocity] = spring(
    state.visible,
    state.visibleVelocity,
    engaged ? 1 : 0,
    90,
    19,
    dt
  );
  state.visible = Math.min(1, Math.max(0, state.visible));
  [state.scale, state.scaleVelocity] = spring(
    state.scale,
    state.scaleVelocity,
    engaged ? 1 : REST_SCALE,
    100,
    20,
    dt
  );

  const boostFade = Math.exp(-dt / BOOST_DECAY);
  const speedEase = 1 - Math.exp(-dt / SPEED_LAG);
  state.rings.forEach((ring, i) => {
    const config = ORBIT_RINGS[i];
    turn(ring.comet, config.comet, boostFade, speedEase, dt);
    turn(ring.spin, config.spin, boostFade, speedEase, dt);
  });
};

/** Lets reduced-motion callers jump straight to the settled pose without a kick. */
export const settleOrbits = (state: OrbitState, engaged: boolean): void => {
  state.engaged = engaged;
  state.visible = engaged ? 1 : 0;
  state.visibleVelocity = 0;
  state.scale = 1;
  state.scaleVelocity = 0;
};

export interface RingFrame {
  back: string;
  front: string;
  /** Comet segments, head first; `front` says which layer each belongs to. */
  comet: { d: string; front: boolean }[];
  cometGain: number;
}

type Point = [x: number, y: number, z: number];

const projector = (config: OrbitRing, spinAngle: number) => {
  const node = config.node * DEG;
  const incline = config.incline * DEG;
  const cosN = Math.cos(node);
  const sinN = Math.sin(node);
  const cosI = Math.cos(incline);
  const sinI = Math.sin(incline);
  const length = Math.hypot(...config.axis);
  const [kx, ky, kz] = config.axis.map((c) => c / length);
  const cosS = Math.cos(spinAngle);
  const sinS = Math.sin(spinAngle);

  return (angle: number): Point => {
    const lx = config.radius * Math.cos(angle);
    const ly = config.radius * Math.sin(angle) * cosI;
    const vz = config.radius * Math.sin(angle) * sinI;
    const vx = lx * cosN - ly * sinN;
    const vy = lx * sinN + ly * cosN;
    // Rodrigues rotation of the posed ring about its own tumble axis.
    const dot = kx * vx + ky * vy + kz * vz;
    const x = vx * cosS + (ky * vz - kz * vy) * sinS + kx * dot * (1 - cosS);
    const y = vy * cosS + (kz * vx - kx * vz) * sinS + ky * dot * (1 - cosS);
    const z = vz * cosS + (kx * vy - ky * vx) * sinS + kz * dot * (1 - cosS);
    const f = PERSPECTIVE / (PERSPECTIVE - z);
    return [x * f, y * f, z];
  };
};

const fmt = (n: number): string => n.toFixed(2);

export const buildOrbitFrame = (state: OrbitState): RingFrame[] =>
  ORBIT_RINGS.map((config, i) => {
    const { comet: light, spin } = state.rings[i];
    const project = projector(config, spin.angle);

    let back = '';
    let front = '';
    let previous = project(0);
    let previousLayer: boolean | null = null;
    for (let s = 1; s <= RING_SAMPLES; s += 1) {
      const point = project((s / RING_SAMPLES) * 2 * Math.PI);
      const prevFront = previous[2] >= 0;
      const currFront = point[2] >= 0;

      if (prevFront !== currFront) {
        // Interpolate the exact z = 0 crossing so front/back arcs meet seamlessly without jumping.
        const t = previous[2] / (previous[2] - point[2]);
        const cx = previous[0] + (point[0] - previous[0]) * t;
        const cy = previous[1] + (point[1] - previous[1]) * t;
        const prevSeg =
          (previousLayer === prevFront ? '' : `M${fmt(previous[0])} ${fmt(previous[1])}`) +
          `L${fmt(cx)} ${fmt(cy)}`;
        if (prevFront) front += prevSeg;
        else back += prevSeg;

        const currSeg = `M${fmt(cx)} ${fmt(cy)}L${fmt(point[0])} ${fmt(point[1])}`;
        if (currFront) front += currSeg;
        else back += currSeg;
        previousLayer = currFront;
      } else {
        const segment =
          (previousLayer === currFront ? '' : `M${fmt(previous[0])} ${fmt(previous[1])}`) +
          `L${fmt(point[0])} ${fmt(point[1])}`;
        if (currFront) front += segment;
        else back += segment;
        previousLayer = currFront;
      }
      previous = point;
    }

    // The tail stretches with speed, which reads as motion blur during the kick.
    const speed = Math.abs(light.speed);
    const tail = Math.min(2.6, 0.35 + 0.1 * speed);
    const comet = Array.from({ length: COMET_SEGMENTS }, (_, j) => {
      const start = light.angle - (tail * j) / COMET_SEGMENTS;
      const end = light.angle - (tail * (j + 1)) / COMET_SEGMENTS;
      const a = project(start);
      const m = project((start + end) / 2);
      const b = project(end);
      return {
        d: `M${fmt(a[0])} ${fmt(a[1])}L${fmt(m[0])} ${fmt(m[1])}L${fmt(b[0])} ${fmt(b[1])}`,
        front: m[2] >= 0,
      };
    });

    return { back, front, comet, cometGain: Math.min(1, 0.55 + 0.04 * speed) };
  });
