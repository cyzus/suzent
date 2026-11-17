/**
 * SuzentBotEngine — Self-contained 120Hz spring-physics & spline-morphing character engine.
 *
 * Ported 1:1 from the Suzent × GrokBot v14 reference engine:
 * - 120Hz damped harmonic springs (breathing, 1.08x blink overshoot, autonomous gaze, pointer tracking)
 * - 4-sided 3D perspective turns & interactive gestures (`spinBounce`, `spinDizzy`, `doubleSpin`)
 * - Full-body physical acts (`workout`, `eureka_levitate`, `speed_reader`, `dj_groove`, `peek_radar`, `constellation_command`)
 * - Pure monochrome B&W geometric morphs (`dots`, `radar`, `receive`, `pencil`, `wave`, `orbit`, `send`, `gather`, `progress`, `bang`)
 * - Monochrome ink-to-silver 3D orbital ribbons (`SuzentParticleSystem`, with `[data-trail]` excluded from `--fg` stroke rules)
 */

import {
  CIRCLE_RING,
  EYE_HALF,
  HEAD_C,
  PENCIL_RING,
  Point2D,
  SUZENT_BELT_RADIUS,
  SUZENT_BODY_PATH,
  SUZENT_BODY_RING,
  SUZENT_BOTTOM,
  SUZENT_EXPRESSIONS,
  SUZENT_RADIUS,
  SUZENT_TILT_SCALE,
  SUZENT_TOP,
  centroid,
  clamp,
  lerpRing,
  ringOutline,
  ringPath,
  spanAt,
  suzentSpanAt,
  turnedSuzentRing,
} from "./suzentBotGeometry";
import {
  FIXED_STEP,
  SpringState,
  activeRng,
  cubicInOut,
  random,
  rng,
  useRng,
  smoothstep,
  springValue,
  stepSpring,
} from "./suzentBotPhysics";
import {
  VElement,
  buildSuzentBotTree,
  sceneFromTree,
  type SceneFrame,
} from "./suzentBotScene";
import { SuzentParticleSystem } from "./suzentBotParticles";
import {
  STAGE_SPECS,
  SuzentBotStageId,
  SuzentMorphId,
  evaluateFullBodyAct,
} from "./suzentBotActs";
import {
  MORPH_EFFECT_IDS,
  MORPH_SIZES,
  MorphLayer,
  MorphRenderState,
  renderBangMorph,
  renderDotsMorph,
  renderGatherMorph,
  renderOrbitMorph,
  renderPencilMorph,
  renderProgressMorph,
  renderRadarMorph,
  renderReceiveMorph,
  renderSendMorph,
  renderWaveMorph,
} from "./suzentBotMorphs";

export { MORPH_SIZES };

// Exact v14 global scale constants
const ENGINE_TEMPO = 0.76;
const ENGINE_MOTION_SCALE = 1.15;
const ENGINE_GAZE_SCALE = 1.15;

export interface SuzentBotEngineConfig {
  stage: SuzentBotStageId;
  size: number;
  isPending?: boolean;
  pointer?: boolean;
  particlesEnabled?: boolean;
  autoMorphCycle?: boolean;
  reducedMotion?: boolean;
  dark?: boolean;
  /** When true, an idle bot eases to a held pose and reports `settled` so the host can stop. */
  holdWhenIdle?: boolean;
  svgId?: string;
  clipId?: string;
  /**
   * Element rectangle in the same client-pixel space as `pointerClient`.
   * Without it, the gaze math treats the bot as sitting at the viewport origin.
   */
  bounds?: { left: number; top: number; width: number; height: number };
  /** Viewport pointer, in client pixels. Null releases the gaze. */
  pointerClient?: { x: number; y: number } | null;
}

function hostNow(): number {
  return typeof performance !== "undefined" ? performance.now() : 0;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function")
    return false;
  const dataset =
    typeof document !== "undefined"
      ? document.documentElement?.dataset?.motion
      : undefined;
  return (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    dataset === "reduced"
  );
}

export class SuzentBotEngine {
  private svg: VElement;
  private getConfig: () => SuzentBotEngineConfig;
  private head: VElement;
  private clipHead: VElement;
  private transformGroup: VElement;
  private eyes: VElement[];
  private actBackLayer: VElement;
  private actFrontLayer: VElement;
  private badge: VElement;
  private baseMorphLayer: MorphLayer;
  private morphLayers = new Map<string, MorphLayer>();
  private activeLayer: MorphLayer;
  private particles: SuzentParticleSystem;
  private rng: () => number = Math.random;
  private idleHold = false;
  private heldClock = 0;
  private morphCycleAt = 0;

  private stage: SuzentBotStageId = "idle";
  private startedAt = hostNow();
  private stageStartedAt = this.startedAt;
  private lastTime = this.startedAt;
  private clockTime = this.startedAt;

  private pointer = {
    active: false,
    clientX: 0,
    clientY: 0,
    x: 0,
    y: 0,
    targetX: 0,
    targetY: 0,
  };
  private expressionFrom: [Point2D[], Point2D[]] = [
    SUZENT_EXPRESSIONS[0][0],
    SUZENT_EXPRESSIONS[0][1],
  ];
  private expressionTo: [Point2D[], Point2D[]] = this.expressionFrom;
  private expressionIndex = 0;
  private expressionSpring = springValue(1);
  private expressionFrequency = 7;

  private rotation = springValue(0);
  private headX = springValue(0);
  private headY = springValue(0);
  private scaleY = springValue(1);
  private eyeOpen = springValue(1);
  private eyeScale = springValue(1);
  private aimX = springValue(0);
  private aimY = springValue(0);
  private morph = springValue(0);
  private morphBlend = springValue(1);
  private turn = springValue(0);
  private notify = springValue(0);
  private humming = springValue(0);
  private spinSpring: SpringState | null = null;

  private requestedMorphEffect: Exclude<SuzentMorphId, "none"> | null = null;
  private morphEffect: Exclude<SuzentMorphId, "none"> | null = null;
  private previousMorphEffect: Exclude<SuzentMorphId, "none"> | null = null;
  private morphVisible = false;
  private morphStartedAt = this.startedAt;
  private morphShotStartedAt = this.startedAt;
  private morphPreview: {
    effect: Exclude<SuzentMorphId, "none">;
    duration: number;
    phase: "reset" | "enter" | "hold" | "exit" | "done";
    phaseStartedAt: number;
  } | null = null;

  private turnDirection = 1;
  private spinAngle = 0;
  private particleSpinAngle = 0;
  private expressionCursor = 0;
  private expressionNext = 0;
  private blinkNext = 0;
  private gazeNext = 0;
  private listenNodNext = 0;
  private listenNodUntil = 0;
  private impulseNext = 0;
  private ambientNext = this.startedAt + random(2500, 5000);
  private blinkQueue: Array<{ at: number; value: number }> = [];
  private blinkTarget: number | null = null;
  private behaviorNext = 0;
  private winkAt = -Infinity;
  private winkEye = 0;
  private winkNext = this.startedAt + random(3000, 8000);
  private notifyTriggered = false;
  private receiveCycle = -1;
  private receiveAngle = -0.7;
  private writingTrail: Point2D[] = [];
  private gesture: {
    kind: "spinBounce" | "spinDizzy";
    startedAt: number;
    direction: number;
    turns: number;
  } | null = null;
  private bounceStartedAt = -1;
  private celebrateCycle = -1;
  private celebrateWildActive = false;
  private wideRibbonActive = false;

