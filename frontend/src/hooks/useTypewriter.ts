import { useState, useEffect, useRef } from 'react';

export const useTypewriter = (text: string, speed: number = 20, isEnabled: boolean = true) => {
    const [displayedText, setDisplayedText] = useState('');
    const indexRef = useRef(0);
    const prevTextRef = useRef(text);

    // Reset when content is replaced (new message), but keep progress when content only appends.
    useEffect(() => {
        if (!text.startsWith(prevTextRef.current) && prevTextRef.current !== '') {
            indexRef.current = 0;
            setDisplayedText('');
        }
        prevTextRef.current = text;
    }, [text]);

    useEffect(() => {
        if (!isEnabled) {
            setDisplayedText(text);
            indexRef.current = text.length;
            return;
        }

        // For very large responses, avoid animation overhead entirely.
        if (text.length > 5000) {
            setDisplayedText(text);
            indexRef.current = text.length;
            return;
        }

        let frameId = 0;
        let cancelled = false;
        let lastTick = 0;

        const getStep = (remaining: number): number => {
            if (remaining > 800) return 10;
            if (remaining > 300) return 6;
            if (remaining > 120) return 4;
            if (remaining > 40) return 2;
            return 1;
        };

        const tick = (now: number) => {
            if (cancelled) return;

            // Use a soft cadence to avoid over-rendering while keeping movement smooth.
            const cadence = Math.max(speed, 16);
            if (now - lastTick >= cadence) {
                if (indexRef.current < text.length) {
                    const remaining = text.length - indexRef.current;
                    const step = getStep(remaining);
                    indexRef.current = Math.min(text.length, indexRef.current + step);
                    setDisplayedText(text.slice(0, indexRef.current));
                }
                lastTick = now;
            }

            if (indexRef.current < text.length) {
                frameId = window.requestAnimationFrame(tick);
            }
        };

        frameId = window.requestAnimationFrame(tick);
        return () => {
            cancelled = true;
            window.cancelAnimationFrame(frameId);
        };
    }, [text, speed, isEnabled]);

    return displayedText;
};
