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
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry) setShow(!entry.isIntersecting);
      },
      { threshold: 0, rootMargin: '0px 0px -100% 0px' }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [triggerRef]);

  if (!show) return null;

  return (
    <div
      className="sticky top-0 z-30 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-2 bg-white/85 dark:bg-gray-900/85 backdrop-blur border-b border-gray-200 dark:border-gray-700"
      role="toolbar"
      aria-label="Page actions"
    >
      <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap max-w-7xl mx-auto">
        {children}
      </div>
    </div>
  );
}
