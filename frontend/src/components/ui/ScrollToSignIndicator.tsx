import { useEffect, useState } from 'react';

interface ScrollToSignIndicatorProps {
  onClick: () => void;
}

// Floating pill shown when the sign/action area is below the fold.
// Fades in on mount unless prefers-reduced-motion is set, in which case
// it appears instantly. Hides itself from print via Tailwind print:hidden.
export function ScrollToSignIndicator({ onClick }: ScrollToSignIndicatorProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
      setVisible(true);
      return;
    }
    // Small rAF delay so the fade-in transition fires after first paint.
    const id = requestAnimationFrame(() => { setVisible(true); });
    return () => { cancelAnimationFrame(id); };
  }, []);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Scroll to sign area"
      className={[
        'fixed bottom-6 right-6 z-50 print:hidden',
        'inline-flex items-center gap-1.5 px-4 py-2 rounded-full',
        'bg-gray-900/80 text-white text-xs font-medium shadow-lg backdrop-blur-sm',
        'hover:bg-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-900',
        'transition-opacity duration-300 motion-reduce:transition-none',
        visible ? 'opacity-100' : 'opacity-0',
      ].join(' ')}
    >
      Scroll to sign
      <span aria-hidden="true">↓</span>
    </button>
  );
}