  private directTurn = 0;
  private directRotation = 0;
  private directX = 0;
  private directY = 0;
  private directGazeX = 0;
  private directGazeY = 0;
  private delta = 1 / 60;

  constructor(getConfig: () => SuzentBotEngineConfig) {
    this.rng = activeRng();
    this.getConfig = getConfig;
    const initialCfg = getConfig();
    const svg = buildSuzentBotTree({
      svgId: initialCfg.svgId || "suzent-bot",
      clipId: initialCfg.clipId || "suzent-bot-clip",
      size: initialCfg.size || 36,
    });
    this.svg = svg;
    this.head = svg.querySelector("#head-path") as VElement;
    this.clipHead = svg.querySelector("#head-clip-path") as VElement;
    this.transformGroup = svg.querySelector("#bot-transform") as VElement;
    this.eyes = svg.querySelectorAll(".eye-path");
    this.actBackLayer = svg.querySelector(".suzent-act-back") as VElement;
    this.actFrontLayer = svg.querySelector(".suzent-act-front") as VElement;
    this.badge = svg.querySelector("#notify-badge") as VElement;

    this.baseMorphLayer = {
      group: null,
      heads: svg.querySelectorAll(".morph-head"),
      rings: svg.querySelectorAll(".morph-ring"),
      parts: svg.querySelectorAll(".morph-part"),
      glyphs: svg.querySelectorAll(".morph-glyph"),
    };
    this.activeLayer = this.baseMorphLayer;

    this.particles = new SuzentParticleSystem(
      svg.querySelector("#particles-back"),
      svg.querySelector("#particles-front"),
      {
        idPrefix: `${svg.id || "suzent-bot"}-`,
        reduceMotion: () => this.motionReduced(),
        radius: () => SUZENT_BELT_RADIUS,
      },
    );

    this.morphCycleAt = this.startedAt + 6800;
    this.setStage(initialCfg.stage, true);
  }

  destroy(): void {
    for (const layer of this.morphLayers.values()) layer.group?.remove();
    this.particles.clear();
  }

  setStage(stage: SuzentBotStageId, immediate = false): void {
    if (!immediate && stage === this.stage) return;
    const now = this.clockTime;
    this.stage = stage;
    this.stageStartedAt = now;
    this.idleHold = false;
    const spec = STAGE_SPECS[stage] ?? STAGE_SPECS.idle;
    const baseState = spec.baseState;
    this.expressionCursor = 0;
    this.expressionNext = now + random(1100, 2000) * ENGINE_TEMPO;
    this.blinkNext = now + random(1500, 5500);
    this.gazeNext = now + random(500, 1400);
    this.listenNodNext = now + random(1200, 2200);
    this.impulseNext = now + random(500, 1200);
    this.behaviorNext =
      now +
      (baseState === "searching"
        ? random(800, 1600)
        : baseState === "working" || baseState === "playful"
          ? random(1200, 2400)
          : random(4000, 8000));
    this.winkNext = now + random(3000, 8000);
    this.blinkQueue = [];
    this.blinkTarget = null;
    this.notifyTriggered = false;
    this.receiveCycle = -1;
    this.writingTrail = [];
    this.morphPreview = null;
    this.celebrateWildActive = false;
    this.morphShotStartedAt = now;
    if (spec.celebrating) {
      this.turnDirection = rng() < 0.5 ? 1 : -1;
      this.celebrateCycle = -1;
    }
    const firstExpr = spec.expressionPool[0] ?? 0;
    this.scheduleBlink(now);
    this.setExpression(firstExpr, 8);
  }

  setExpression(index: number, frequency = 7): void {
    const safeIdx = clamp(index, 0, SUZENT_EXPRESSIONS.length - 1);
    if (safeIdx === this.expressionIndex && this.expressionSpring.target === 1)
      return;
    const amount = clamp(this.expressionSpring.x, 0, 1);
    this.expressionFrom = [
      lerpRing(this.expressionFrom[0], this.expressionTo[0], amount),
      lerpRing(this.expressionFrom[1], this.expressionTo[1], amount),
    ];
    this.expressionTo = [
      SUZENT_EXPRESSIONS[safeIdx][0],
      SUZENT_EXPRESSIONS[safeIdx][1],
    ];
    this.expressionIndex = safeIdx;
    this.expressionSpring.x = 0;
    this.expressionSpring.v = 0;
    this.expressionSpring.target = 1;
    this.expressionFrequency = frequency;
  }

  scheduleBlink(now: number): void {
    this.blinkTarget = this.eyeOpen.target;
    this.blinkQueue.push(
      { at: now, value: 0.05 },
      { at: now + 70, value: 0.05 },
      { at: now + 150, value: 1.08 },
      { at: now + 300, value: 1 },
    );
    if (rng() < 0.14) {
      this.blinkQueue.push(
        { at: now + 370, value: 0.05 },
        { at: now + 480, value: 1 },
      );
    }
  }

  triggerMorphPreview(
    effect: Exclude<SuzentMorphId, "none">,
    duration = 2200,
  ): void {
    this.morphPreview = {
      effect,
      duration: clamp(duration, 200, 15000),
      phase: "reset",
      phaseStartedAt: this.clockTime,
    };
  }

  clearMorphPreview(): void {
    this.morphPreview = null;
  }

  startSpin(turns = 1, direction = rng() < 0.5 ? 1 : -1): boolean {
    if (this.spinSpring) return false;
    this.spinSpring = { x: 0, v: 0, target: turns * Math.PI * 2 * direction };
    return true;
  }

  startGesture(kind: "spinBounce" | "spinDizzy"): void {
    if (this.gesture || this.spinSpring) return;
    const turns = kind === "spinDizzy" ? Math.round(random(3, 4)) : 1;
    this.gesture = {
      kind,
      startedAt: this.clockTime,
      direction: rng() < 0.5 ? 1 : -1,
      turns,
    };
  }

  startBounce(now = this.clockTime): void {
    if (this.bounceStartedAt < 0) this.bounceStartedAt = now;
  }

  triggerInteractiveTrick(cycleIndex = 0): void {
    const mode = cycleIndex % 3;
    if (mode === 0) {
      this.wideRibbonActive = this.startSpin(2);
    } else if (mode === 1) {
      this.startGesture("spinBounce");
    } else {
      this.startGesture("spinDizzy");
      this.particles.burst(18, 0.95, 0.3);
    }
  }

