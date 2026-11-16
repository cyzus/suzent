/**
 * String-in, string-out host for JavaScriptCore (iOS) and Rhino (Android).
 * Desktop imports the TypeScript modules directly and does not use this entry.
 */
import {
  resolveSuzentStage,
  type SuzentBotStageId,
  type SuzentMorphId,
} from "./suzentBotActs";
import { SuzentBotEngine, type SuzentBotEngineConfig } from "./suzentBotEngine";
import { useRng } from "./suzentBotPhysics";
import { portableMulberry32 } from "./suzentBotScene";

export interface HostInput {
  stage?: SuzentBotStageId;
  isThinking?: boolean;
  hasPending?: boolean;
  isError?: boolean;
  isPending?: boolean;
  toolName?: string;
  isActive?: boolean;
  time: number;
  reducedMotion?: boolean;
  dark?: boolean;
  size?: number;
  gazeX?: number | null;
  gazeY?: number | null;
  particlesEnabled?: boolean;
  autoMorphCycle?: boolean;
  holdWhenIdle?: boolean;
  svgId?: string;
  clipId?: string;
  /** Fires once, before this step, matching the desktop morph preview. */
  morph?: string;
  morphDuration?: number;
}

interface Session {
  engine: SuzentBotEngine;
  input: HostInput;
}

const sessions = new Map<number, Session>();
let nextId = 1;

function stageOf(input: HostInput): SuzentBotStageId {
  if (input.stage) return input.stage;
  return resolveSuzentStage({
    isThinking: input.isThinking,
    hasPending: input.hasPending,
    isError: input.isError,
    toolName: input.toolName,
    isActive: input.isActive,
  });
}

function toConfig(input: HostInput): SuzentBotEngineConfig {
  const gaze =
    input.gazeX != null && input.gazeY != null
      ? { x: input.gazeX, y: input.gazeY }
      : null;
  return {
    stage: stageOf(input),
    size: input.size ?? 32,
    isPending: input.isPending ?? Boolean(input.hasPending),
    pointer: gaze !== null,
    pointerClient: gaze,
    particlesEnabled: input.particlesEnabled ?? input.isActive !== false,
    autoMorphCycle:
      input.autoMorphCycle ??
      (input.isActive !== false && !input.reducedMotion),
    reducedMotion: Boolean(input.reducedMotion),
    dark: Boolean(input.dark),
    holdWhenIdle: input.holdWhenIdle ?? true,
    svgId: input.svgId ?? "suzent-bot",
    clipId: input.clipId ?? "suzent-bot-clip",
  };
}

export function resolveStage(json: string): string {
  return resolveSuzentStage(JSON.parse(json) as HostInput);
}

export function create(seed: number, json = "{}"): number {
  const id = nextId;
  nextId += 1;
  const input = Object.assign(
    {
      stage: "idle" as const,
      time: 0,
      reducedMotion: false,
      dark: false,
      size: 32,
    },
    JSON.parse(json) as HostInput,
  );
  useRng(portableMulberry32(seed >>> 0 || 1));
  const engine = new SuzentBotEngine(() => toConfig(input));
  sessions.set(id, { engine, input });
  return id;
}

export function step(id: number, json: string): string {
  const session = sessions.get(id);
  if (!session) return JSON.stringify({ error: "missing" });
  Object.assign(session.input, JSON.parse(json) as HostInput);
  const morph = session.input.morph;
  if (morph && morph !== "none") {
    session.engine.triggerMorphPreview(
      morph as Exclude<SuzentMorphId, "none">,
      session.input.morphDuration ?? 1750,
    );
    session.input.morph = undefined;
  }
  return JSON.stringify(session.engine.step(session.input.time));
}

export function destroy(id: number): void {
  const session = sessions.get(id);
  session?.engine.destroy();
  sessions.delete(id);
}

const suzentBotApi = { resolveStage, create, step, destroy };

/** Rhino and JavaScriptCore read a plain object. esbuild's export getters are not reliable there. */
function publishSuzentBot(): void {
  const target = globalThis as unknown as { SuzentBot?: typeof suzentBotApi };
  target.SuzentBot = suzentBotApi;
}

publishSuzentBot();
