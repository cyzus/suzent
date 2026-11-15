/**
 * Monochrome B&W 3D orbital ink-ribbon & stardust particle system for the Suzent Bot Engine.
 *
 * Projects 3D orbital trajectories into front (`z >= 0`) and back (`z < 0`) SVG ribbon layers
 * with ink-to-silver monochrome gradients (`hsl(0 0% L%)`), plus monochrome stardust bursts.
 */

import { HEAD_C, STAR_PATH, clamp } from './suzentBotGeometry';
import { random } from './suzentBotPhysics';

const MONO_COLORS = ['#09090b', '#27272a', '#52525b', '#71717a', '#a1a1aa', '#d4d4d8'];
const SVG_NS = 'http://www.w3.org/2000/svg';

interface OrbitPoint {
  x: number;
  y: number;
  angle: number;
  z: number;
}

interface OrbitConfig {
  angle: number;
  angularVelocity: number;
  tilt: number;
  roll: number;
  radius: number;
  radiusVelocity: number;
  follow: number;
  carry: number;
  arc: number;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  returnAmount: number;
  life: number;
  max: number;
  radius: number;
  rotation: number;
  rotationSpeed: number;
  curl: number;
  color: string;
  round: boolean;
  isStar: boolean;
  hue: number;
  hueSpan: number;
  hueVelocity: number;
  orbit: OrbitConfig | null;
  history: OrbitPoint[];
  element: SVGElement | null;
  trailElement?: SVGPathElement;
  trailFrontElement?: SVGPathElement;
  gradientElement?: SVGLinearGradientElement;
  stops?: SVGStopElement[];
}

export class SuzentParticleSystem {
  private back: SVGGElement | null;
  private front: SVGGElement | null;
  private idPrefix: string;
  private reduceMotion: () => boolean;
  private getRadius: () => number;
  private particles: Particle[] = [];
  private spinAngle = random(0, Math.PI * 2);
  private lastSpinAngle = 0;
  private angularVelocity = 0;
  private trailActive = false;
  private emissionQueue: Array<{ at: number; index: number }> = [];
  private gradientIndex = 0;
  private orbitLayouts: Array<{ tilt: number; roll: number }> = [];
  private hue = 0;
  private orbitCount = 4;
  private sizeScale = 1;
  private wideStyle = false;

  constructor(
    back: SVGGElement | null,
    front: SVGGElement | null,
    options: { idPrefix: string; reduceMotion: () => boolean; radius: () => number }
  ) {
    this.back = back;
    this.front = front;
    this.idPrefix = options.idPrefix;
    this.reduceMotion = options.reduceMotion;
    this.getRadius = options.radius;
  }

  clear(): void {
    for (const p of this.particles) {
      p.element?.remove();
      p.trailElement?.remove();
      p.trailFrontElement?.remove();
      p.gradientElement?.remove();
    }
    this.particles = [];
  }

  private resetOrbitStyle(layoutCount = 1): void {
    const roll = random(-0.85, 0.85);
    this.orbitLayouts = Array.from({ length: layoutCount }, (_, index) => ({
      tilt: random(0.16, 0.5),
      roll: roll + (index * Math.PI) / layoutCount + random(-0.12, 0.12),
    }));
    this.orbitCount = layoutCount > 1 ? 3 * layoutCount : Math.round(random(3, 5));
    this.hue = random(0, 360);
  }