  /** Advance one frame. `now` is the host clock in milliseconds, the same value rAF used to pass. */
  step(realNow: number): SceneFrame {
    useRng(this.rng);
    const rawDelta = Math.max(0, (realNow - this.lastTime) / 1000);
    this.lastTime = realNow;
    const delta = Math.min(rawDelta, 0.1);
    this.delta = delta || 1 / 60;
    this.clockTime += delta * 1000;
    const now = this.clockTime;

    const config = this.getConfig();
    if (config.stage !== this.stage) {
      this.setStage(config.stage, false);
    }
    this.syncPointer(config);
    this.prepareIdleHold(now);
    this.maybeCycleMorph(now);
    const size = config.size || 36;
    const box = config.bounds;
    const boxWidth = box?.width || size;
    const boxHeight = box?.height || size;
    const boxLeft = box?.left ?? 0;
    const boxTop = box?.top ?? 0;
    this.svg.bounds = {
      left: boxLeft,
      top: boxTop,
      width: boxWidth,
      height: boxHeight,
      right: boxLeft + boxWidth,
      bottom: boxTop + boxHeight,
    };

    const isDark =
      config.dark ??
      (typeof document !== "undefined" &&
        document.documentElement.classList.contains("dark"));
    const fg = config.isPending ? "#000000" : isDark ? "#f4f4f5" : "#000000";
    const bg = config.isPending ? "#ffe666" : isDark ? "#18181b" : "#ffffff";
    this.svg.style.setProperty("--fg", fg);
    this.svg.style.setProperty("--bg", bg);

    this.updateMorph(now);
    this.updateStateTargets(now, delta);
    this.stepPhysics(delta, this.motionReduced());
    this.render(now, config, fg, bg);

    if (
      this.spinSpring &&
      Math.abs(this.spinSpring.target - this.spinSpring.x) < 0.004 &&
      Math.abs(this.spinSpring.v) < 0.015
    ) {
      this.spinSpring = null;
      this.wideRibbonActive = false;
    }

    const spec = STAGE_SPECS[this.stage] ?? STAGE_SPECS.idle;
    if (this.spinSpring) this.particleSpinAngle = this.spinSpring.x;
    else if (Math.abs(this.directTurn) > 0.001)
      this.particleSpinAngle = this.directTurn;
    else if (spec.humming) this.particleSpinAngle = this.spinAngle;

    const width = this.svg.getBoundingClientRect().width || config.size || 24;
    const sizeScale = clamp((340 / Math.max(width, 16)) ** 0.7, 1, 2.6);
    this.particles.update(now, delta, {
      spinAngle: this.particleSpinAngle,
      sizeScale,
      wideStyle:
        spec.humming || this.celebrateWildActive || this.wideRibbonActive,
      enabled:
        config.particlesEnabled !== false && this.morphEffect !== "pencil",
      dark: isDark,
    });

    return sceneFromTree(this.svg, { fg, bg, settled: this.isSettled() });
  }

  private motionReduced(): boolean {
    const flag = this.getConfig().reducedMotion;
    if (typeof flag === "boolean") return flag;
    return prefersReducedMotion();
  }

  private syncPointer(config: SuzentBotEngineConfig): void {
    const client =
      config.pointer === false ? null : (config.pointerClient ?? null);
    this.pointer.active = client !== null;
    if (client) {
      this.pointer.clientX = client.x;
      this.pointer.clientY = client.y;
    }
  }

  private prepareIdleHold(now: number): void {
    const config = this.getConfig();
    if (
      this.motionReduced() ||
      !config.holdWhenIdle ||
      this.stage !== "idle" ||
      this.pointer.active ||
      this.gesture ||
      this.spinSpring ||
      this.morphPreview ||
      this.morph.x > 0.02
    ) {
      this.idleHold = false;
      return;
    }
    if (now - this.stageStartedAt < 900) {
      this.idleHold = false;
      return;
    }
    if (!this.idleHold) this.heldClock = now;
    this.idleHold = true;
  }

  private maybeCycleMorph(now: number): void {
    if (now < this.morphCycleAt) return;
    this.morphCycleAt = now + 6800;
    const config = this.getConfig();
    if (config.autoMorphCycle === false || this.motionReduced()) return;
    const spec = STAGE_SPECS[this.stage] ?? STAGE_SPECS.idle;
    if (spec.cycleMorph !== "none") {
      const dur = spec.cycleMorph === "pencil" ? 3200 : 1750;
      this.triggerMorphPreview(spec.cycleMorph, dur);
    }
  }

  private isSettled(): boolean {
    if (this.motionReduced()) return true;
    if (!this.idleHold) return false;
    const springs = [
      this.expressionSpring,
      this.rotation,
      this.headX,
      this.headY,
      this.scaleY,
      this.eyeOpen,
      this.eyeScale,
      this.aimX,
      this.aimY,
      this.morph,
      this.morphBlend,
      this.turn,
      this.notify,
      this.humming,
    ];
    return springs.every(
      (spring) =>
        Math.abs(spring.v) < 0.04 && Math.abs(spring.x - spring.target) < 0.04,
    );
  }

  private stepPhysics(delta: number, reducedMotion: boolean): void {
    const steps = Math.max(1, Math.ceil(delta / FIXED_STEP));
    const step = delta / steps;
    for (let i = 0; i < steps; i += 1) {
      stepSpring(this.expressionSpring, this.expressionFrequency, 1, step);
      stepSpring(this.rotation, 5, 0.9, step);
      stepSpring(this.headX, 3.5, 1, step);
      stepSpring(this.headY, 4, 1, step);
      stepSpring(this.scaleY, 10, 0.8, step);
      stepSpring(this.eyeOpen, 26, 1, step);
      stepSpring(this.eyeScale, 9, 0.85, step);
      stepSpring(this.aimX, 13, 1, step);
      stepSpring(this.aimY, 13, 1, step);
      stepSpring(this.morph, 14, 1, step);
      stepSpring(this.morphBlend, 11, 1, step);
      stepSpring(this.turn, 14, 1, step);
      stepSpring(this.notify, 9, 0.55, step);
      stepSpring(this.humming, 6, 1, step);
      if (this.spinSpring) stepSpring(this.spinSpring, 6.2, 1, step);
    }
    if (reducedMotion) {
      const snap = (spring: SpringState) => {
        spring.x = spring.target;
        spring.v = 0;
      };
      snap(this.expressionSpring);
      snap(this.rotation);
      snap(this.headX);
      snap(this.headY);
      snap(this.scaleY);
      snap(this.eyeOpen);
      snap(this.eyeScale);
      snap(this.aimX);
      snap(this.aimY);
      snap(this.morph);
      snap(this.morphBlend);
      snap(this.turn);
      snap(this.notify);
      snap(this.humming);
      if (this.spinSpring) snap(this.spinSpring);
    }
  }

  private updateMorph(now: number): void {
    let requestedEffect: Exclude<SuzentMorphId, "none"> | null = null;
    if (this.morphPreview) {
      const preview = this.morphPreview;
      if (preview.phase === "reset") {
        requestedEffect = null;
        if (this.morph.x < 0.004) {
          preview.phase = "enter";
          preview.phaseStartedAt = now;
          requestedEffect = preview.effect;
        }
      } else if (preview.phase === "enter") {
        requestedEffect = preview.effect;
        if (this.morph.x > 0.996) {
          preview.phase = "hold";
          preview.phaseStartedAt = now;
        }
      } else if (preview.phase === "hold") {
        requestedEffect = preview.effect;
        if (now - preview.phaseStartedAt >= preview.duration) {
          preview.phase = "exit";
          preview.phaseStartedAt = now;
          requestedEffect = null;
        }
      } else if (preview.phase === "exit") {
        requestedEffect = null;
        if (this.morph.x < 0.004) {
          preview.phase = "done";
          preview.phaseStartedAt = now;
        }
      }
    }

    if (requestedEffect !== this.requestedMorphEffect) {
      this.requestedMorphEffect = requestedEffect;
      this.morphShotStartedAt = now;
    }

    const visible = Boolean(requestedEffect);
    this.morph.target = visible ? 1 : 0;

    if (requestedEffect && requestedEffect !== this.morphEffect) {
      if (this.morphEffect && this.morph.x > 0.02) {
        this.previousMorphEffect = this.morphEffect;
        this.morphBlend.x = 0;
        this.morphBlend.v = 0;
        this.morphBlend.target = 1;
      } else {
        this.previousMorphEffect = null;
        this.morphBlend.x = 1;
        this.morphBlend.v = 0;
        this.morphBlend.target = 1;
      }
      this.morphEffect = requestedEffect;
      this.morphStartedAt = now;
      this.writingTrail = [];
    }

    if (!requestedEffect && this.morph.x < 0.004) {
      this.morphEffect = null;
      this.previousMorphEffect = null;
      this.morphBlend.x = 1;
      this.morphBlend.v = 0;
      this.morphBlend.target = 1;
    }
    if (this.previousMorphEffect && this.morphBlend.x > 0.996) {
      this.previousMorphEffect = null;
    }

    if (visible !== this.morphVisible) {
      if (visible && !this.motionReduced())
        this.turnDirection = rng() < 0.5 ? 1 : -1;
      if (!this.motionReduced())
        this.turn.target += Math.PI * this.turnDirection;
      this.morphVisible = visible;
    }
  }

