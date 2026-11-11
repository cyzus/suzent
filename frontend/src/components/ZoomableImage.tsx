import React, { useCallback, useEffect, useRef } from 'react';

export interface ImageTransform {
  scale: number;
  x: number;
  y: number;
}

export function zoomImage(
  current: ImageTransform,
  scale: number,
  x: number,
  y: number
): ImageTransform {
  const next = Math.min(8, Math.max(1, scale));
  if (next === 1) return { scale: 1, x: 0, y: 0 };
  const ratio = next / current.scale;
  return { scale: next, x: x - (x - current.x) * ratio, y: y - (y - current.y) * ratio };
}

export function ZoomableImage({
  src,
  alt,
  imageRef,
}: {
  src: string;
  alt: string;
  imageRef: React.RefObject<HTMLImageElement>;
}): React.ReactElement {
  const viewport = useRef<HTMLDivElement>(null);
  const transform = useRef<ImageTransform>({ scale: 1, x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const frameId = useRef<number | null>(null);
  const geometry = useRef({ left: 0, top: 0, width: 0, height: 0, imageWidth: 0, imageHeight: 0 });
  const paint = useCallback((): void => {
    if (frameId.current !== null) return;
    frameId.current = requestAnimationFrame(() => {
      frameId.current = null;
      const { x, y, scale } = transform.current;
      if (imageRef.current) {
        imageRef.current.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${scale})`;
      }
      if (viewport.current) {
        viewport.current.style.cursor =
          scale > 1 ? (pointers.current.size > 0 ? 'grabbing' : 'grab') : 'zoom-in';
      }
    });
  }, [imageRef]);
  const update = useCallback(
    (next: ImageTransform): void => {
      const { width, height, imageWidth, imageHeight } = geometry.current;
      const maxX = Math.max(0, (imageWidth * next.scale - width) / 2);
      const maxY = Math.max(0, (imageHeight * next.scale - height) / 2);
      transform.current = {
        ...next,
        x: Math.max(-maxX, Math.min(maxX, next.x)),
        y: Math.max(-maxY, Math.min(maxY, next.y)),
      };
      paint();
    },
    [paint]
  );
  const measure = useCallback((): void => {
    const rect = viewport.current?.getBoundingClientRect();
    const element = imageRef.current;
    if (!rect || !element) return;
    geometry.current = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      imageWidth: element.offsetWidth,
      imageHeight: element.offsetHeight,
    };
    update(transform.current);
  }, [imageRef, update]);
  const zoom = useCallback(
    (scale: number, clientX: number, clientY: number): void => {
      const rect = geometry.current;
      update(
        zoomImage(
          transform.current,
          scale,
          clientX - rect.left - rect.width / 2,
          clientY - rect.top - rect.height / 2
        )
      );
    },
    [update]
  );
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    transform.current = { scale: 1, x: 0, y: 0 };
    pointers.current.clear();
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (imageRef.current) observer.observe(imageRef.current);
    const wheel = (event: WheelEvent): void => {
      event.preventDefault();
      const delta =
        event.deltaY *
        (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? geometry.current.height : 1);
      zoom(transform.current.scale * Math.exp(-delta * 0.003), event.clientX, event.clientY);
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => {
      element.removeEventListener('wheel', wheel);
      observer.disconnect();
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
      frameId.current = null;
    };
  }, [src, imageRef, measure, zoom]);
  const release = (event: React.PointerEvent<HTMLDivElement>): void => {
    pointers.current.delete(event.pointerId);
    paint();
  };
  return (
    <div
      ref={viewport}
      className="absolute inset-0 flex h-full w-full touch-none items-center justify-center overflow-hidden select-none"
      onDoubleClick={(event) =>
        zoom(transform.current.scale > 1 ? 1 : 2, event.clientX, event.clientY)
      }
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
        paint();
      }}
      onPointerMove={(event) => {
        const previous = pointers.current.get(event.pointerId);
        if (!previous) return;
        const before = [...pointers.current.values()];
        pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
        const after = [...pointers.current.values()];
        if (before.length === 2) {
          const distance = (points: typeof before): number =>
            Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
          const oldDistance = distance(before);
          if (oldDistance > 0)
            zoom(
              (transform.current.scale * distance(after)) / oldDistance,
              (after[0].x + after[1].x) / 2,
              (after[0].y + after[1].y) / 2
            );
        } else if (transform.current.scale > 1) {
          update({
            ...transform.current,
            x: transform.current.x + event.clientX - previous.x,
            y: transform.current.y + event.clientY - previous.y,
          });
        }
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onLostPointerCapture={release}
      style={{ cursor: 'zoom-in' }}
    >
      <img
        ref={imageRef}
        src={src}
        alt={alt}
        draggable={false}
        onLoad={measure}
        className="max-h-[calc(100%-2rem)] max-w-[calc(100%-2rem)] object-contain will-change-transform"
      />
    </div>
  );
}
