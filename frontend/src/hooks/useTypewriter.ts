import { useState, useEffect, useRef } from 'react';

export const useTypewriter = (text: string, speed: number = 20, isEnabled: boolean = true) => {
    const [displayedText, setDisplayedText] = useState('');
    const indexRef = useRef(0);
    const textRef = useRef(text);

    // Reset when text completely changes (e.g. new message) but we need to be careful
    // not to reset if it's just the same message getting longer (streaming).
    // We detect "new message" if the new text doesn't start with the old text.
    useEffect(() => {
        if (!text.startsWith(textRef.current) && textRef.current !== '') {
            // ID changed or content totally different - reset
            indexRef.current = 0;
            setDisplayedText('');
        }
        textRef.current = text;
    }, [text]);

    useEffect(() => {
        if (!isEnabled) {
            setDisplayedText(text);
            indexRef.current = text.length;
            return;
        }

        const interval = setInterval(() => {
            if (indexRef.current < text.length) {
                // Calculate how many chars to add to catch up if we are falling too far behind
                // This prevents the typewriter from never finishing if the stream is huge and fast
                const remaining = text.length - indexRef.current;
                const step = remaining > 100 ? 5 : (remaining > 50 ? 2 : 1);

                indexRef.current += step;
                setDisplayedText(text.slice(0, indexRef.current));
            } else {
                clearInterval(interval);
            }
        }, speed);

        return () => clearInterval(interval);
    }, [text, speed, isEnabled]);

    return displayedText;
};
