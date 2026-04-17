import React, { useMemo, useState, useEffect } from 'react';
import { RobotAvatar, RobotVariant } from './RobotAvatar';

interface ThinkingAnimationProps {
  isThinking: boolean;
}

// Weighted probability configuration for Thinking Animation (Production Line)
const THINKING_WEIGHTS: { variant: RobotVariant; weight: number }[] = [
  { variant: 'idle', weight: 20 }, // High chance
  { variant: 'observer', weight: 20 },
  { variant: 'party', weight: 5 },
  { variant: 'workout', weight: 5 },
  { variant: 'skeptic', weight: 1 },
  { variant: 'eater', weight: 1 },
  { variant: 'scanner', weight: 1 },
];

// Weighted probability configuration for Agent Badge (Personality)
const BADGE_WEIGHTS: { variant: RobotVariant; weight: number }[] = [
  { variant: 'idle', weight: 20 }, // High chance of calm
  { variant: 'observer', weight: 20 },
  { variant: 'peeker', weight: 10 },
  { variant: 'jumper', weight: 5 },
  { variant: 'party', weight: 5 },  // Occasional cool
  { variant: 'love', weight: 2 },  // Rare heartwarming
  { variant: 'dj', weight: 2 },  // Very rare music
];

const selectWeightedVariant = (weights: { variant: RobotVariant; weight: number }[]): RobotVariant => {
  const totalWeight = weights.reduce((sum, item) => sum + item.weight, 0);
  let random = Math.random() * totalWeight;

  for (const item of weights) {
    random -= item.weight;
    if (random <= 0) return item.variant;
  }
  return weights[0].variant; // Fallback
};

const ThinkingAnimationComponent: React.FC<ThinkingAnimationProps> = ({ isThinking }) => {
  // Randomly select 3 variants based on weights on mount
  const variants = useMemo(() => {
    return [0, 1, 2].map(() => selectWeightedVariant(THINKING_WEIGHTS));
  }, []);

  return (
    <div className={`
      absolute inset-0 pointer-events-none overflow-hidden
      transition-opacity duration-500 rounded-lg
      ${isThinking ? 'opacity-100' : 'opacity-0'}
    `}>
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-dot-pattern opacity-10"></div>

      {/* Edge Masking (Soft Fade) */}
      <div className="absolute inset-0 bg-gradient-to-r from-white via-transparent to-white z-20"></div>

      {/* Robots Layer */}
      <div className="absolute inset-0 z-10">
        {variants.map((variant, i) => (
          <div
            key={i}
            className="conveyor-item"
            style={{ animationDelay: `${i * 0.8}s` }}
          >
            <div className="w-full h-full flex items-center justify-center text-brutal-black relative">
              <div className="robot-carrier"></div>
              <div className="w-10 h-10 relative z-10">
                <RobotAvatar variant={variant} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Scanner Layer (Must be top for blend mode) */}
      <div className="scanner-beam z-30 mix-blend-difference"></div>
    </div>
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
  rightEyeStyle
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
      <rect className={eyeClass} style={rightEyeStyle} x="13.5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
    </svg>
  );
};



interface AgentBadgeProps {
  isThinking: boolean;
  isStreaming: boolean;
  currentToolName?: string;
  hasError?: boolean;
  isPendingApproval?: boolean;
  eyeClass?: string;
}

const AgentBadgeComponent: React.FC<AgentBadgeProps> = ({
  isThinking,
  isStreaming,
  currentToolName,
  hasError,
  isPendingApproval,
}) => {
  // Determine variant based on state
  const [baseVariant, setBaseVariant] = useState<RobotVariant>(() => selectWeightedVariant(BADGE_WEIGHTS));

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

  if (hasError) {
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
          variant = 'peeker';  // peeking search
          break;
        case 'bash_execute':
        case 'write_file':
        case 'edit_file':
          variant = 'workout'; // working out (writing/editing code)
          break;
        case 'spawn_subagent':
          variant = 'portal';  // spawning portal
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
    <div className={`
      absolute inset-0 flex items-center justify-center text-white
      transition-opacity duration-500 delay-200
      ${isThinking ? 'opacity-0 pointer-events-none' : 'opacity-100'}
    `}>
      <div 
        key={variant} 
        className="w-8 h-8 shrink-0 relative"
        style={{
          animation: 'robot-drop-in 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)'
        }}
      >
        <RobotAvatar variant={variant} />
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
