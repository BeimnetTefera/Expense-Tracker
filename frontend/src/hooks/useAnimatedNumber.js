import { useEffect, useRef, useState } from "react";

// Glides from the current value to `target` (ease-out, 500 ms) so totals count up/down.
export function useAnimatedNumber(target, duration = 500) {
  const [shown, setShown] = useState(target);
  const current = useRef(target);

  useEffect(() => {
    const from = current.current;
    if (from === target) return;
    const start = performance.now();
    let raf;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      current.current = from + (target - from) * (1 - Math.pow(1 - p, 3));
      setShown(current.current);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return shown;
}