  private updateStateTargets(now: number, delta: number): void {
    const elapsed = (now - this.stageStartedAt) / 1000;
    const runtime = (now - this.startedAt) / 1000;
    const spec = STAGE_SPECS[this.stage] ?? STAGE_SPECS.idle;
    const baseState = spec.baseState;

    let eyeOpen = 1;
    let eyeScale = 1;
    let rotation = 0;
    let x = 0;
    let y = 0;
    let scaleY = 1;

    const gesture = this.motionReduced()
      ? this.emptyGesture()
      : this.updateGestures(now);

    if (this.motionReduced()) {
      this.setExpression(spec.expressionPool[0] ?? 0);
    } else if (!this.idleHold) {
      switch (baseState) {
        case "idle":
          rotation =
            1.5 * Math.sin(0.5 * runtime) + 0.6 * Math.sin(0.17 * runtime);
          x = Math.sin(0.27 * runtime);
          y = 1.2 * Math.sin(0.85 * runtime);
          scaleY = 1 + 0.007 * Math.sin(0.85 * runtime);
          break;
        case "listening":
          rotation = 8 + 1.5 * Math.sin(0.5 * runtime);
          x = 2;
          y = -2 + 0.8 * Math.sin(0.8 * runtime);
          scaleY = 1.015;
          if (now >= this.listenNodNext) {
            this.listenNodUntil = now + 380;
            this.listenNodNext = now + random(1800, 3200);
          }
          if (now < this.listenNodUntil) {
            const phase = 1 - (this.listenNodUntil - now) / 380;
            y += 4.5 * Math.sin(phase * Math.PI);
            rotation += 2 * Math.sin(phase * Math.PI);
          }
          break;
        case "thinking":
          rotation = -9 + 5 * Math.sin(0.35 * runtime);
          x = 5 * Math.sin(0.3 * runtime);
          y = 2.5 * Math.sin(0.6 * runtime);
          break;
        case "searching": {
          const wave = Math.sin(1.3 * runtime);
          rotation = 13 * wave;
          x = 7 * wave;
          y = 3 * Math.sin(1.7 * runtime);
          break;
        }
        case "working": {
          const wave = Math.sin(runtime * Math.PI * 3.2);
          rotation = 4 + 2.5 * wave;
          x = 3;
          y = 1.5 + 3 * Math.max(0, wave);
          scaleY = 1 - 0.02 * Math.max(0, wave);
          break;
        }
        case "suspicious":
          rotation = -6 + 3 * Math.sin(0.3 * runtime);
          x = -4 * Math.sin(0.25 * runtime);
          y = 1 + 1.2 * Math.sin(0.45 * runtime);
          eyeOpen = 0.85;
          if (now >= this.impulseNext) {
            this.rotation.v += (30 * Math.PI) / 180;
            this.impulseNext = now + random(4000, 7000);
          }
          break;
        case "curious":
          rotation = 10 + 6 * Math.sin(0.7 * runtime);
          x = 5 * Math.sin(0.6 * runtime);
          y = -2 + 1.5 * Math.sin(0.9 * runtime);
          scaleY = 1.01;
          eyeScale = 1.08;
          if (now >= this.listenNodNext) {
            this.listenNodUntil = now + 440;
            this.listenNodNext = now + random(1600, 2800);
          }
          if (now < this.listenNodUntil) {
            const phase = 1 - (this.listenNodUntil - now) / 440;
            x += 8 * Math.sin(phase * Math.PI);
            rotation += 5 * Math.sin(phase * Math.PI);
          }
          break;
        case "playful":
          rotation = 8 * Math.sin(1.4 * runtime);
          x = 4 * Math.sin(1.1 * runtime);
          y = -3 * Math.abs(Math.sin(2.2 * runtime));
          scaleY = 1 + 0.015 * Math.sin(2.2 * runtime);
          eyeScale = 1.06;
          break;
        case "humming":
          rotation = 2 * Math.sin(0.4 * runtime);
          x = 1.5 * Math.sin(0.3 * runtime);
          y = 1.5 * Math.sin(0.7 * runtime);
          break;
        case "notifying":
          if (!this.notifyTriggered && elapsed > 0.12) {
            this.notifyTriggered = true;
            this.headY.v -= 26;
            this.scheduleBlink(now);
          }
          eyeScale = 1 + 0.05 * Math.exp(-3 * elapsed);
          rotation = 3;
          x = 2;
          y = -1;
          break;
        case "celebrate": {
          y = -2.5 * Math.abs(Math.sin(1.6 * runtime));
          eyeScale = 1.1;
          eyeOpen = 1.1;
          Object.assign(gesture, this.celebratePose(elapsed));
          break;
        }
        default:
          break;
      }

      const blinkOverride = this.updateExpressionAndBlink(now, spec);
      if (blinkOverride !== null) {
        eyeOpen = blinkOverride;
      }
      this.updateAim(now, baseState);
    }

    if (gesture.eyeOpen !== null) eyeOpen = gesture.eyeOpen;
    if (gesture.eyeScale !== null) eyeScale = gesture.eyeScale;
    this.directTurn = gesture.turn;
    this.directRotation = gesture.rotation;
    this.directX = gesture.x;
    this.directY = gesture.y + gesture.bounceY;
    this.directGazeX = gesture.gazeX;
    this.directGazeY = gesture.gazeY;

    if (!(this.idleHold && baseState === "idle")) {
      this.rotation.target = (rotation * ENGINE_MOTION_SCALE * Math.PI) / 180;
      this.headX.target = x * ENGINE_MOTION_SCALE;
      this.headY.target = y * ENGINE_MOTION_SCALE;
      this.scaleY.target = scaleY;
      this.eyeOpen.target = eyeOpen;
      this.eyeScale.target = eyeScale;
      this.notify.target = spec.notifying ? 1 : 0;
      this.humming.target = spec.humming ? 1 : 0;
    }

    if (spec.humming && !this.motionReduced()) {
      const speed =
        elapsed < 0.5
          ? 7 * cubicInOut(elapsed / 0.5)
          : elapsed < 1.3
            ? 7 + (1.6 - 7) * cubicInOut((elapsed - 0.5) / 0.8)
            : 1.6 + 0.3 * Math.sin(0.5 * elapsed);
      this.spinAngle += speed * delta;
    } else if (!spec.celebrating) {
      this.spinAngle *= 0.94;
    }
  }

