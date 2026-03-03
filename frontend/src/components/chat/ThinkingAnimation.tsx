import React, { useState, useEffect, useRef } from 'react';
import { RobotAvatar, RobotVariant } from './RobotAvatar';

interface ThinkingAnimationProps {
  isThinking: boolean;
}

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

const WireframeCube: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const SIZE = 56;
    const ox = SIZE / 2, oy = SIZE / 2;
    const r = 17;       // projected cube half-size
    const fov = 5;      // perspective strength
    const xTilt = -0.38; // ~-22° fixed tilt so top face is visible
    const cosX = Math.cos(xTilt), sinX = Math.sin(xTilt);
    let angle = 0;

    // Unit cube vertices: 0-3 back face, 4-7 front face
    const verts: [number, number, number][] = [
      [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
      [-1,-1, 1],[1,-1, 1],[1,1, 1],[-1,1, 1],
    ];
    const edges: [number, number][] = [
      [0,1],[1,2],[2,3],[3,0],   // back
      [4,5],[5,6],[6,7],[7,4],   // front
      [0,4],[1,5],[2,6],[3,7],   // connecting
    ];

    const project = ([x, y, z]: [number, number, number]): [number, number] => {
      // Y-axis rotation
      const cosY = Math.cos(angle), sinY = Math.sin(angle);
      const x1 = x * cosY + z * sinY;
      const z1 = -x * sinY + z * cosY;
      // X-axis tilt
      const y2 = y * cosX - z1 * sinX;
      const z2 = y * sinX + z1 * cosX;
      // Perspective divide
      const s = fov / (fov - z2);
      return [ox + x1 * r * s, oy + y2 * r * s];
    };

    const draw = () => {
      ctx.clearRect(0, 0, SIZE, SIZE);
      const pts = verts.map(project);

      // Theme-aware stroke color
      const dark = document.documentElement.classList.contains('dark');
      const base = dark ? '255,255,255' : '100,116,139';

      // Cube edges
      ctx.strokeStyle = `rgba(${base},0.65)`;
      ctx.lineWidth = 0.8;
      for (const [a, b] of edges) {
        ctx.beginPath();
        ctx.moveTo(pts[a][0], pts[a][1]);
        ctx.lineTo(pts[b][0], pts[b][1]);
        ctx.stroke();
      }

      // Eyes on front face — visible only when front face faces viewer
      const facing = Math.cos(angle);
      if (facing > 0) {
        ctx.strokeStyle = `rgba(${base},${(facing * 0.95).toFixed(2)})`;
        ctx.lineWidth = 0.85;
        const drawEye = (ex: number, ey: number) => {
          const hw = 0.24, hh = 0.30;
          const corners = ([
            [ex - hw, ey - hh, 1], [ex + hw, ey - hh, 1],
            [ex + hw, ey + hh, 1], [ex - hw, ey + hh, 1],
          ] as [number, number, number][]).map(project);
          ctx.beginPath();
          ctx.moveTo(corners[0][0], corners[0][1]);
          for (let i = 1; i < 4; i++) ctx.lineTo(corners[i][0], corners[i][1]);
          ctx.closePath();
          ctx.stroke();
        };
        drawEye(-0.42, -0.18);
        drawEye( 0.42, -0.18);
      }

      angle += 0.009; // ~11.5s per full rotation
      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  return <canvas ref={canvasRef} width={56} height={56} style={{ display: 'block' }} />;
};

const ThinkingAnimationComponent: React.FC<ThinkingAnimationProps> = ({ isThinking }) => {
  return (
    <div className={`
      absolute inset-0 pointer-events-none
      flex items-center justify-center
      transition-opacity duration-500
      ${isThinking ? 'opacity-100' : 'opacity-0'}
    `}>
      <WireframeCube />
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
  eyeClass?: string;
}

const AgentBadgeComponent: React.FC<AgentBadgeProps> = ({
  isThinking,
  isStreaming
}) => {
  // Determine variant based on state
  const [baseVariant, setBaseVariant] = useState<RobotVariant>(() => selectWeightedVariant(BADGE_WEIGHTS));

  // Effect to handle snoozing
  useEffect(() => {
    if (isStreaming) {
      // If we start streaming, ensure we wake up if we were sleeping
      if (baseVariant === 'snoozer') {
        setBaseVariant('idle');
      }
      return;
    }

    // Only auto-snooze if we are 'idle'
    if (baseVariant === 'idle') {
      const timeout = setTimeout(() => {
        setBaseVariant('snoozer');
      }, 10000); // 10s of idleness = snooze
      return () => clearTimeout(timeout);
    }
  }, [isStreaming, baseVariant]);

  let variant: RobotVariant = baseVariant;

  if (isStreaming) {
    variant = 'observer'; // Active/Working
  }

  return (
    <div className={`
      absolute inset-0 flex items-center justify-center text-white
      transition-opacity duration-500 delay-200
      ${isThinking ? 'opacity-0 pointer-events-none' : 'opacity-100'}
    `}>
      <div className="w-8 h-8">
        <RobotAvatar variant={variant} />
      </div>
    </div>
  );
};

export const AgentBadge = React.memo(AgentBadgeComponent);
AgentBadge.displayName = 'AgentBadge';