  private spawnOrbitParticle(angle: number, direction: number, index: number): void {
    if (this.particles.length > 90) return;
    if (!this.orbitLayouts.length) this.resetOrbitStyle();
    const layout = this.orbitLayouts[index % this.orbitLayouts.length];
    const countPerLayout = Math.max(Math.ceil(this.orbitCount / this.orbitLayouts.length) - 1, 1);
    const baseRadius = 114 * (this.getRadius() / HEAD_C);
    this.particles.push({
      x: HEAD_C,
      y: HEAD_C,
      vx: 0,
      vy: 0,
      returnAmount: 0,
      life: 0,
      max: 9,
      radius:
        this.orbitCount <= 3
          ? random(8, 10.5)
          : this.orbitCount === 4
            ? random(6.6, 8.6)
            : random(5.6, 7.4),
      rotation: random(0, 360),
      rotationSpeed: random(-240, 240),
      curl: 0,
      color: MONO_COLORS[Math.floor(Math.random() * MONO_COLORS.length)],
      round: true,
      isStar: false,
      hue: this.hue + (360 * index) / Math.max(this.orbitCount, 1) + random(-14, 14),
      hueSpan: random(45, 95) * (Math.random() < 0.5 ? 1 : -1),
      hueVelocity: random(18, 42) * (Math.random() < 0.5 ? 1 : -1),
      orbit: {
        angle,
        angularVelocity: direction * random(0.5, 1.1),
        tilt: layout.tilt + random(-0.04, 0.04),
        roll: layout.roll + random(-0.05, 0.05),
        radius:
          baseRadius +
          Math.floor(index / this.orbitLayouts.length) * (34 / countPerLayout) +
          random(-1.5, 1.5),
        radiusVelocity: random(0, 2.2),
        follow: random(0.74, 0.94),
        carry: 0,
        arc: random(2.2, 3.4),
      },
      history: [],
      element: null,
    });
  }

  burst(count = 18, force = 1, curl = 0): void {
    if (this.reduceMotion() || !this.back || this.particles.length > 100) return;
    for (let i = 0; i < count; i += 1) {
      const angle = (i / count) * Math.PI * 2 + random(-0.35, 0.35);
      const distance = random(94, 114) * (this.getRadius() / HEAD_C);
      const speed = random(170, 340) * force;
      const tangentX = -Math.sin(angle);
      const tangentY = Math.cos(angle);
      const curlVelocity = curl * speed * 0.2;
      const isStar = Math.random() < 0.22;
      const round = !isStar && Math.random() < 0.35;
      this.particles.push({
        element: null,
        x: HEAD_C + Math.cos(angle) * distance,
        y: HEAD_C + Math.sin(angle) * distance,
        vx: Math.cos(angle) * speed + tangentX * curlVelocity,
        vy: Math.sin(angle) * speed + tangentY * curlVelocity - random(20, 75),
        life: 0,
        max: random(0.45, 0.85),
        radius: isStar ? random(4, 7) : random(3.5, 8),
        rotation: random(0, 360),
        rotationSpeed: random(-260, 260),
        curl: 0,
        color: MONO_COLORS[Math.floor(Math.random() * MONO_COLORS.length)],
        isStar,
        round,
        returnAmount: 0,
        hue: 0,
        hueSpan: 0,
        hueVelocity: 0,
        orbit: null,
        history: [],
      });
    }
  }

  private projectOrbit(orbit: OrbitConfig, angle: number): { x: number; y: number } {
    const horizontal = orbit.radius * Math.sin(angle);
    const vertical = -orbit.radius * Math.cos(angle) * Math.sin(orbit.tilt);
    const cosine = Math.cos(orbit.roll);
    const sine = Math.sin(orbit.roll);
    return {
      x: HEAD_C + horizontal * cosine - vertical * sine,
      y: HEAD_C + horizontal * sine + vertical * cosine,
    };
  }

  private orbitDepth(orbit: OrbitConfig, angle: number): number {
    return Math.cos(angle) * Math.cos(orbit.tilt);
  }

