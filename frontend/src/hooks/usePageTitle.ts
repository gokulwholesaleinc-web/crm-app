import { useEffect } from 'react';

export function usePageTitle(title: string) {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = title ? `${title} - CRM App` : 'CRM App';
    return () => {
      document.title = prevTitle;
    };
  }, [title]);
}