  private updateExpressionAndBlink(
    now: number,
    spec: (typeof STAGE_SPECS)[SuzentBotStageId],
  ): number | null {
    if (now >= this.expressionNext) {
      const pool = spec.expressionPool;
      if (pool.length) {
        this.expressionCursor =
          (this.expressionCursor +
            1 +
            Math.floor(random(0, Math.max(pool.length - 1, 1)))) %
          pool.length;
        this.setExpression(
          pool[this.expressionCursor],
          spec.baseState === "searching" ? 10 : 6,
        );
      }
      this.expressionNext = now + random(1100, 2000) * ENGINE_TEMPO;
    }

    if (now >= this.blinkNext) {
      this.scheduleBlink(now);
      this.blinkNext = now + random(2500, 5500) * ENGINE_TEMPO;
    }

    while (this.blinkQueue.length && now >= this.blinkQueue[0].at) {
      this.blinkTarget = this.blinkQueue.shift()!.value;
    }
    if (this.blinkQueue.length) return this.blinkTarget;
    if (this.blinkTarget !== null) {
      const finalValue = this.blinkTarget;
      this.blinkTarget = null;
      return finalValue;
    }
    return null;
  }

  private updateAim(now: number, baseState: string): void {
    if (now < this.gazeNext) return;
    const direction = () => (rng() < 0.5 ? -1 : 1);
    let x = 0;
    let y = 0;
    let min = 2500;
    let max = 5000;
    switch (baseState) {
      case "idle":
        min = 2500;
        max = 5500;
        break;
      case "listening":
        x = 15 * random(-0.3, 0.3);
        y = 9 * random(-0.25, 0.25);
        min = 2200;
        max = 4200;
        break;
      case "thinking":
        x = direction() * random(0.5, 1) * 15;
        y = -9 * random(0.4, 1);
        min = 1500;
        max = 2800;
        break;
      case "searching":
        x = direction() * random(0.7, 1) * 15;
        y = 9 * random(-1, 1);
        min = 550;
        max = 1150;
        break;
      case "working":
        x = 15 * random(-0.4, 0.4);
        y = 9 * random(0.4, 1);
        min = 1200;
        max = 2400;
        break;
      case "suspicious":
        x = 15 * direction();
        y = 2.7;
        min = 2200;
        max = 4200;
        break;
      case "curious":
        x = direction() * random(0.6, 1) * 15;
        y = 9 * random(-1, 1);
        min = 950;
        max = 1900;
        break;
      case "playful":
        x = direction() * random(0.5, 1) * 15;
        y = -9 * random(0, 0.6);
        min = 900;
        max = 1800;
        break;
      case "notifying": {
        const focused = rng() < 0.72;
        x = (focused ? 0.45 : 0.1) * 15;
        y = -9 * (focused ? 0.3 : 0.05);
        min = 1200;
        max = 2400;
        break;
      }
      default:
        x = 15 * random(-0.4, 0.4);
        y = 9 * random(-0.3, 0.3);
    }
    this.aimX.target = x * ENGINE_GAZE_SCALE;
    this.aimY.target = y * ENGINE_GAZE_SCALE;
    this.gazeNext = now + random(min, max) * ENGINE_TEMPO;
  }

  private emptyGesture() {
    return {
      turn: 0,
      rotation: 0,
      x: 0,
      y: 0,
      bounceY: 0,
      gazeX: 0,
      gazeY: 0,
      eyeOpen: null as number | null,
      eyeScale: null as number | null,
    };
  }

  private updateGestures(now: number) {
    const spec = STAGE_SPECS[this.stage] ?? STAGE_SPECS.idle;
    const baseState = spec.baseState;
    const out = this.emptyGesture();
    if (
      ["idle", "curious", "playful"].includes(baseState) &&
      now >= this.winkNext
    ) {
      this.winkAt = now;
      this.winkEye = rng() < 0.5 ? 0 : 1;
      this.winkNext = now + random(4500, 10000);
    }
    if (now >= this.behaviorNext && !this.gesture && !this.spinSpring) {
      if (baseState === "searching") {
        this.startSpin();
        this.behaviorNext = now + random(4000, 7000);
      } else if (baseState === "working") {
        this.startSpin(1, 1);
        this.behaviorNext = now + random(6000, 9000);
      } else if (baseState === "playful") {
        this.startSpin(1);
        this.behaviorNext = now + random(3500, 6000);
      }
    }
    if (now >= this.ambientNext) {
      if (!this.gesture && !this.spinSpring && baseState === "playful") {
        const roll = rng();
        if (roll < 0.34) this.startGesture("spinBounce");
        else if (roll < 0.62) this.startBounce(now);
        else if (roll < 0.86) this.startGesture("spinDizzy");
        else this.startSpin(1);
      }
      this.ambientNext = now + random(9000, 18000);
    }
    if (this.gesture) {
      const elapsed = (now - this.gesture.startedAt) / 1000;
      const { kind, direction, turns } = this.gesture;
      if (kind === "spinBounce") {
        if (elapsed < 0.7) {
          out.turn =
            turns * Math.PI * 2 * direction * cubicInOut(elapsed / 0.7);
        } else {
          this.startBounce(now);
          this.gesture = null;
        }
      } else if (kind === "spinDizzy") {
        const spinDur = 0.55 + 0.16 * turns;
        if (elapsed < spinDur) {
          out.turn = turns * Math.PI * 2 * direction * (elapsed / spinDur) ** 2;
        } else if (elapsed < spinDur + 1.5) {
          const st = elapsed - spinDur;
          const env = (1 - st / 1.5) ** 1.3;
          out.rotation = 17 * Math.sin(10 * st) * direction * env;
          out.x = 10 * Math.cos(10 * st) * direction * env;
          out.y = 3 * Math.sin(20 * st) * env;
          out.eyeOpen = 0.46 + 0.14 * Math.sin(21 * st);
          out.eyeScale = 1.03;
        } else {
          this.gesture = null;
        }
      }
    }
    if (this.bounceStartedAt >= 0) {
      const seq = [
        { h: 48, d: 0.5 },
        { h: 28, d: 0.382 },
        { h: 14, d: 0.27 },
        { h: 6, d: 0.177 },
      ];
      let elapsed = (now - this.bounceStartedAt) / 1000;
      let step = 0;
      while (step < seq.length && elapsed >= seq[step].d) {
        elapsed -= seq[step].d;
        step += 1;
      }
      if (step >= seq.length) this.bounceStartedAt = -1;
      else {
        const phase = elapsed / seq[step].d;
        out.bounceY = -4 * seq[step].h * phase * (1 - phase);
      }
    }
    return out;
  }