  private trailPaths(points: OrbitPoint[], width: number): { front: string; back: string } {
    const round = (v: number) => Math.round(v * 10) / 10;
    let length = 0;
    for (let i = 1; i < points.length; i += 1) {
      length += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    }
    if (length < 2) return { front: '', back: '' };
    const actualWidth = Math.min(width, 0.34 * length);
    const normalX: number[] = [];
    const normalY: number[] = [];
    for (let i = 0; i < points.length; i += 1) {
      const prev = points[i > 0 ? i - 1 : 0];
      const next = points[i < points.length - 1 ? i + 1 : points.length - 1];
      let dx = next.x - prev.x;
      let dy = next.y - prev.y;
      const mag = Math.hypot(dx, dy) || 1;
      dx /= mag;
      dy /= mag;
      const halfWidth = (actualWidth * (0.5 + (i / (points.length - 1)) * 0.5)) / 2;
      normalX.push(-dy * halfWidth);
      normalY.push(dx * halfWidth);
    }
    const cap = (idx: number) => {
      const r = Math.max(Math.hypot(normalX[idx], normalY[idx]), 0.2);
      return `A${round(r)} ${round(r)} 0 0 0 `;
    };
    const segment = (start: number, end: number) => {
      let path = '';
      for (let i = start; i <= end; i += 1) {
        path += `${i === start ? 'M' : 'L'}${round(points[i].x + normalX[i])} ${round(points[i].y + normalY[i])}`;
      }
      path += end === points.length - 1 ? cap(end) : 'L';
      for (let i = end; i >= start; i -= 1) {
        path += `${i === end ? '' : 'L'}${round(points[i].x - normalX[i])} ${round(points[i].y - normalY[i])}`;
      }
      if (start === 0) {
        path += `${cap(0)}${round(points[0].x + normalX[0])} ${round(points[0].y + normalY[0])}`;
      }
      return `${path}Z`;
    };

    let front = '';
    let back = '';
    let cursor = 0;
    while (cursor < points.length) {
      const isFront = points[cursor].z >= 0;
      let end = cursor;
      while (end + 1 < points.length && points[end + 1].z >= 0 === isFront) end += 1;
      const segStart = Math.max(cursor - 1, 0);
      const segEnd = Math.min(end + 1, points.length - 1);
      if (segEnd > segStart) {
        const p = segment(segStart, segEnd);
        if (isFront) front += p;
        else back += p;
      }
      cursor = end + 1;
    }
    return { front, back };
  }

