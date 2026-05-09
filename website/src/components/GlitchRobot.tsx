import React from 'react';
import styles from './GlitchRobot.module.css';

export function GlitchRobot() {
  return (
    <div className={styles.wrapper}>
      <div className={styles.scanlines} aria-hidden />
      <div className={styles.scanBeam} aria-hidden />

      {/* Base: black body + white eyes */}
      <svg className={styles.base} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="3" fill="#111" />
        <rect x="5" y="8" width="5" height="5" rx="0" fill="#fff" />
        <rect x="14" y="8" width="5" height="5" rx="0" fill="#fff" />
      </svg>

      {/* Red channel ghost — eyes only */}
      <svg className={styles.ghostR} viewBox="0 0 24 24" aria-hidden="true">
        <rect x="5" y="8" width="5" height="5" rx="1" fill="#ff2255" />
        <rect x="14" y="8" width="5" height="5" rx="1" fill="#ff2255" />
      </svg>

      {/* Cyan channel ghost — eyes only */}
      <svg className={styles.ghostC} viewBox="0 0 24 24" aria-hidden="true">
        <rect x="5" y="8" width="5" height="5" rx="1" fill="#00ffee" />
        <rect x="14" y="8" width="5" height="5" rx="1" fill="#00ffee" />
      </svg>
    </div>
  );
}