  private celebratePose(elapsed: number) {
    const out = this.emptyGesture();
    this.celebrateWildActive = false;
    const activeElapsed = elapsed - 0.14;
    if (activeElapsed < 0 || this.motionReduced()) return out;
    const cycleIndex = Math.floor(activeElapsed / 6.2);
    if (cycleIndex !== this.celebrateCycle) {
      this.celebrateCycle = cycleIndex;
      this.turnDirection = rng() < 0.5 ? 1 : -1;
    }
    const cycle = activeElapsed % 6.2;
    if (cycle > 5.49) return out;
    this.celebrateWildActive = true;
    const turns = 9;
    const dir = this.turnDirection;
    const speed = (turns * Math.PI * 2 + 0.5) / (0.15 + 2 + 0.3125);
    let angle = 0;
    if (cycle < 0.24) angle = -0.25 * (1 - Math.cos((cycle / 0.24) * Math.PI));
    else if (cycle < 0.54) {
      const t = cycle - 0.24;
      angle = -0.5 + (speed * t * t) / 0.6;
    } else if (cycle < 2.54) angle = -0.5 + speed * (0.15 + cycle - 0.54);
    else if (cycle < 3.79) {
      angle =
        -0.5 +
        speed * 2.15 +
        (1.25 * speed * (1 - (1 - (cycle - 2.54) / 1.25) ** 4)) / 4;
    } else angle = turns * Math.PI * 2;
    out.turn = angle * dir;

    let envelope = 0;
    if (cycle > 2.54) {
      const progress = Math.min((cycle - 2.54) / 1.25, 1);
      envelope = progress < 0.4 ? 0 : ((progress - 0.4) / 0.6) ** 2;
      if (cycle >= 3.79)
        envelope = Math.max(0, (1 - (cycle - 3.79) / 1.7) ** 1.6);
    }
    const shakeTime = Math.max(cycle - 2.54, 0);
    out.rotation =
      (angle / (turns * Math.PI * 2)) * 1080 * dir +
      11 * Math.sin(9.2 * shakeTime) * dir * envelope;
    out.x = (Math.cos(9.2 * shakeTime) - 1) * 6 * dir * envelope;
    out.y = 2.6 * Math.sin(18.4 * shakeTime) * envelope;
    out.gazeX = 13 * Math.sin(11.5 * shakeTime) * dir * envelope;
    out.gazeY = (Math.cos(9 * shakeTime) - 1) * 3.5 * envelope;
    out.eyeOpen =
      1.14 - 0.44 * envelope + 0.1 * Math.sin(16 * shakeTime) * envelope;
    out.eyeScale = 1.12 - 0.09 * envelope;
    return out;
  }

  private renderHummingMarkers(): void {
    const amount = clamp(this.humming.x, 0, 1);
    if (amount <= 0.01) return;
    for (let index = 0; index < 2; index += 1) {
      const element = this.baseMorphLayer.parts[3 + index];
      if (!element) continue;
      const angle = 0.85 * this.spinAngle + index * Math.PI;
      const radius = 1.3 * SUZENT_RADIUS;
      const depth = 0.55 + 0.45 * clamp((Math.cos(angle) + 1) / 2, 0, 1);
      element.style.display = "";
      element.setAttribute(
        "cx",
        (HEAD_C + radius * Math.sin(angle)).toFixed(1),
      );
      element.setAttribute(
        "cy",
        (HEAD_C - 0.38 * radius * Math.cos(angle) - 8).toFixed(1),
      );
      element.setAttribute("r", (7.5 * depth * amount).toFixed(2));
      element.setAttribute(
        "opacity",
        ((0.3 + 0.7 * depth) * amount).toFixed(3),
      );
    }
  }

  private render(
    now: number,
    config: SuzentBotEngineConfig,
    fg: string,
    bg: string,
  ): void {
    const morphAmount = clamp(this.morph.x, 0, 1);
    const morphBlend = clamp(this.morphBlend.x, 0, 1);
    const prevMorphEffect =
      morphBlend < 0.999 ? this.previousMorphEffect : null;
    const morphIsTurning =
      this.morph.x > 0.001 || Math.abs(this.turn.target - this.turn.x) > 0.01;
    const morphTurn = morphIsTurning ? this.turn.x : 0;
    const turnAngle = morphTurn + (this.spinSpring?.x ?? 0) + this.directTurn;

    const shapeRing =
      Math.abs(turnAngle) > 0.001
        ? turnedSuzentRing(SUZENT_BODY_RING, turnAngle)
        : SUZENT_BODY_RING;

    const spec = STAGE_SPECS[this.stage] ?? STAGE_SPECS.idle;
    const elapsedSec = Math.max(0, (now - this.stageStartedAt) / 1000);
    const actList = spec.acts?.length ? spec.acts : [spec.act];
    const activeAct =
      actList[Math.floor(elapsedSec / 4.2) % actList.length] ?? spec.act;
    const baseRot =
      ((this.rotation.x * 180) / Math.PI) * SUZENT_TILT_SCALE +
      this.directRotation;
    const actPose = evaluateFullBodyAct(activeAct, elapsedSec, morphAmount, {
      x: this.headX.x + this.directX,
      y: this.headY.x + this.directY,
      rot: baseRot,
    });
    if (actPose.gazeX || actPose.gazeY) {
      this.directGazeX += actPose.gazeX;
      this.directGazeY += actPose.gazeY;
    }
    this.actBackLayer.innerHTML = actPose.backHtml;
    this.actFrontLayer.innerHTML = actPose.frontHtml;

    const actRingBlend =
      actPose.targetRing && actPose.ringBlend
        ? clamp(actPose.ringBlend, 0, 1)
        : 0;
    const baseShapeRing =
      actRingBlend > 0.001 && actPose.targetRing
        ? lerpRing(shapeRing, actPose.targetRing, actRingBlend)
        : shapeRing;

    const activeMorphRing =
      this.morphEffect === "pencil" ? PENCIL_RING : CIRCLE_RING;
    const prevMorphRing =
      prevMorphEffect === "pencil" ? PENCIL_RING : CIRCLE_RING;
    const morphRing = prevMorphEffect
      ? lerpRing(prevMorphRing, activeMorphRing, cubicInOut(morphBlend))
      : activeMorphRing;
    const morphPathAmount = clamp(morphAmount / 0.62, 0, 1);
    const headRing =
      morphPathAmount <= 0
        ? baseShapeRing
        : lerpRing(baseShapeRing, morphRing, cubicInOut(morphPathAmount));
    const headPath =
      morphPathAmount <= 0 && actRingBlend <= 0.001
        ? Math.abs(turnAngle) > 0.001
          ? ringOutline(shapeRing)
          : SUZENT_BODY_PATH
        : ringOutline(headRing);

    this.head.setAttribute("d", headPath);
    this.clipHead.setAttribute("d", headPath);

    // Render eyes with actPose gaze overrides, then morph effects & humming markers
    this.renderEyes(
      now,
      config,
      shapeRing,
      turnAngle,
      actPose.hideEyes ? 1 : morphAmount,
    );

    const effect = this.morphEffect;
    const activeMorphSize = effect ? MORPH_SIZES[effect] : 19;
    const prevMorphSize = prevMorphEffect
      ? MORPH_SIZES[prevMorphEffect]
      : activeMorphSize;
    const morphSize =
      activeMorphSize * morphBlend + prevMorphSize * (1 - morphBlend);
    const morphScale = morphSize / HEAD_C;
    const effectPose = this.renderMorphEffects(
      morphAmount,
      morphBlend,
      prevMorphEffect,
      morphSize,
      now,
    );

    this.renderHummingMarkers();

    const normal = 1 - morphAmount;
    const translateX =
      (this.headX.x + this.directX + actPose.x) * normal + effectPose.x;
    const translateY =
      (this.headY.x + this.directY + actPose.y) * normal + effectPose.y;
    const rotation = (baseRot + actPose.rot) * normal + effectPose.rotation;
    const scaleX =
      actPose.sx * normal + morphScale * effectPose.scale * morphAmount;
    const scaleY =
      this.scaleY.x * actPose.sy * normal +
      morphScale * effectPose.scale * morphAmount;

    this.transformGroup.setAttribute(
      "transform",
      `translate(${(HEAD_C + translateX).toFixed(2)} ${(HEAD_C + translateY).toFixed(2)}) rotate(${rotation.toFixed(2)}) scale(${scaleX.toFixed(4)} ${scaleY.toFixed(4)}) translate(${-HEAD_C} ${-HEAD_C})`,
    );
    this.transformGroup.style.opacity = effectPose.opacity.toFixed(3);

    const badgeAmount = clamp(this.notify.x, 0, 1.4);
    if (badgeAmount <= 0.01) {
      this.badge.setAttribute("style", "display:none");
    } else {
      const badgeAnchor =
        shapeRing[Math.round((7 * shapeRing.length) / 8) % shapeRing.length];
      this.badge.setAttribute("style", "");
      this.badge.setAttribute("fill", fg);
      this.badge.setAttribute("stroke", bg);
      this.badge.setAttribute("stroke-width", "10");
      this.badge.setAttribute("cx", badgeAnchor[0].toFixed(1));
      this.badge.setAttribute("cy", badgeAnchor[1].toFixed(1));
      this.badge.setAttribute("r", (20 * badgeAmount).toFixed(2));
    }
  }

