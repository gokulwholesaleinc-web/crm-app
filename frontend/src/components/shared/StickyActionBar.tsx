import { ReactNode, RefObject, useEffect, useState } from 'react';

interface StickyActionBarProps {
  children: ReactNode;
  triggerRef?: RefObject<HTMLElement | null>;
}

export function StickyActionBar({ children, triggerRef }: StickyActionBarProps) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const target = triggerRef?.current;
    if (!target) return;
    // Show the sticky bar only after the original action row has scrolled
    // ABOVE the viewport (its bottom edge crosses y=0). Using
    // `boundingClientRect.bottom < 0` makes the trigger explicit; the prior
    // `rootMargin: '0px 0px -100% 0px'` collapsed the root to a 1px line
    // which made `isIntersecting` false on the unscrolled page and the bar
    // appeared duplicated on first paint.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry) setShow(entry.boundingClientRect.bottom < 0);
      },
      { threshold: 0 }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [triggerRef]);

  if (!show) return null;

  // Position:fixed (not sticky) so mount/unmount on scroll toggle adds
  // ZERO layout space inside <main>'s scroll flow. With the prior `sticky
  // top-0`, the bar's natural box sat at the top of main's content and
  // claimed ~50px every time `show` flipped — the browser preserves
  // scrollTop, so the visible content jolted down (and back up when the
  // bar unmounted on upward scroll). Going out-of-flow eliminates the
  // jolt entirely. Offsets clear the 3px brand strip + sticky Header
  // (h-14 mobile → h-16 sm+); --app-sidebar-w is set by Layout so the
  // bar aligns with main's left edge whether the sidebar is collapsed
  // (4rem) or expanded (16rem).
  return (
    <div
      className="fixed top-[calc(3.5rem+3px)] sm:top-[calc(4rem+3px)] left-0 right-0 lg:left-[var(--app-sidebar-w,16rem)] z-30 px-4 sm:px-6 lg:px-8 py-2 bg-white/85 dark:bg-gray-900/85 backdrop-blur border-b border-gray-200 dark:border-gray-700"
      role="toolbar"
      aria-label="Page actions"
    >
      <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap max-w-7xl mx-auto">
        {children}
      </div>
    </div>
  );
}