  update(
    now: number,
    delta: number,
    options: { spinAngle: number; sizeScale: number; wideStyle: boolean; enabled?: boolean }
  ): void {
    this.sizeScale = options.sizeScale;
    this.spinAngle = options.spinAngle;
    this.wideStyle = options.wideStyle;
    if (options.enabled === false) {
      if (this.particles.length) this.clear();
      this.emissionQueue = [];
      this.trailActive = false;
      this.angularVelocity = 0;
      this.lastSpinAngle = this.spinAngle;
      return;
    }
    let diff = this.spinAngle - this.lastSpinAngle;
    if (!Number.isFinite(diff) || Math.abs(diff) > 1.2) diff = 0;
    this.lastSpinAngle = this.spinAngle;
    const wasSpinning = Math.abs(this.angularVelocity) >= 0.9;
    this.angularVelocity = delta > 0 ? diff / delta : 0;
    const isSpinning = Math.abs(this.angularVelocity) >= 0.9;
    if (!wasSpinning && isSpinning) {
      this.resetOrbitStyle(this.wideStyle ? 3 : 1);
      this.trailActive = false;
    }
    if (wasSpinning && !isSpinning) this.emissionQueue = [];
    if (!this.reduceMotion() && this.back) {
      if (!this.trailActive && Math.abs(this.angularVelocity) >= 5) {
        this.trailActive = true;
        this.emissionQueue = Array.from({ length: this.orbitCount }, (_, index) => ({
          at: now + index * random(55, 105),
          index,
        }));
      }
      while (this.emissionQueue.length && now >= this.emissionQueue[0].at) {
        const queued = this.emissionQueue.shift()!;
        this.spawnOrbitParticle(
          this.spinAngle - random(0, 0.18),
          Math.sign(this.angularVelocity) || 1,
          queued.index
        );
      }
    }

    const alive: Particle[] = [];
    const isDarkTheme =
      typeof document !== 'undefined' && document.documentElement.classList.contains('dark');

    for (const p of this.particles) {
      p.life += delta;
      const progress = clamp(p.life / p.max, 0, 1);
      if (p.orbit) {
        const shouldReturn = !isSpinning || progress > 0.55;
        p.returnAmount = clamp(p.returnAmount + (shouldReturn ? delta / 0.5 : -delta / 0.35), 0, 1);
        if (p.returnAmount >= 1) {
          p.trailElement?.remove();
          p.trailFrontElement?.remove();
          p.gradientElement?.remove();
          continue;
        }
      } else if (p.life >= p.max) {
        p.element?.remove();
        continue;
      }

      const opacity = p.orbit
        ? Math.min(1, p.life / 0.26)
        : progress < 0.1
          ? progress / 0.1
          : (1 - (progress - 0.1) / 0.9) ** 1.7;

      if (p.orbit && this.back) {
        const orbit = p.orbit;
        if (isSpinning) {
          orbit.carry = this.angularVelocity * orbit.follow;
          orbit.angle += this.angularVelocity * delta * orbit.follow + orbit.angularVelocity * delta;
        } else {
          orbit.angle += (orbit.carry + orbit.angularVelocity) * delta;
          orbit.carry *= Math.exp(-2.6 * delta);
          orbit.angularVelocity *= Math.exp(-2.6 * delta);
        }
        orbit.radius += orbit.radiusVelocity * delta;
        const pos = this.projectOrbit(orbit, orbit.angle);
        p.x = pos.x;
        p.y = pos.y;
        const depth = this.orbitDepth(orbit, orbit.angle);
        const depthScale = 0.72 + 0.28 * clamp(depth, 0, 1);
        const enter = Math.min(p.life / 0.34, 1);
        const smoothEnter = enter * enter * (3 - 2 * enter);
        const width = Math.max(
          p.radius * depthScale * 1.7 * this.sizeScale * smoothEnter * (1 - 0.72 * p.returnAmount ** 2),
          0.5
        );

        if (!p.trailElement) {
          const trail = document.createElementNS(SVG_NS, 'path');
          trail.setAttribute('data-trail', '');
          trail.setAttribute('stroke', 'none');
          const grad = document.createElementNS(SVG_NS, 'linearGradient');
          const gradId = `${this.idPrefix}t${this.gradientIndex++}`;
          grad.setAttribute('id', gradId);
          grad.setAttribute('gradientUnits', 'userSpaceOnUse');
          p.stops = [];
          for (let i = 0; i < 5; i += 1) {
            const stop = document.createElementNS(SVG_NS, 'stop');
            stop.setAttribute('offset', (i / 4).toFixed(3));
            grad.appendChild(stop);
            p.stops.push(stop);
          }
          this.back.appendChild(grad);
          p.gradientElement = grad;
          trail.setAttribute('fill', `url(#${gradId})`);
          this.back.appendChild(trail);
          p.trailElement = trail;
          const frontTrail = document.createElementNS(SVG_NS, 'path');
          frontTrail.setAttribute('data-trail', '');
          frontTrail.setAttribute('stroke', 'none');
          frontTrail.setAttribute('fill', `url(#${gradId})`);
          this.front?.appendChild(frontTrail);
          p.trailFrontElement = frontTrail;
        }

        const history = p.history;
        const prevAngle = history.length ? history[history.length - 1].angle : orbit.angle;
        const angleChange = orbit.angle - prevAngle;
        const subdivisions = Math.min(Math.ceil(Math.abs(angleChange) / 0.09), 24);
        for (let i = 1; i <= subdivisions; i += 1) {
          const a = prevAngle + (angleChange * i) / subdivisions;
          const pt = this.projectOrbit(orbit, a);
          history.push({ x: pt.x, y: pt.y, angle: a, z: this.orbitDepth(orbit, a) });
        }
        if (!history.length) {
          history.push({ x: p.x, y: p.y, angle: orbit.angle, z: depth });
        }
        const arc = orbit.arc * (1 - p.returnAmount ** 2 * (3 - 2 * p.returnAmount));
        while (history.length > 2 && Math.abs(orbit.angle - history[0].angle) > arc) {
          history.shift();
        }
        const excess = Math.abs(orbit.angle - history[0].angle) - arc;
        if (history.length >= 2 && excess > 0) {
          const a = history[0].angle + Math.sign(orbit.angle - history[0].angle) * excess;
          const pt = this.projectOrbit(orbit, a);
          history[0] = { x: pt.x, y: pt.y, angle: a, z: this.orbitDepth(orbit, a) };
        }
        if (history.length > 48) history.splice(0, history.length - 48);

        if (history.length >= 2 && p.stops && p.gradientElement) {
          const paths = this.trailPaths(history, width);
          const trailOp = opacity.toFixed(3);
          p.trailElement.setAttribute('d', paths.back);
          p.trailElement.setAttribute('opacity', trailOp);
          p.trailFrontElement?.setAttribute('d', paths.front);
          p.trailFrontElement?.setAttribute('opacity', trailOp);
          const hue = p.hue + p.hueVelocity * p.life;
          for (let i = 0; i < p.stops.length; i += 1) {
            const posRatio = i / (p.stops.length - 1);
            const wave = 0.5 + 0.5 * Math.sin(hue * 0.04 + posRatio * Math.PI * 1.4);
            const lightness = isDarkTheme ? 42 + 48 * wave : 8 + 58 * wave;
            p.stops[i].setAttribute('stop-color', `hsl(0 0% ${lightness.toFixed(0)}%)`);
          }
          const first = history[0];
          const last = history[history.length - 1];
          p.gradientElement.setAttribute('x1', first.x.toFixed(1));
          p.gradientElement.setAttribute('y1', first.y.toFixed(1));
          p.gradientElement.setAttribute('x2', last.x.toFixed(1));
          p.gradientElement.setAttribute('y2', last.y.toFixed(1));
        } else {
          p.trailElement.setAttribute('opacity', '0');
          p.trailFrontElement?.setAttribute('opacity', '0');
        }
        alive.push(p);
        continue;
      }

      if (!this.back) continue;
      p.x += p.vx * delta;
      p.y += p.vy * delta;
      const drag = 0.94 ** (60 * delta);
      p.vx *= drag;
      p.vy = p.vy * drag + 40 * delta;
      const size = Math.max(p.radius * (1 - 0.4 * progress), 0.5);

      if (!p.element) {
        p.element = document.createElementNS(
          SVG_NS,
          p.isStar ? 'path' : p.round ? 'circle' : 'rect'
        );
        if (p.isStar) p.element.setAttribute('d', STAR_PATH);
        p.element.setAttribute('fill', p.color);
        this.back.appendChild(p.element);
      }
      p.element.setAttribute('opacity', opacity.toFixed(3));
      if (p.isStar) {
        p.rotation += p.rotationSpeed * delta;
        p.element.setAttribute(
          'transform',
          `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) rotate(${p.rotation.toFixed(1)}) scale(${size.toFixed(2)})`
        );
      } else if (p.round) {
        p.element.setAttribute('cx', p.x.toFixed(1));
        p.element.setAttribute('cy', p.y.toFixed(1));
        p.element.setAttribute('r', size.toFixed(2));
      } else {
        const w = Math.max(2 * size, Math.min(0.05 * Math.hypot(p.vx, p.vy), 30));
        const h = 1.5 * size;
        p.element.setAttribute('width', w.toFixed(1));
        p.element.setAttribute('height', h.toFixed(1));
        p.element.setAttribute('rx', (h / 2).toFixed(2));
        p.element.setAttribute('x', (p.x - w / 2).toFixed(1));
        p.element.setAttribute('y', (p.y - h / 2).toFixed(1));
        p.element.setAttribute(
          'transform',
          `rotate(${((Math.atan2(p.vy, p.vx) * 180) / Math.PI).toFixed(1)} ${p.x.toFixed(1)} ${p.y.toFixed(1)})`
        );
      }
      alive.push(p);
    }
    this.particles = alive;
  }
}
