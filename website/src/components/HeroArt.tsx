import React, { useEffect, useRef } from 'react';
import {
  DOT_CUBE_BASE_ROT_X,
  DOT_CUBE_BASE_ROT_Y,
  DOT_CUBE_FOV,
  DOT_CUBE_R,
  type DotFieldPointer,
} from './DotSphere';
import styles from './HeroArt.module.css';

type HeroArtProps = {
  pointer?: DotFieldPointer;
};

export function HeroArt({ pointer = { x: 0, y: 0, active: false } }: HeroArtProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const leftEyeRef = useRef<HTMLDivElement>(null);
  const rightEyeRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef(pointer);
  const poseRef = useRef({
    phase: 0,
    rotX: DOT_CUBE_BASE_ROT_X,
    rotY: DOT_CUBE_BASE_ROT_Y,
    focus: 0,
  });

  useEffect(() => {
    pointerRef.current = pointer;
  }, [pointer]);

  useEffect(() => {
    let raf: number;

    function projectPoint(point: { x: number; y: number; z: number }, rotX: number, rotY: number) {
      const cy = Math.cos(rotY), sy = Math.sin(rotY);
      const cx = Math.cos(rotX), sx = Math.sin(rotX);
      const x1 = point.x * cy - point.z * sy;
      const z1 = point.x * sy + point.z * cy;
      const y2 = point.y * cx - z1 * sx;
      const z2 = point.y * sx + z1 * cx;
      const scale = DOT_CUBE_FOV / (DOT_CUBE_FOV - z2);

      return {
        x: 240 + x1 * DOT_CUBE_R * scale,
        y: 240 + y2 * DOT_CUBE_R * scale,
        scale,
      };
    }

    function tick() {
      const pose = poseRef.current;
      const cursor = pointerRef.current;
      pose.focus += ((cursor.active ? 1 : 0) - pose.focus) * 0.08;
      pose.phase += 0.008 - pose.focus * 0.0035;

      const idleY = Math.sin(pose.phase) * 0.055 * (1 - pose.focus);
      const idleX = Math.cos(pose.phase * 0.8) * 0.025 * (1 - pose.focus);
      const targetY = DOT_CUBE_BASE_ROT_Y + idleY - cursor.x * 0.46 * pose.focus;
      const targetX = DOT_CUBE_BASE_ROT_X + idleX - cursor.y * 0.18 * pose.focus;
      pose.rotY += (targetY - pose.rotY) * 0.09;
      pose.rotX += (targetX - pose.rotX) * 0.09;

      const logoEyeY = -0.125;
      const logoEyeSize = 5 / 12;
      const logoEyes = [
        { node: leftEyeRef.current, x: -0.44 },
        { node: rightEyeRef.current, x: 0.44 },
      ];
      const rootSize = rootRef.current
        ? Math.min(rootRef.current.clientWidth, rootRef.current.clientHeight)
        : 480;
      const displayScale = rootSize / 480;
      const pointerScreen = {
        x: 240 + cursor.x * 480 * 0.95,
        y: 240 + cursor.y * 480 * 0.95,
      };
      let nearEyes = false;

      for (const eye of logoEyes) {
        if (!eye.node) continue;

        const half = logoEyeSize / 2;
        const topLeft = projectPoint({ x: eye.x - half, y: logoEyeY - half, z: 1 }, pose.rotX, pose.rotY);
        const topRight = projectPoint({ x: eye.x + half, y: logoEyeY - half, z: 1 }, pose.rotX, pose.rotY);
        const bottomLeft = projectPoint({ x: eye.x - half, y: logoEyeY + half, z: 1 }, pose.rotX, pose.rotY);
        const center = projectPoint({ x: eye.x, y: logoEyeY, z: 1 }, pose.rotX, pose.rotY);
        const logicalSize = Math.hypot(topRight.x - topLeft.x, topRight.y - topLeft.y);
        const size = logicalSize * displayScale;
        const radius = size * (1.5 / 5);
        const matrixA = (topRight.x - topLeft.x) / logicalSize;
        const matrixB = (topRight.y - topLeft.y) / logicalSize;
        const matrixC = (bottomLeft.x - topLeft.x) / logicalSize;
        const matrixD = (bottomLeft.y - topLeft.y) / logicalSize;

        eye.node.style.width = `${size}px`;
        eye.node.style.height = `${size}px`;
        eye.node.style.borderRadius = `${radius}px`;
        eye.node.style.transform = `matrix(${matrixA}, ${matrixB}, ${matrixC}, ${matrixD}, ${topLeft.x * displayScale}, ${topLeft.y * displayScale})`;
        eye.node.style.visibility = 'visible';

        const hoverDistance = Math.hypot(pointerScreen.x - center.x, pointerScreen.y - center.y);
        if (cursor.active && hoverDistance < logicalSize * 0.95) {
          nearEyes = true;
        }
      }

      for (const node of [leftEyeRef.current, rightEyeRef.current]) {
        const core = node?.firstElementChild;
        if (!(core instanceof HTMLElement)) continue;

        core.classList.toggle(styles.eyeSquint, nearEyes);
      }

      raf = requestAnimationFrame(tick);
    }

    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className={styles.root} ref={rootRef}>
      <div className={styles.eyesGroup}>
        <div className={styles.eyeL} ref={leftEyeRef}>
          <div className={styles.eyeCore} />
        </div>
        <div className={styles.eyeR} ref={rightEyeRef}>
          <div className={styles.eyeCore} />
        </div>
      </div>
    </div>
  );
}
