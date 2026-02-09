import { useEffect } from 'react';

export function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${title} - CRM App`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
