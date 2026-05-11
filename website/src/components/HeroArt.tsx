import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import {
  DOT_CUBE_BASE_ROT_X,
  DOT_CUBE_BASE_ROT_Y,
  DOT_CUBE_FOV,
  type DotFieldPointer,
} from './DotSphere';
import styles from './HeroArt.module.css';

type HeroArtProps = { pointer?: DotFieldPointer };

const EYE_DEFS = [
  { x: -0.44, y: 0.10 },
  { x:  0.44, y: 0.10 },
];
const EYE_HALF = 5 / 12 / 2;
const LOGICAL  = 480; // matches DotSphere canvas logical size

export function HeroArt({ pointer = { x: 0, y: 0, active: false } }: HeroArtProps) {
  const rootRef     = useRef<HTMLDivElement>(null);
  const leftEyeRef  = useRef<HTMLDivElement>(null);
  const rightEyeRef = useRef<HTMLDivElement>(null);
  const pointerRef  = useRef(pointer);
  const poseRef     = useRef({ phase: 0, rotX: DOT_CUBE_BASE_ROT_X, rotY: DOT_CUBE_BASE_ROT_Y, focus: 0, entry: 0, blinkTimer: 0 });

  useEffect(() => { pointerRef.current = pointer; }, [pointer]);

  useEffect(() => {
    // Mirrors DotSphere camera exactly — must match FOV in DotSphere.tsx
    const camera = new THREE.PerspectiveCamera(90, 1, 0.1, 50);
    camera.position.z = DOT_CUBE_FOV;
    camera.updateMatrixWorld();

    const group  = new THREE.Group();
    const tmpVec = new THREE.Vector3();

    // Project a model-space point → logical 480×480 pixel coords
    function project(x: number, y: number, z: number) {
      tmpVec.set(x, y, z);
      tmpVec.applyEuler(group.rotation);
      tmpVec.project(camera);
      return {
        px: (tmpVec.x  + 1) / 2 * LOGICAL,
        py: (1 - tmpVec.y) / 2 * LOGICAL,
      };
    }

    let raf: number;

    function tick() {
      const pose   = poseRef.current;
      const cursor = pointerRef.current;

      pose.entry += (1 - pose.entry) * 0.012; // Synchronized entry easing
      pose.focus += ((cursor.active ? 1 : 0) - pose.focus) * 0.08;
      pose.phase += 0.008 - pose.focus * 0.0035;

      const idleMix = 1 - pose.focus * 0.68;
      const idleY = Math.sin(pose.phase) * 0.12 * idleMix;
      const idleX = Math.cos(pose.phase * 0.8) * 0.06 * idleMix;
      // Matches DotSphere tick exactly
      const tY = DOT_CUBE_BASE_ROT_Y + idleY - cursor.x * 0.46 * pose.focus;
      const tX = DOT_CUBE_BASE_ROT_X + idleX + cursor.y * 0.42 * pose.focus;
      pose.rotY += (tY - pose.rotY) * 0.09;
      pose.rotX += (tX - pose.rotX) * 0.09;

      group.rotation.set(pose.rotX, -pose.rotY, 0, 'YXZ');

      // displayScale: how many CSS pixels per logical pixel
      const rootSize    = rootRef.current ? Math.min(rootRef.current.clientWidth, rootRef.current.clientHeight) : LOGICAL;
      const displayScale = rootSize / LOGICAL;

      const ptrLogical = {
        x: (cursor.x  + 1) / 2 * LOGICAL,
        y: (1 - cursor.y) / 2 * LOGICAL,
      };
      let nearEyes = false;

      const eyeRefs = [leftEyeRef.current, rightEyeRef.current];
      for (let ei = 0; ei < EYE_DEFS.length; ei++) {
        const node = eyeRefs[ei];
        if (!node) continue;
        const { x: ex, y: ey } = EYE_DEFS[ei];

        const tl = project(ex - EYE_HALF, ey - EYE_HALF, 1);
        const tr = project(ex + EYE_HALF, ey - EYE_HALF, 1);
        const bl = project(ex - EYE_HALF, ey + EYE_HALF, 1);
        const ct = project(ex, ey, 1);

        const logicalSize = Math.hypot(tr.px - tl.px, tr.py - tl.py);
        const size   = logicalSize * displayScale;
        const radius = size * (1.5 / 5);

        // matrix maps unit square → projected quad, in logical-pixel space
        const mA = (tr.px - tl.px) / logicalSize;
        const mB = (tr.py - tl.py) / logicalSize;
        const mC = (bl.px - tl.px) / logicalSize;
        const mD = (bl.py - tl.py) / logicalSize;
        // translate in CSS pixels
        const tx = tl.px * displayScale;
        const ty = tl.py * displayScale;
        
        // Entry transition: wait for the cube to mostly assemble, then pop the eyes out very quickly
        // pose.entry asymptotically approaches 1. At 0.8 the cube is visually settled.
        const eyeEntry = Math.max(0, Math.min(1.0, (pose.entry - 0.8) * 30.0));
        const entryScaleY = Math.min(1.0, Math.max(0.01, eyeEntry));
        const entryScaleX = Math.min(1.0, Math.max(0.01, (eyeEntry - 0.1) * 1.25));
        
        const mA_Entry = mA * entryScaleX;
        const mB_Entry = mB * entryScaleX;
        const mC_Entry = mC * entryScaleY;
        const mD_Entry = mD * entryScaleY;

        // Adjust translation to scale from the exact quad center instead of top-left
        const tx_Entry = tx + (mA + mC - mA_Entry - mC_Entry) * (size / 2);
        const ty_Entry = ty + (mB + mD - mB_Entry - mD_Entry) * (size / 2);

        node.style.width        = `${size}px`;
        node.style.height       = `${size}px`;
        node.style.borderRadius = `${radius}px`;
        node.style.transform    = `matrix(${mA_Entry},${mB_Entry},${mC_Entry},${mD_Entry},${tx_Entry},${ty_Entry})`;
        node.style.visibility   = 'visible';
        node.style.opacity      = `${Math.max(0, Math.min(1.0, (eyeEntry - 0.1) * 1.5))}`;

        if (cursor.active && Math.hypot(ptrLogical.x - ct.px, ptrLogical.y - ct.py) < logicalSize * 0.95)
          nearEyes = true;
      }

      // Random blink and gaze interaction
      if (pose.blinkTimer <= 0) {
        if (Math.random() < 0.005) pose.blinkTimer = 16;
      } else {
        pose.blinkTimer--;
      }
      
      let blinkScale = 1.0;
      if (pose.blinkTimer > 0) {
        const t = pose.blinkTimer / 16.0;
        // drops to 0 at middle (t=0.5), then comes back up
        blinkScale = Math.max(0.05, Math.pow(Math.abs(t - 0.5) * 2.0, 1.5));
      }

      // Track mouse if active, otherwise drift around slightly and naturally
      const gazeX = cursor.active ? cursor.x * 6.0 : Math.sin(pose.phase * 0.8) * 1.5;
      const gazeY = cursor.active ? -cursor.y * 6.0 : Math.cos(pose.phase * 1.2) * 1.5;

      for (const node of [leftEyeRef.current, rightEyeRef.current]) {
        const core = node?.firstElementChild;
        if (core instanceof HTMLElement) {
          core.classList.toggle(styles.eyeSquint, nearEyes);
          // Apply pupil tracking and blink scale via transform on the eyeCore
          core.style.transform = `translate(${gazeX}px, ${gazeY}px) scaleY(${blinkScale})`;
        }
      }

      raf = requestAnimationFrame(tick);
    }

    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className={styles.root} ref={rootRef}>
      <div className={styles.eyesGroup}>
        <div className={styles.eyeL} ref={leftEyeRef}><div className={styles.eyeCore} /></div>
        <div className={styles.eyeR} ref={rightEyeRef}><div className={styles.eyeCore} /></div>
      </div>
    </div>
  );
}
