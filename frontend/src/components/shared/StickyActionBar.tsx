import { ReactNode, RefObject, useEffect, useState } from 'react';

// Single source of truth for the CSS variable name. Layout sets it from
// `sidebarCollapsed`; this file consumes it via the className below. A
// typo in either spot would silently fall back to 16rem and misalign on
// a collapsed sidebar — the `const` shared by writer + reader prevents
// that drift.
export const APP_SIDEBAR_W_VAR = '--app-sidebar-w';

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

  // fixed (not sticky): mount/unmount on scroll added ~50px to main's
  // flow and jolted scrollTop. Offsets clear 3px brand strip + Header
  // (h-14/h-16); --app-sidebar-w from Layout aligns the left edge.
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
