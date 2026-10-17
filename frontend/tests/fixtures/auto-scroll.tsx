// Open /tests/fixtures/auto-scroll.html on the Vite dev server.
// This exercises real React effects and ResizeObserver, including a keyed
// container replacement followed by child-only streaming renders.
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useAutoScroll } from '../../src/hooks/useAutoScroll';

function Stream() {
  const [lines, setLines] = useState(1);
  useEffect(() => {
    const timer = setInterval(() => setLines((n) => Math.min(30, n + 1)), 60);
    return () => clearInterval(timer);
  }, []);
  return (
    <div>
      {Array.from({ length: lines }, (_, i) => (
        <p key={i}>Streaming line {i + 1}</p>
      ))}
    </div>
  );
}
function Probe() {
  const [chat, setChat] = useState(0);
  const hook = useAutoScroll([chat], { resetKey: chat, smooth: false });
  const [result, setResult] = useState('Running');
  useEffect(() => {
    const change = setTimeout(() => setChat(1), 300);
    const check = setTimeout(() => {
      const el = hook.scrollContainerRef.current!;
      const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
      setResult(`${gap <= 1 ? 'PASS' : 'FAIL'}: bottom gap ${gap}px`);
    }, 2600);
    return () => {
      clearTimeout(change);
      clearTimeout(check);
    };
  }, []);
  return (
    <section>
      <h2>Chat container replacement</h2>
      <output>{result}</output>
      <div
        key={chat}
        ref={hook.attachScrollContainer}
        style={{ height: 240, overflowY: 'auto', border: '1px solid', width: 360 }}
      >
        <Stream />
      </div>
    </section>
  );
}
createRoot(document.getElementById('root')!).render(<Probe />);
