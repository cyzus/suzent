/**
 * Frame-data parity against the DOM engine captured before the render-agnostic
 * core. Same seed, same rAF timestamps, same scene tree.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createContext, runInContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

import {
  STAGE_SPECS,
  type SuzentBotStageId,
  type SuzentMorphId,
} from '../../../packages/suzent-bot-core/src/suzentBotActs';
import {
  SuzentBotEngine,
  type SuzentBotEngineConfig,
} from '../../../packages/suzent-bot-core/src/suzentBotEngine';
import { useRng } from '../../../packages/suzent-bot-core/src/suzentBotPhysics';
import {
  type SceneFrame,
  parseSvgFragment,
  portableMulberry32,
} from '../../../packages/suzent-bot-core/src/suzentBotScene';

const FIXTURE = resolve(
  import.meta.dirname,
  '../../../packages/mobile-contract/suzent-bot-frames.json'
);

interface Fixture {
  seed: number;
  times: number[];
  scenarios: Array<{
    stage: SuzentBotStageId;
    morph: Exclude<SuzentMorphId, 'none'> | null;
    frames: Array<{ at: number; scene: SceneFrame }>;
  }>;
}

function replay(
  stage: SuzentBotStageId,
  morph: Exclude<SuzentMorphId, 'none'> | null,
  times: number[]
): SceneFrame[] {
  const previous = globalThis.performance;
  Object.assign(globalThis, { performance: { now: () => 0 } });
  useRng(portableMulberry32(1));
  const config: SuzentBotEngineConfig = {
    stage,
    size: 36,
    isPending: stage === 'approval',
    pointer: false,
    particlesEnabled: true,
    autoMorphCycle: false,
    svgId: 'suzent-bot-test',
    clipId: 'suzent-bot-clip-test',
    holdWhenIdle: false,
    reducedMotion: false,
    dark: false,
  };
  const engine = new SuzentBotEngine(() => config);
  const frames = times.map((at) => {
    if (at === 1000 && morph) engine.triggerMorphPreview(morph, morph === 'pencil' ? 3200 : 1750);
    return engine.step(at);
  });
  engine.destroy();
  Object.assign(globalThis, { performance: previous });
  return frames;
}

describe('suzent bot frame parity', () => {
  const fixture = JSON.parse(readFileSync(FIXTURE, 'utf8')) as Fixture;

  it('matches the legacy engine scene at every captured stage and timestamp', () => {
    for (const scenario of fixture.scenarios) {
      const frames = replay(scenario.stage, scenario.morph, fixture.times);
      expect(frames, scenario.stage).toEqual(scenario.frames.map((frame) => frame.scene));
    }
  });

  it('keeps every morph still under reduced motion and settles on the first frame', () => {
    const morphs = Object.keys(STAGE_SPECS).flatMap((stage) => {
      const morph = STAGE_SPECS[stage as SuzentBotStageId].cycleMorph;
      return morph === 'none' ? [] : [morph];
    });
    for (const morph of new Set(morphs)) {
      Object.assign(globalThis, { performance: { now: () => 0 } });
      useRng(portableMulberry32(3));
      const config: SuzentBotEngineConfig = {
        stage: 'idle',
        size: 36,
        pointer: false,
        particlesEnabled: false,
        autoMorphCycle: false,
        reducedMotion: true,
        holdWhenIdle: false,
      };
      const engine = new SuzentBotEngine(() => config);
      expect(engine.step(0).settled, morph).toBe(true);
      engine.triggerMorphPreview(morph, 4000);
      engine.step(0);
      engine.step(32);
      const morphNodes = (frame: SceneFrame) =>
        frame.nodes.filter((node) => node.attrs['data-morph-effect'] === morph);
      const held = engine.step(64);
      const later = engine.step(4000);
      expect(morphNodes(later), morph).toEqual(morphNodes(held));
      expect(morphNodes(held).length, morph).toBe(1);
      engine.destroy();
    }
  });

  it('stops changing once an idle bot has settled', () => {
    Object.assign(globalThis, { performance: { now: () => 0 } });
    useRng(portableMulberry32(5));
    const config: SuzentBotEngineConfig = {
      stage: 'idle',
      size: 36,
      pointer: false,
      autoMorphCycle: false,
      particlesEnabled: false,
      holdWhenIdle: true,
      reducedMotion: false,
    };
    const engine = new SuzentBotEngine(() => config);
    let settled = false;
    let last = '';
    for (let at = 0; at <= 4000; at += 16) {
      const frame = engine.step(at);
      last = JSON.stringify(frame);
      if (frame.settled) {
        settled = true;
        break;
      }
    }
    expect(settled).toBe(true);
    expect(JSON.stringify(engine.step(5000))).toBe(last);
    engine.destroy();
  });

  it('runs the mobile bundle to the same frames as the desktop engine', () => {
    const bundlePath = resolve(
      import.meta.dirname,
      '../../../packages/SuzentCore/Sources/SuzentCore/Resources/suzent-bot-core.js'
    );
    const sandbox = { performance: { now: () => 0 } };
    createContext(sandbox);
    runInContext(readFileSync(bundlePath, 'utf8'), sandbox);
    const bot = (
      sandbox as unknown as {
        SuzentBot: {
          create: (seed: number, json: string) => number;
          step: (id: number, json: string) => string;
          destroy: (id: number) => void;
          resolveStage: (json: string) => string;
        };
      }
    ).SuzentBot;
    expect(bot.resolveStage(JSON.stringify({ toolName: 'WebSearch', isActive: true }))).toBe(
      'searching'
    );
    for (const scenario of fixture.scenarios) {
      const id = bot.create(
        1,
        JSON.stringify({
          stage: scenario.stage,
          size: 36,
          isPending: scenario.stage === 'approval',
          holdWhenIdle: false,
          particlesEnabled: true,
          autoMorphCycle: false,
          reducedMotion: false,
          dark: false,
          svgId: 'suzent-bot-test',
          clipId: 'suzent-bot-clip-test',
        })
      );
      fixture.times.forEach((at, index) => {
        const input: Record<string, unknown> = {
          stage: scenario.stage,
          time: at,
          size: 36,
          isPending: scenario.stage === 'approval',
          reducedMotion: false,
          dark: false,
          particlesEnabled: true,
          autoMorphCycle: false,
          holdWhenIdle: false,
          svgId: 'suzent-bot-test',
          clipId: 'suzent-bot-clip-test',
        };
        if (at === 1000 && scenario.morph) {
          input.morph = scenario.morph;
          input.morphDuration = scenario.morph === 'pencil' ? 3200 : 1750;
        }
        expect(JSON.parse(bot.step(id, JSON.stringify(input))), `${scenario.stage}@${at}`).toEqual(
          scenario.frames[index].scene
        );
      });
      bot.destroy(id);
    }
  });

  it('parses the act markup subset into elements', () => {
    const nodes = parseSvgFragment(
      '<g opacity="0.50"><circle cx="1" cy="2" r="3" /><path d="M0 0L1 1Z" /></g>'
    );
    expect(nodes).toHaveLength(1);
    expect(nodes[0].attrs.opacity).toBe('0.50');
    expect(nodes[0].children.map((child) => child.tag)).toEqual(['circle', 'path']);
    expect(nodes[0].children[0].attrs.r).toBe('3');
  });
});
