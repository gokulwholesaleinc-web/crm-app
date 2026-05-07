import { useId } from 'react';
import type { PreferencesSectionProps } from './DensitySection';
import {
  DEFAULT_MAIN_NAVIGATION,
  DEFAULT_SECONDARY_NAVIGATION,
  type NavItem,
} from '../../layout/navigation.config';

const PROTECTED_ID = 'settings';

interface ItemRowProps {
  item: NavItem;
  hidden: Set<string>;
  idPrefix: string;
  onToggle: (id: string, nextChecked: boolean) => void;
}

function ItemRow({ item, hidden, idPrefix, onToggle }: ItemRowProps) {
  const inputId = `${idPrefix}-${item.id}`;
  const isProtected = item.id === PROTECTED_ID;
  const checked = isProtected ? true : !hidden.has(item.id);
  const describedById = isProtected ? `${inputId}-desc` : undefined;

  return (
    <li className="flex items-center gap-3 py-1.5">
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={isProtected}
        onChange={(e) => onToggle(item.id, e.target.checked)}
        aria-describedby={describedById}
        className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-700"
      />
      <label
        htmlFor={inputId}
        className={
          isProtected
            ? 'flex flex-1 items-center gap-2 text-sm text-gray-500 dark:text-gray-400'
            : 'flex flex-1 items-center gap-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer'
        }
      >
        <item.icon className="h-4 w-4 flex-shrink-0 text-gray-400 dark:text-gray-500" aria-hidden="true" />
        <span>{item.name}</span>
      </label>
      {isProtected && (
        <span
          id={describedById}
          className="text-xs text-gray-400 dark:text-gray-500"
        >
          Always visible
        </span>
      )}
    </li>
  );
}

export function NavVisibilitySection({ draft, setDraft }: PreferencesSectionProps) {
  const mainListId = useId();
  const secondaryListId = useId();
  const hidden = new Set(draft.hiddenNavIds ?? []);

  const handleToggle = (id: string, nextChecked: boolean) => {
    if (id === PROTECTED_ID) return;
    const current = new Set(draft.hiddenNavIds ?? []);
    if (nextChecked) {
      current.delete(id);
    } else {
      current.add(id);
    }
    setDraft('hiddenNavIds', Array.from(current));
  };

  const handleShowAll = () => {
    setDraft('hiddenNavIds', []);
  };

  return (
    <section aria-labelledby="prefs-nav-heading">
      <h3
        id="prefs-nav-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Sidebar items
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Uncheck items you don&rsquo;t use to hide them from the sidebar.
      </p>

      <div className="mt-3 space-y-4">
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Main navigation
          </h4>
          <ul className="mt-1" role="group" aria-label="Main navigation items">
            {DEFAULT_MAIN_NAVIGATION.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                hidden={hidden}
                idPrefix={mainListId}
                onToggle={handleToggle}
              />
            ))}
          </ul>
        </div>

        <div>
          <h4 className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Secondary navigation
          </h4>
          <ul className="mt-1" role="group" aria-label="Secondary navigation items">
            {DEFAULT_SECONDARY_NAVIGATION.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                hidden={hidden}
                idPrefix={secondaryListId}
                onToggle={handleToggle}
              />
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={handleShowAll}
          disabled={hidden.size === 0}
          className="text-xs font-medium text-primary-600 hover:text-primary-700 disabled:cursor-not-allowed disabled:text-gray-400 dark:text-primary-400 dark:hover:text-primary-300"
        >
          Show all
        </button>
      </div>
    </section>
  );
}
