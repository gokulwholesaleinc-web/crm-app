import { useEffect, useMemo, useState } from 'react';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import { SECTIONS } from './helpContent';

function HelpPage() {
  const [query, setQuery] = useState('');
  const [activeId, setActiveId] = useState<string>('getting-started');

  const filteredSections = useMemo(() => {
    if (!query.trim()) return SECTIONS;
    const q = query.toLowerCase();
    return SECTIONS.filter(
      s => s.title.toLowerCase().includes(q) || s.searchText.toLowerCase().includes(q)
    );
  }, [query]);

  // Honor URL hashes like #tutorial-send-invoice so shared deep links land
  // on the right walkthrough. The browser's native hash-scroll fires before
  // React mounts the article elements, so we re-scroll on mount and on
  // hashchange.
  useEffect(() => {
    const scrollToHash = () => {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      const el = document.getElementById(hash);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    };
    scrollToHash();
    window.addEventListener('hashchange', scrollToHash);
    return () => window.removeEventListener('hashchange', scrollToHash);
  }, []);

  const handleSelect = (id: string) => {
    setActiveId(id);
    const el = document.getElementById(`help-section-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Help &amp; User Guide</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          A walkthrough of every tab and how the pieces fit together.
        </p>
      </div>

      {/* Search */}
      <Card padding="sm">
        <Input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search the guide..."
          aria-label="Search the help guide"
          leftIcon={<MagnifyingGlassIcon />}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Table of contents */}
        <aside className="lg:col-span-1 lg:sticky lg:top-4 lg:self-start">
          <Card padding="sm">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2 px-2">
              Contents
            </h2>
            <nav aria-label="Help guide contents">
              <ul className="space-y-0.5">
                {filteredSections.map(section => {
                  const Icon = section.icon;
                  const isActive = section.id === activeId;
                  return (
                    <li key={section.id}>
                      <button
                        type="button"
                        onClick={() => handleSelect(section.id)}
                        className={`group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                          isActive
                            ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300'
                            : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                        }`}
                      >
                        <Icon
                          className={`h-4 w-4 flex-shrink-0 ${
                            isActive ? 'text-primary-500' : 'text-gray-400'
                          }`}
                          aria-hidden="true"
                        />
                        <span className="flex-1 truncate">{section.title}</span>
                      </button>
                    </li>
                  );
                })}
                {filteredSections.length === 0 && (
                  <li className="px-2 py-2 text-xs text-gray-500 dark:text-gray-400">
                    No matches.
                  </li>
                )}
              </ul>
            </nav>
          </Card>
        </aside>

        {/* Main content */}
        <main className="lg:col-span-3 space-y-6">
          {filteredSections.map(section => {
            const Icon = section.icon;
            return (
              <Card key={section.id} padding="lg">
                <article id={`help-section-${section.id}`} className="scroll-mt-4">
                  <header className="flex items-center gap-3 mb-4">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                      {section.title}
                    </h2>
                  </header>
                  {section.body}
                </article>
              </Card>
            );
          })}
          {filteredSections.length === 0 && (
            <Card padding="lg">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No sections match &ldquo;{query}&rdquo;. Try a different search term.
              </p>
            </Card>
          )}
        </main>
      </div>
    </div>
  );
}

export default HelpPage;
