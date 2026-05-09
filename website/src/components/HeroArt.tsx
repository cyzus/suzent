import React, { useEffect, useRef, useState } from 'react';
import styles from './HeroArt.module.css';

export function HeroArt() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      
      const deltaX = e.clientX - centerX;
      const deltaY = e.clientY - centerY;

      // Mouse tracking intensity
      const maxDistance = 600; 
      let moveX = (deltaX / maxDistance) * 32; // px
      let moveY = (deltaY / maxDistance) * 32;

      // Clamp movement range
      moveX = Math.max(-32, Math.min(32, moveX));
      moveY = Math.max(-32, Math.min(32, moveY));

      setMousePos({ x: moveX, y: moveY });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <div className={styles.root} ref={containerRef}>
      <div 
        className={styles.eyesGroup} 
        style={{ transform: `translate(${mousePos.x}px, ${mousePos.y}px)` }}
      >
        <div className={styles.eyeL} />
        <div className={styles.eyeR} />
      </div>
    </div>
  );
}
