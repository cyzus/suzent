import React, { useEffect, useRef } from 'react';
import { mountVoiceCube, type VoiceCubeState } from '../../lib/voice/voiceCubeRenderer';

export const VoiceCubeStage: React.FC<VoiceCubeState> = (props) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(props);
  stateRef.current = props;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      return mountVoiceCube(canvas, () => ({
        ...stateRef.current,
        reducedMotion:
          stateRef.current.reducedMotion ??
          (document.documentElement.dataset.motion === 'reduced' ? true : undefined),
      }));
    }
  }, []);

  return (
    <div className="flex justify-center py-1">
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        data-testid="voice-cube-stage"
        className="block h-28 w-full max-w-[260px]"
      />
    </div>
  );
};
