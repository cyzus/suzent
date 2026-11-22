import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';

const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;
import { applySuzentBotScene } from '../../lib/suzentBot/applySuzentBotScene';
import {
  SuzentBotEngine,
  type SuzentBotEngineConfig,
  type SuzentBotStageId,
  portableMulberry32,
  resolveSuzentStage,
  seedRng,
} from '../../lib/suzentBot';

export interface SuzentBotMarkProps {
  /** Explicit stage override; if omitted, resolved automatically from `isThinking` / `toolName` / `hasPending` / `isError`. */
  stage?: SuzentBotStageId;
  isThinking?: boolean;
  /** Whether the turn is currently streaming or awaiting approval. */
  isStreaming?: boolean;
  /** Whether the physics engine should run (true for the latest turn or active stream). */
  isActive?: boolean;
  hasPending?: boolean;
  isError?: boolean;
  /** Total failed tool calls in this turn; triggers a temporary 2.6s startled reaction only when incremented. */
  errorCount?: number;
  toolName?: string;
  /** Visual diameter in CSS pixels (default 28px inside ActivityRail). */
  size?: number;
  className?: string;
  /** Enable pointer gaze tracking & hover/click spin interactions (default true when active). */
  interactive?: boolean;
}

const ERROR_FLASH_MS = 2600;

function readReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
    document.documentElement.dataset.motion === 'reduced'
  );
}

function readDark(): boolean {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
}

function readBounds(svg: SVGSVGElement | null, fallback: number): SuzentBotEngineConfig['bounds'] {
  if (!svg) return undefined;
  const rect = svg.getBoundingClientRect();
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width || fallback,
    height: rect.height || fallback,
  };
}

