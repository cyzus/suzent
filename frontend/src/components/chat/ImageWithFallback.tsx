import React, { useState } from 'react';

interface ImageWithFallbackProps {
  src: string;
  imgClassName?: string;
  fallbackClassName?: string;
  /** Rendered in place of the image once it fails to load. */
  fallback: React.ReactNode;
  loading?: 'lazy' | 'eager';
}

/**
 * An image that degrades to a fallback glyph **without swapping DOM nodes**.
 *
 * The obvious spelling — `failed ? <span/> : <img/>` — unmounts one element and
 * mounts another seconds after paint, when a remote favicon finally times out.
 * Chrome renormalizes any live selection whose range spans that mutation, so a
 * user who selected a paragraph watches the selection silently swallow the
 * blocks above it. Keeping both nodes mounted and toggling `display` makes the
 * fallback an attribute change, which selections are immune to.
 *
 * `display` is set inline rather than via a utility class because Tailwind's
 * `hidden` and `inline-flex` have equal specificity — stylesheet order would
 * decide the winner.
 */
export const ImageWithFallback: React.FC<ImageWithFallbackProps> = ({
  src,
  imgClassName,
  fallbackClassName,
  fallback,
  loading = 'lazy',
}) => {
  const [failed, setFailed] = useState(false);

  return (
    <>
      <img
        src={src}
        alt=""
        className={imgClassName}
        style={failed ? { display: 'none' } : undefined}
        onError={() => setFailed(true)}
        loading={loading}
      />
      <span
        className={fallbackClassName}
        style={failed ? undefined : { display: 'none' }}
        aria-hidden="true"
      >
        {fallback}
      </span>
    </>
  );
};
