import { Select, type SelectOption } from '../../ui/Select';
import type {
  EntityKindWithTabs,
  UserPreferences,
} from '../../../hooks/useUserPreferences';
import type { PreferencesSectionProps } from './DensitySection';

// Tab IDs are mirrored from each entity's detail page. They stay in sync
// because invalid saved values are silently ignored by `useUrlTabState`
// (the fallback wins), so a renamed tab degrades gracefully.
const ENTITY_TABS: Record<EntityKindWithTabs, readonly string[]> = {
  contact: [
    'details',
    'activities',
    'notes',
    'emails',
    'contracts',
    'quotes',
    'proposals',
    'payments',
    'documents',
    'attachments',
    'history',
    'sharing',
  ],
  lead: [
    'details',
    'activities',
    'notes',
    'emails',
    'attachments',
    'comments',
    'history',
    'sharing',
  ],
  opportunity: [
    'details',
    'activities',
    'quotes',
    'proposals',
    'payments',
    'notes',
    'attachments',
    'comments',
    'history',
    'sharing',
  ],
  company: [
    'overview',
    'opportunities',
    'contracts',
    'quotes',
    'proposals',
    'payments',
    'activities',
    'notes',
    'attachments',
    'meta',
    'expenses',
    'history',
    'sharing',
  ],
};

const ENTITY_LABELS: Record<EntityKindWithTabs, string> = {
  contact: 'Contacts',
  lead: 'Leads',
  opportunity: 'Opportunities',
  company: 'Companies',
};

const TAB_LABEL_OVERRIDES: Record<string, string> = {
  meta: 'Meta/Social',
};

function formatTabLabel(id: string): string {
  return TAB_LABEL_OVERRIDES[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

const NO_PREFERENCE_VALUE = '';

export function TabDefaultsSection({ draft, setDraft }: PreferencesSectionProps) {
  const tabDefaults = draft.tabDefaults ?? {};

  const handleChange = (entity: EntityKindWithTabs, value: string) => {
    const next: NonNullable<UserPreferences['tabDefaults']> = { ...tabDefaults };
    if (value === NO_PREFERENCE_VALUE) {
      delete next[entity];
    } else {
      next[entity] = value;
    }
    setDraft('tabDefaults', next);
  };

  return (
    <section aria-labelledby="prefs-tabs-heading">
      <h3
        id="prefs-tabs-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Default tab on detail pages
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Pick the tab that opens first when you visit each entity type.
        Deep links with <code>?tab=</code> still win.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {(Object.keys(ENTITY_TABS) as EntityKindWithTabs[]).map((entity) => {
          const options: SelectOption[] = [
            { value: NO_PREFERENCE_VALUE, label: '(no preference)' },
            ...ENTITY_TABS[entity].map((id) => ({
              value: id,
              label: formatTabLabel(id),
            })),
          ];
          const current = tabDefaults[entity] ?? NO_PREFERENCE_VALUE;
          return (
            <Select
              key={entity}
              label={ENTITY_LABELS[entity]}
              options={options}
              value={current}
              onChange={(e) => handleChange(entity, e.target.value)}
            />
          );
        })}
      </div>
    </section>
  );
}