export const SuzentBotMark: React.FC<SuzentBotMarkProps> = React.memo(
  ({
    stage: stageProp,
    isThinking = false,
    isStreaming,
    isActive = true,
    hasPending = false,
    isError = false,
    errorCount,
    toolName,
    size = 36,
    className = '',
    interactive = true,
  }) => {
    const rawId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
    const clipId = `suzent-bot-clip-${rawId}`;
    const svgId = `suzent-bot-${rawId}`;
    const svgRef = useRef<SVGSVGElement | null>(null);
    const engineRef = useRef<SuzentBotEngine | null>(null);
    const kickRef = useRef<() => void>(() => undefined);
    const clickCycleRef = useRef(0);

    const streamingFlag = isStreaming ?? isActive;
    const wasStreamingRef = useRef(streamingFlag);
    const [celebratingDone, setCelebratingDone] = useState(false);

    const [errorFlash, setErrorFlash] = useState(false);
    const seenErrorCountRef = useRef(errorCount ?? 0);
    const flashTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

    useEffect(() => {
      if (errorCount === undefined) return;
      const isNewError = errorCount > seenErrorCountRef.current;
      seenErrorCountRef.current = errorCount;
      if (!isNewError) return;
      setErrorFlash(true);
      clearTimeout(flashTimerRef.current);
      flashTimerRef.current = setTimeout(() => setErrorFlash(false), ERROR_FLASH_MS);
    }, [errorCount]);

    useEffect(() => () => clearTimeout(flashTimerRef.current), []);

    const effectiveError =
      errorCount !== undefined ? errorFlash && streamingFlag : Boolean(isError && streamingFlag);

    useEffect(() => {
      if (wasStreamingRef.current && !streamingFlag && !hasPending && !effectiveError) {
        setCelebratingDone(true);
        const timer = setTimeout(() => setCelebratingDone(false), 3800);
        wasStreamingRef.current = streamingFlag;
        return () => clearTimeout(timer);
      }
      if (streamingFlag) {
        setCelebratingDone(false);
      }
      wasStreamingRef.current = streamingFlag;
      return undefined;
    }, [streamingFlag, hasPending, effectiveError]);

    const resolvedStage: SuzentBotStageId =
      stageProp ??
      (celebratingDone && !streamingFlag && !hasPending && !effectiveError
        ? 'done'
        : resolveSuzentStage({
            isThinking,
            hasPending,
            isError: effectiveError,
            toolName: streamingFlag ? toolName : undefined,
            isActive: streamingFlag,
          }));

    const configRef = useRef<SuzentBotEngineConfig>({
      stage: resolvedStage,
      size,
      isPending: hasPending,
      pointer: interactive && isActive,
      particlesEnabled: isActive,
      autoMorphCycle: isActive,
      reducedMotion: false,
      dark: false,
      holdWhenIdle: true,
      svgId,
      clipId,
      pointerClient: null,
    });
    const playingRef = useRef(isActive);
    playingRef.current = isActive;
    configRef.current = {
      ...configRef.current,
      stage: resolvedStage,
      size,
      isPending: hasPending,
      pointer: interactive && isActive,
      particlesEnabled: isActive,
      autoMorphCycle: isActive,
      holdWhenIdle: true,
      svgId,
      clipId,
    };

    useIsoLayoutEffect(() => {
      const svg = svgRef.current;
      if (!svg) return undefined;
      seedRng(portableMulberry32((Math.random() * 0x100000000) >>> 0));
      const engine = new SuzentBotEngine(() => configRef.current);
      engineRef.current = engine;
      let raf = 0;
      let running = false;

      const draw = (now: number): boolean => {
        configRef.current.reducedMotion = readReducedMotion();
        configRef.current.dark = readDark();
        configRef.current.bounds = readBounds(svg, configRef.current.size);
        const frame = engine.step(now);
        applySuzentBotScene(svg, frame);
        return frame.settled || Boolean(configRef.current.reducedMotion) || !playingRef.current;
      };

      const loop = (now: number) => {
        if (draw(now)) {
          running = false;
          return;
        }
        raf = requestAnimationFrame(loop);
      };

      const kick = () => {
        if (running) return;
        if (draw(performance.now())) return;
        running = true;
        raf = requestAnimationFrame(loop);
      };

      kickRef.current = kick;
      kick();
      return () => {
        kickRef.current = () => undefined;
        running = false;
        cancelAnimationFrame(raf);
        engine.destroy();
        engineRef.current = null;
      };
    }, [clipId, svgId]);

    useIsoLayoutEffect(() => {
      kickRef.current();
    }, [resolvedStage, isActive, hasPending, size, interactive]);

    useEffect(() => {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function')
        return undefined;
      const media = window.matchMedia('(prefers-reduced-motion: reduce)');
      const onChange = () => kickRef.current();
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    }, []);

    useEffect(() => {
      if (!interactive || !isActive) return undefined;
      const move = (event: PointerEvent) => {
        configRef.current.bounds = readBounds(svgRef.current, configRef.current.size);
        configRef.current.pointerClient = { x: event.clientX, y: event.clientY };
        kickRef.current();
      };
      const leave = () => {
        configRef.current.pointerClient = null;
      };
      window.addEventListener('pointermove', move, { passive: true });
      document.documentElement.addEventListener('mouseleave', leave);
      return () => {
        window.removeEventListener('pointermove', move);
        document.documentElement.removeEventListener('mouseleave', leave);
        configRef.current.pointerClient = null;
      };
    }, [interactive, isActive]);

    const handleMouseEnter = () => {
      if (!interactive || !isActive) return;
      engineRef.current?.startSpin(1);
      kickRef.current();
    };

    const handleClick = (event: React.MouseEvent<HTMLElement>) => {
      if (!interactive || !isActive || !engineRef.current) return;
      event.stopPropagation();
      engineRef.current.triggerInteractiveTrick(clickCycleRef.current++);
      kickRef.current();
    };

    return (
      <span
        data-suzent-bot=""
        data-stage={resolvedStage}
        onMouseEnter={handleMouseEnter}
        onClick={handleClick}
        style={{ width: size, height: size }}
        className={`relative inline-flex shrink-0 items-center justify-center select-none ${
          interactive && isActive ? 'cursor-pointer' : ''
        } ${className}`}
      >
        <svg
          ref={svgRef}
          id={svgId}
          viewBox="-46 -46 320.54 320.54"
          aria-hidden="true"
          data-pending={hasPending ? 'true' : undefined}
          style={{ overflow: 'visible' }}
          className="suzent-bot-svg h-full w-full overflow-visible"
        />
      </span>
    );
  }
);

SuzentBotMark.displayName = 'SuzentBotMark';
