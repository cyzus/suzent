import React, { useEffect, useId, useRef, useState } from 'react';
import {
  HEAD_C,
  SUZENT_BODY_PATH,
  SUZENT_EXPRESSIONS,
  SuzentBotEngine,
  SuzentBotStageId,
  resolveSuzentStage,
  ringPath,
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
const INITIAL_LEFT_EYE_PATH = ringPath(SUZENT_EXPRESSIONS[0][0]);
const INITIAL_RIGHT_EYE_PATH = ringPath(SUZENT_EXPRESSIONS[0][1]);

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
    size = 28,
    className = '',
    interactive = true,
  }) => {
    const rawId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
    const clipId = `suzent-bot-clip-${rawId}`;
    const svgId = `suzent-bot-${rawId}`;
    const svgRef = useRef<SVGSVGElement | null>(null);
    const engineRef = useRef<SuzentBotEngine | null>(null);
    const clickCycleRef = useRef(0);

    const streamingFlag = isStreaming ?? isActive;
    const wasStreamingRef = useRef(streamingFlag);
    const [celebratingDone, setCelebratingDone] = useState(false);

    // Transient startled reaction when errorCount increments (matching AgentBadge's ERROR_FLASH_MS):
    // a past tool failure that the agent already recovered from must not freeze the robot in `!` forever.
    const [errorFlash, setErrorFlash] = useState(false);
    const seenErrorCountRef = useRef(errorCount ?? 0);
    const flashTimerRef = useRef<ReturnType<typeof setTimeout>>();

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

    const configRef = useRef({
      stage: resolvedStage,
      size,
      isPending: hasPending,
      pointer: interactive && isActive,
      particlesEnabled: isActive,
      autoMorphCycle: isActive,
    });
    configRef.current = {
      stage: resolvedStage,
      size,
      isPending: hasPending,
      pointer: interactive && isActive,
      particlesEnabled: isActive,
      autoMorphCycle: isActive,
    };

    useEffect(() => {
      const svg = svgRef.current;
      if (!svg || !isActive) return undefined;
      const engine = new SuzentBotEngine(svg, () => configRef.current);
      engineRef.current = engine;
      return () => {
        engine.destroy();
        engineRef.current = null;
      };
    }, [isActive]);

    useEffect(() => {
      engineRef.current?.setStage(resolvedStage, false);
    }, [resolvedStage]);

    const handleMouseEnter = () => {
      if (!interactive || !isActive) return;
      engineRef.current?.startSpin(1);
    };

    const handleClick = (e: React.MouseEvent<HTMLElement>) => {
      if (!interactive || !isActive || !engineRef.current) return;
      e.stopPropagation();
      engineRef.current.triggerInteractiveTrick(clickCycleRef.current++);
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
        >
          <defs>
            <clipPath id={clipId}>
              <path id="head-clip-path" d={SUZENT_BODY_PATH} />
            </clipPath>
          </defs>
          <g id="particles-back" />
          <g className="suzent-act-back" />
          <path
            className="grok-bot-mark__head morph-head"
            d={SUZENT_BODY_PATH}
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <path
            className="grok-bot-mark__head morph-head"
            d={SUZENT_BODY_PATH}
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <circle
            className="morph-ring"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            style={{ display: 'none' }}
          />
          <circle
            className="morph-ring"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            style={{ display: 'none' }}
          />
          <circle
            className="morph-ring"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            style={{ display: 'none' }}
          />
          <circle
            className="morph-ring"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            style={{ display: 'none' }}
          />
          <circle
            className="morph-ring"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            style={{ display: 'none' }}
          />
          <circle
            className="grok-bot-mark__head morph-part"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <circle
            className="grok-bot-mark__head morph-part"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <circle
            className="grok-bot-mark__head morph-part"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <circle
            className="grok-bot-mark__head morph-part"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <circle
            className="grok-bot-mark__head morph-part"
            cx={HEAD_C}
            cy={HEAD_C}
            r="0"
            fill="var(--fg)"
            style={{ display: 'none' }}
          />
          <path className="morph-glyph" style={{ display: 'none' }} />
          <path className="morph-glyph" style={{ display: 'none' }} />
          <path className="morph-glyph" style={{ display: 'none' }} />
          <g id="bot-transform">
            <path
              id="head-path"
              className="grok-bot-mark__head"
              d={SUZENT_BODY_PATH}
              fill="var(--fg)"
            />
            <g clipPath={`url(#${clipId})`}>
              <g id="eyes-group">
                <path
                  className="grok-bot-mark__eye eye-path"
                  d={INITIAL_LEFT_EYE_PATH}
                  fill="var(--bg)"
                />
                <path
                  className="grok-bot-mark__eye eye-path"
                  d={INITIAL_RIGHT_EYE_PATH}
                  fill="var(--bg)"
                />
              </g>
            </g>
            <circle id="notify-badge" cx="198" cy="40" r="0" style={{ display: 'none' }} />
          </g>
          <g className="suzent-act-front" />
          <g id="particles-front" />
        </svg>
      </span>
    );
  }
);

SuzentBotMark.displayName = 'SuzentBotMark';
