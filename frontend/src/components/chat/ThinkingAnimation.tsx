import React, { useRef, useState, useEffect } from 'react';
import { RobotAvatar, RobotVariant } from './RobotAvatar';
import { assemblyFrame } from './assemblyScene';

interface ThinkingAnimationProps {
  isThinking: boolean;
}

// Weighted probability configuration for Agent Badge (Personality)
const BADGE_WEIGHTS: { variant: RobotVariant; weight: number }[] = [
  { variant: 'idle', weight: 20 }, // High chance of calm
  { variant: 'observer', weight: 20 },
  { variant: 'peeker', weight: 10 },
  { variant: 'jumper', weight: 5 },
  { variant: 'party', weight: 5 }, // Occasional cool
  { variant: 'love', weight: 2 }, // Rare heartwarming
  { variant: 'dj', weight: 2 }, // Very rare music
];

// How long the robot stays startled after a tool call fails.
const ERROR_FLASH_MS = 2600;

const selectWeightedVariant = (
  weights: { variant: RobotVariant; weight: number }[]
): RobotVariant => {
  const totalWeight = weights.reduce((sum, item) => sum + item.weight, 0);
  let random = Math.random() * totalWeight;

  for (const item of weights) {
    random -= item.weight;
    if (random <= 0) return item.variant;
  }
  return weights[0].variant; // Fallback
};

const ThinkingAnimationComponent: React.FC<ThinkingAnimationProps> = ({ isThinking }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!isThinking) return;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0,
      seconds = 0;
    let previous: number | undefined;
    const draw = (): void => {
      const { width, height } = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      const w = Math.round(width * ratio),
        h = Math.round(height * ratio);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, w, h);
      const scale = Math.min(w / 320, h / 108);
      context.setTransform(scale, 0, 0, scale, (w - 320 * scale) / 2, (h - 108 * scale) / 2);
      for (const mark of assemblyFrame(seconds, motion.matches)) {
        context.beginPath();
        mark.points.forEach(([x, y], i) => {
          if (i === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        if (mark.points.length > 2) context.closePath();
        context.globalAlpha = mark.alpha;
        if (mark.stroke) {
          context.strokeStyle = mark.color;
          context.lineWidth = mark.width ?? 0.65;
          context.stroke();
        } else {
          context.fillStyle = mark.color;
          context.fill();
        }
      }
      context.globalAlpha = 1;
    };
    const tick = (now: number): void => {
      if (previous !== undefined) seconds += Math.min((now - previous) / 1000, 0.05);
      previous = now;
      draw();
      frame = requestAnimationFrame(tick);
    };
    const sync = (): void => {
      cancelAnimationFrame(frame);
      previous = undefined;
      draw();
      if (!document.hidden) frame = requestAnimationFrame(tick);
    };
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    motion.addEventListener('change', sync);
    document.addEventListener('visibilitychange', sync);
    sync();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      motion.removeEventListener('change', sync);
      document.removeEventListener('visibilitychange', sync);
    };
  }, [isThinking]);
  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`absolute inset-0 h-full w-full pointer-events-none transition-opacity duration-500 motion-reduce:transition-none ${isThinking ? 'opacity-100' : 'opacity-0'}`}
    />
  );
};

export const ThinkingAnimation = React.memo(ThinkingAnimationComponent);
ThinkingAnimation.displayName = 'ThinkingAnimation';

interface RobotIconProps {
  className?: string;
  isStreaming?: boolean;
  eyeClass?: string;
  rightEyeStyle?: React.CSSProperties;
}