  private renderEyes(
    now: number,
    config: SuzentBotEngineConfig,
    shapeRing: Point2D[],
    turnAngle: number,
    morphAmount: number,
  ): void {
    const amount = clamp(this.expressionSpring.x, 0, 1);
    const eyeRings = [
      lerpRing(this.expressionFrom[0], this.expressionTo[0], amount),
      lerpRing(this.expressionFrom[1], this.expressionTo[1], amount),
    ];
    const centers = eyeRings.map(centroid);
    let top = SUZENT_TOP;
    let bottom = SUZENT_BOTTOM;
    if (Math.abs(turnAngle) > 0.001) {
      top = Math.min(...shapeRing.map((p) => p[1]));
      bottom = Math.max(...shapeRing.map((p) => p[1]));
    }

    let leftHalf = 0;
    let rightHalf = 0;
    for (const pt of eyeRings[0])
      leftHalf = Math.max(leftHalf, Math.abs(pt[0] - centers[0][0]));
    for (const pt of eyeRings[1])
      rightHalf = Math.max(rightHalf, Math.abs(pt[0] - centers[1][0]));
    const distance = Math.abs(centers[1][0] - centers[0][0]);
    const fit =
      leftHalf + rightHalf > 0.5
        ? clamp((distance + 24) / (leftHalf + rightHalf), 1.02, 4)
        : 4;

    if (config.pointer !== false && this.pointer.active) {
      const bounds = this.svg.getBoundingClientRect();
      this.pointer.targetX =
        22 *
        clamp(
          (this.pointer.clientX - (bounds.left + bounds.width / 2)) /
            bounds.width,
          -0.6,
          0.6,
        );
      this.pointer.targetY =
        14 *
        clamp(
          (this.pointer.clientY - (bounds.top + bounds.height / 2)) /
            bounds.height,
          -0.6,
          0.6,
        );
    } else {
      this.pointer.targetX = 0;
      this.pointer.targetY = 0;
    }
    const smoothing = 1 - Math.exp(60 * Math.log(0.91) * this.delta);

    for (let index = 0; index < 2; index += 1) {
      this.pointer.x += (this.pointer.targetX - this.pointer.x) * smoothing;
      this.pointer.y += (this.pointer.targetY - this.pointer.y) * smoothing;
      const el = this.eyes[index];
      const ring = eyeRings[index];
      const [centerX, centerY] = centers[index];
      el.setAttribute("d", ringPath(ring));

      let localCenter = HEAD_C;
      let offsetX = centerX - HEAD_C;
      let perspectiveX = 1;
      let visible = true;
      let perspectiveFade = 1;

      if (Math.abs(turnAngle) > 0.001) {
        const [left, right] = spanAt(
          shapeRing,
          clamp(centerY, top + 2, bottom - 2),
        );
        const radius = Math.max((right - left) / 2, 12);
        localCenter = (left + right) / 2;
        const initial = Math.asin(clamp(offsetX / radius, -1, 1));
        const turned = initial + turnAngle;
        const cosine = Math.cos(turned);
        const baseCosine = Math.max(Math.cos(initial), 0.02);
        visible = cosine > 0.02;
        perspectiveX = Math.max(cosine, 0.02) / baseCosine;
        offsetX = radius * Math.sin(turned);
        perspectiveFade = smoothstep(clamp(cosine / 0.5, 0, 1));
      }

      const pulse = 1 + 0.07 * Math.sin(amount * Math.PI);
      const driftNow = this.motionReduced()
        ? 0
        : this.idleHold
          ? this.heldClock
          : now;
      let driftX =
        1.4 * Math.sin(0.00042 * driftNow + index) +
        0.5 * Math.sin(0.001 * driftNow + 2 * index);
      let driftY = 0.9 * Math.sin(0.00058 * driftNow + index);
      const autoGazeWeight =
        config.pointer !== false && this.pointer.active ? 0.2 : 1;
      driftX +=
        this.pointer.x + this.aimX.x * autoGazeWeight + this.directGazeX;
      driftY +=
        this.pointer.y + this.aimY.x * autoGazeWeight + this.directGazeY;

      const notification = clamp(this.notify.x, 0, 1);
      driftX -= 10 * notification;
      driftY += 7 * notification;

      const eyeScale = Math.min(clamp(this.eyeScale.x, 0.2, 2), fit / pulse);
      const scaleX = clamp(perspectiveX * eyeScale * pulse, 0.02, 2.4);
      let winkScale = 1;
      if (index === this.winkEye && now < this.winkAt + 320) {
        const phase = (now - this.winkAt) / 320;
        winkScale = Math.max(
          phase < 0.42 ? 1 - phase / 0.42 : (phase - 0.42) / 0.58,
          0.04,
        );
      }
      const scaleY = clamp(
        Math.max(this.eyeOpen.x * winkScale, 0.04) * eyeScale * pulse,
        0.02,
        2.4,
      );
      el.style.display = visible && morphAmount < 0.5 ? "" : "none";

      const halfHeight = EYE_HALF * scaleY + 2;
      const y = clamp(centerY + driftY, top + halfHeight, bottom - halfHeight);
      let maxLeft = -Infinity;
      let minRight = Infinity;
      for (let pt = 0; pt < ring.length; pt += 2) {
        const scaledX = (ring[pt][0] - centerX) * scaleX;
        const sampleY = y + (ring[pt][1] - centerY) * scaleY;
        const [left, right] =
          Math.abs(turnAngle) > 0.001
            ? spanAt(shapeRing, sampleY)
            : suzentSpanAt(shapeRing, sampleY);
        maxLeft = Math.max(maxLeft, left - scaledX);
        minRight = Math.min(minRight, right - scaledX);
      }
      const desired = localCenter + offsetX + driftX;
      const bounded =
        maxLeft <= minRight
          ? clamp(desired, maxLeft, minRight)
          : (maxLeft + minRight) / 2;
      let finalX = bounded + (desired - bounded) * (1 - perspectiveFade);
      let finalY = y;

      if (notification > 0.01) {
        const badgeAnchor =
          shapeRing[Math.round((7 * shapeRing.length) / 8) % shapeRing.length];
        const dx = finalX - badgeAnchor[0];
        const dy = finalY - badgeAnchor[1];
        const dist = Math.hypot(dx, dy) || 1;
        const dirX = dx / dist;
        const dirY = dy / dist;
        const eyeHalf = index === 0 ? leftHalf : rightHalf;
        const needed =
          20 * clamp(this.notify.x, 0, 1.4) +
          Math.hypot(eyeHalf * scaleX * dirX, EYE_HALF * scaleY * dirY) +
          5;
        if (dist < needed) {
          finalX += dirX * (needed - dist);
          finalY += dirY * (needed - dist);
        }
      }

      el.setAttribute(
        "transform",
        `translate(${finalX.toFixed(2)} ${finalY.toFixed(2)}) scale(${scaleX.toFixed(4)} ${scaleY.toFixed(4)}) translate(${(-centerX).toFixed(2)} ${(-centerY).toFixed(2)})`,
      );
    }
  }

