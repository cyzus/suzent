import React, { useMemo } from 'react';
import { RobotAvatar } from './RobotAvatar';

interface ThinkingAnimationProps {
  isThinking: boolean;
}

export const ThinkingAnimation: React.FC<ThinkingAnimationProps> = ({ isThinking }) => {
  const variants = ['idle', 'observer', 'jumper', 'peeker'];

  // Randomly select 3 variants only when the component mounts
  // This prevents the robots from changing types during a re-render
  const selectedVariants = useMemo(() => {
    return [0, 1, 2].map(() =>
      variants[Math.floor(Math.random() * variants.length)]
    );
  }, []);

  return (
    <div className={`
      absolute inset-0 pointer-events-none
      transition-opacity duration-500
      ${isThinking ? 'opacity-100' : 'opacity-0'}
    `}>
      <div className="scanner-beam"></div>
      <div className="conveyor-track"></div>

      {selectedVariants.map((variant, i) => (
        <div
          key={i}
          className="conveyor-item"
          style={{ animationDelay: `${i * 0.7}s` }}
        >
          <div className="w-full h-full text-white">
            <RobotAvatar variant={variant as any} />
          </div>
        </div>
      ))}
    </div>
  );
};

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
  eyeClass?: string;
  rightEyeStyle?: React.CSSProperties;
}

export const AgentBadge: React.FC<AgentBadgeProps> = ({
  isThinking,
  isStreaming,
}) => {
  // Determine variant based on state (simple mapping for now)
  // Logic mostly moved to AssistantMessage, but kept here for backward compat/transition
  const variant = isStreaming ? 'observer' : 'idle';

  return (
    <div className={`
      absolute inset-0 flex items-center justify-center gap-1.5 text-brutal-white font-bold text-xs tracking-wider uppercase
      transition-opacity duration-500 delay-200
      ${isThinking ? 'opacity-0 pointer-events-none' : 'opacity-100'}
    `}>
      <div className="w-5 h-5 relative">
        <RobotAvatar variant={variant} />
      </div>
      <span>AGENT</span>
    </div>
  );
};