export const RobotIcon: React.FC<RobotIconProps> = ({
  className = '',
  isStreaming = false,
  eyeClass = 'robot-eye robot-eye-idle',
  rightEyeStyle,
}) => {
  return (
    <svg
      className={`w-4 h-4 shrink-0 ${isStreaming ? 'robot-streaming' : ''} ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <rect x="2" y="2" width="20" height="20" rx="3" fill="currentColor" />
      <rect x="4" y="4" width="16" height="16" rx="3" fill="#000000" />
      <rect className={eyeClass} x="5.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
      <rect
        className={eyeClass}
        style={rightEyeStyle}
        x="13.5"
        y="7"
        width="5"
        height="5"
        rx="1.5"
        fill="currentColor"
      />
    </svg>
  );
};

interface AgentBadgeProps {
  isThinking: boolean;
  isStreaming: boolean;
  currentToolName?: string;
  /**
   * How many tool calls in this turn have failed. A count rather than a flag:
   * the robot reacts to a *new* failure and then settles, so a turn that
   * errored once must not freeze the badge on the startled face forever.
   */
  errorCount?: number;
  isPendingApproval?: boolean;
  eyeClass?: string;
  /**
   * Replaces the robot avatar with a caller-supplied mark, keeping the same
   * slot, drop-in animation, and thinking fade. Used for ACP turns, where the
   * work was done by an external agent and the Suzent robot would misattribute
   * it. Variant state is ignored in that case.
   */
  icon?: React.ReactNode;
}

const AgentBadgeComponent: React.FC<AgentBadgeProps> = ({
  isThinking,
  isStreaming,
  currentToolName,
  errorCount = 0,
  isPendingApproval,
  icon,
}) => {
  // Determine variant based on state
  const [baseVariant, setBaseVariant] = useState<RobotVariant>(() =>
    selectWeightedVariant(BADGE_WEIGHTS)
  );

  // The startled reaction is a beat, not a mode: it fires when the error count
  // goes up and clears itself, so the badge returns to whatever the agent is
  // doing now instead of staying frozen on the last failure.
  const [errorFlash, setErrorFlash] = useState(false);
  const seenErrorCountRef = React.useRef(errorCount);
  const flashTimerRef = React.useRef<ReturnType<typeof setTimeout>>();

  // The timer lives outside the effect's cleanup: a count that drops (parts
  // reconciled after a resume) re-runs the effect, and cancelling the timer
  // there left the badge shaking for good.
  useEffect(() => {
    const isNewError = errorCount > seenErrorCountRef.current;
    seenErrorCountRef.current = errorCount;
    if (!isNewError) return;
    setErrorFlash(true);
    clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => setErrorFlash(false), ERROR_FLASH_MS);
  }, [errorCount]);

  useEffect(() => () => clearTimeout(flashTimerRef.current), []);

  // Effect to handle snoozing
  useEffect(() => {
    if (isStreaming || isPendingApproval) {
      // If we start streaming or waiting for approval, ensure we wake up if we were sleeping
      if (baseVariant === 'snoozer') {
        setBaseVariant('idle');
      }
      return;
    }

    // Only auto-snooze if we are 'idle' (and NOT waiting for approval)
    if (baseVariant === 'idle' && !isPendingApproval) {
      const timeout = setTimeout(() => {
        setBaseVariant('snoozer');
      }, 10000); // 10s of idleness = snooze
      return () => clearTimeout(timeout);
    }
  }, [isStreaming, isPendingApproval, baseVariant]);

  let variant: RobotVariant = baseVariant;

  if (errorFlash) {
    variant = 'shaker'; // shaking when there's an error
  } else if (isPendingApproval) {
    variant = 'skeptic'; // skeptical when waiting for user approval
  } else if (isStreaming || currentToolName) {
    if (currentToolName) {
      switch (currentToolName) {
        case 'read_file':
        case 'webpage_fetch':
          variant = 'eater'; // eating data
          break;
        case 'glob_search':
        case 'grep_search':
          variant = 'scanner'; // scanning data
          break;
        case 'web_search':
          variant = 'peeker'; // peeking search
          break;
        case 'run_command':
        case 'start_command':
        case 'write_file':
        case 'edit_file':
          variant = 'workout'; // working out (writing/editing code)
          break;
        case 'agent':
          variant = 'portal'; // spawning portal
          break;
        case 'skill_execute':
          variant = 'dj';
          break;
        default:
          variant = 'observer';
      }
    } else {
      variant = 'observer'; // pure text streaming output
    }
  }

  return (
    <div
      className={`
      absolute inset-0 flex items-center justify-center text-white
      transition-opacity duration-500 delay-200
      ${isThinking ? 'opacity-0 pointer-events-none' : 'opacity-100'}
    `}
    >
      <div
        key={icon ? 'icon' : variant}
        className="w-8 h-8 shrink-0 relative flex items-center justify-center text-brutal-black dark:text-white"
        style={{
          animation: 'robot-drop-in 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        }}
      >
        {icon ?? <RobotAvatar variant={variant} />}
      </div>
      <style>{`
        @keyframes robot-drop-in {
          0% { transform: translateY(15px) scale(0.5); opacity: 0; }
          50% { transform: translateY(-3px) scale(1.05); opacity: 1; }
          100% { transform: translateY(0) scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
};

export const AgentBadge = React.memo(AgentBadgeComponent);
AgentBadge.displayName = 'AgentBadge';