  private createMorphLayer(effect: string): MorphLayer {
    const group = new VElement("g");
    group.setAttribute("class", "morph-effect-layer");
    group.setAttribute("data-morph-effect", effect);
    const create = (
      tag: string,
      className: string,
      count: number,
      filled = false,
    ): VElement[] =>
      Array.from({ length: count }, () => {
        const el = new VElement(tag);
        el.setAttribute("class", className);
        if (filled) {
          el.setAttribute("fill", "var(--fg)");
        }
        if (tag === "circle") {
          el.setAttribute("cx", String(HEAD_C));
          el.setAttribute("cy", String(HEAD_C));
          el.setAttribute("r", "0");
        }
        el.style.display = "none";
        group.appendChild(el);
        return el;
      });
    const layer: MorphLayer = {
      group,
      heads: create("path", "grok-bot-mark__head morph-head", 2, true),
      rings: create("circle", "morph-ring", 5, false),
      parts: create("circle", "grok-bot-mark__head morph-part", 5, true),
      glyphs: create("path", "morph-glyph", 3, false),
    };
    this.svg.insertBefore(group, this.transformGroup);
    this.morphLayers.set(effect, layer);
    return layer;
  }

  private hideLayerElements(layer: MorphLayer): void {
    for (const el of [
      ...layer.heads,
      ...layer.rings,
      ...layer.parts,
      ...layer.glyphs,
    ]) {
      el.style.display = "none";
    }
  }

  private renderMorphEffects(
    morphAmount: number,
    morphBlend: number,
    prevMorphEffect: Exclude<SuzentMorphId, "none"> | null,
    morphSize: number,
    now: number,
  ) {
    this.hideLayerElements(this.baseMorphLayer);
    for (const layer of this.morphLayers.values()) {
      if (layer.group) layer.group.style.display = "none";
    }
    const pose = { x: 0, y: 0, rotation: 0, scale: 1, opacity: 1 };
    if (!this.morphEffect || morphAmount <= 0.004) return pose;

    const effectAmount = (eff: Exclude<SuzentMorphId, "none">) => {
      if (eff === this.morphEffect) return morphAmount * morphBlend;
      if (eff === prevMorphEffect) return morphAmount * (1 - morphBlend);
      return 0;
    };
    const elapsed = now - this.stageStartedAt;
    const morphState: MorphRenderState = {
      stageStartedAt: this.stageStartedAt,
      morphStartedAt: this.morphStartedAt,
      morphShotStartedAt: this.morphShotStartedAt,
      receiveCycle: this.receiveCycle,
      receiveAngle: this.receiveAngle,
      writingTrail: this.writingTrail,
      reducedMotion: this.motionReduced(),
    };

    for (const eff of MORPH_EFFECT_IDS) {
      const amount = effectAmount(eff);
      if (amount <= 0.004) continue;
      const layer = this.morphLayers.get(eff) || this.createMorphLayer(eff);
      if (layer.group) layer.group.style.display = "";
      this.activeLayer = layer;
      this.hideLayerElements(layer);

      switch (eff) {
        case "dots": {
          renderDotsMorph(layer, amount, now, morphState);
          const dist = Math.abs(
            (((((now - this.morphStartedAt) / 1400 + 0.119) % 1) + 1) % 1) -
              1 / 3,
          );
          const pulseDist = Math.min(dist, 1 - dist);
          const pulse = morphState.reducedMotion
            ? 1
            : Math.exp(-(pulseDist ** 2) / 0.045);
          const pop = morphState.reducedMotion ? 1 : 0.84 + 0.22 * pulse;
          pose.scale *= 1 + (pop - 1) * (amount / Math.max(morphAmount, 0.001));
          pose.y -= morphState.reducedMotion
            ? 0
            : 9 * pulse * amount * morphAmount;
          pose.opacity *=
            1 - (morphState.reducedMotion ? 0 : 0.5 * (1 - pulse)) * amount;
          break;
        }
        case "orbit":
          renderOrbitMorph(layer, amount, now, morphState.reducedMotion);
          break;
        case "radar":
          renderRadarMorph(
            layer,
            amount,
            now,
            morphSize,
            morphState.reducedMotion,
          );
          break;
        case "progress":
          renderProgressMorph(layer, amount, now, morphState);
          break;
        case "gather":
          renderGatherMorph(layer, amount, now, morphState);
          break;
        case "wave":
          renderWaveMorph(layer, amount, now, morphState.reducedMotion);
          break;
        case "send": {
          renderSendMorph(layer, amount, now, morphState);
          if (!morphState.reducedMotion) {
            const phase = (((elapsed / 1500) % 1) + 1) % 1;
            pose.scale *=
              1 +
              (phase < 0.18
                ? -0.06 * Math.sin((phase / 0.18) * Math.PI)
                : phase < 0.42
                  ? 0.05 * Math.sin(((phase - 0.18) / 0.24) * Math.PI)
                  : 0) *
                amount;
          }
          break;
        }
        case "receive": {
          renderReceiveMorph(layer, amount, now, morphState);
          this.receiveCycle = morphState.receiveCycle;
          this.receiveAngle = morphState.receiveAngle;
          if (!morphState.reducedMotion) {
            const phase = clamp(
              (((((elapsed / 1700) % 1) + 1) % 1) - 0.58) / 0.34,
              0,
              1,
            );
            pose.scale *= 1 + 0.11 * Math.sin(phase * Math.PI) * amount;
          }
          break;
        }
        case "pencil": {
          const p = renderPencilMorph(layer, amount, now, morphState);
          this.writingTrail = morphState.writingTrail;
          pose.x += p.x * amount * morphAmount;
          pose.y += p.y * amount * morphAmount;
          pose.rotation += p.rotation * amount * morphAmount;
          break;
        }
        case "bang":
          renderBangMorph(layer, amount, now, morphState);
          pose.y += 58 * amount * morphAmount;
          if (!morphState.reducedMotion) {
            pose.scale *=
              1 + 0.04 * Math.exp(-((elapsed / 1000) % 2.2) * 5.5) * amount;
          }
          break;
        default:
          break;
      }
    }
    this.activeLayer = this.baseMorphLayer;
    return pose;
  }
}
