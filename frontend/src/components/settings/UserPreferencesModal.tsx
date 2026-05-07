import { useEffect, useRef, useState } from 'react';
import { Button, Modal } from '../ui';
import {
  useUserPreferences,
  type UserPreferences,
} from '../../hooks/useUserPreferences';
import { DensitySection } from './preferences/DensitySection';
import { TabDefaultsSection } from './preferences/TabDefaultsSection';
import { NavVisibilitySection } from './preferences/NavVisibilitySection';
import { SignatureSection } from './preferences/SignatureSection';

export interface UserPreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PREF_FIELDS: ReadonlyArray<keyof UserPreferences> = [
  'density',
  'tabDefaults',
  'hiddenNavIds',
  'signature',
  'listDefaults',
];

function fieldChanged<K extends keyof UserPreferences>(
  a: UserPreferences[K],
  b: UserPreferences[K],
): boolean {
  // Pref values are small (≤ a few strings or one object with a handful of
  // keys) so JSON.stringify is plenty fast and correct for our shapes.
  return JSON.stringify(a) !== JSON.stringify(b);
}

/**
 * Per-user preference editor. Sections receive a shared `draft` object and a
 * `setDraft` updater so each can edit its own slice without persisting until
 * the user clicks Save (which writes ONLY the fields that actually changed
 * since the modal opened — fields a sibling tab edited while the modal was
 * open are left alone instead of being clobbered by a stale draft snapshot).
 *
 * Each pref slice (density, tabDefaults, hiddenNavIds, signature) is a
 * separate top-level field on UserPreferences — adding a new pref means
 * adding a new field, not extending a generic registry.
 */
export function UserPreferencesModal({
  isOpen,
  onClose,
}: UserPreferencesModalProps) {
  const { prefs, setMany } = useUserPreferences();
  const [draft, setDraft] = useState<UserPreferences>(prefs);
  // Snapshot prefs at the moment the modal opens. The Save handler diffs
  // draft against this, NOT against the live `prefs` (which may have been
  // updated by another tab during the edit session).
  const openBaselineRef = useRef<UserPreferences>(prefs);

  useEffect(() => {
    if (isOpen) {
      setDraft(prefs);
      openBaselineRef.current = prefs;
    }
    // We intentionally only re-seed on open transitions; updating `prefs`
    // mid-edit (from another tab) would clobber the user's in-progress
    // changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const updateField = <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => {
    setDraft((curr) => ({ ...curr, [key]: value }));
  };

  const handleSave = () => {
    const baseline = openBaselineRef.current;
    const partial: Partial<UserPreferences> = {};
    for (const key of PREF_FIELDS) {
      if (fieldChanged(draft[key], baseline[key])) {
        // Cast widens because TS can't narrow Partial assignment through
        // a generic key. Each branch is sound by construction since the
        // value was produced by the matching section bound to the same
        // key.
        (partial as Record<keyof UserPreferences, unknown>)[key] = draft[key];
      }
    }
    if (Object.keys(partial).length > 0) {
      setMany(partial);
    }
    onClose();
  };

  const sectionProps = { draft, setDraft: updateField };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Preferences"
      description="Personal settings stored in this browser."
      size="full"
    >
      <div className="space-y-6">
        <DensitySection {...sectionProps} />
        <hr className="border-gray-200 dark:border-gray-700" />
        <TabDefaultsSection {...sectionProps} />
        <hr className="border-gray-200 dark:border-gray-700" />
        <NavVisibilitySection {...sectionProps} />
        <hr className="border-gray-200 dark:border-gray-700" />
        <SignatureSection {...sectionProps} />
      </div>
      <div className="mt-6 flex justify-end gap-3 border-t border-gray-200 dark:border-gray-700 pt-4">
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" onClick={handleSave}>
          Save preferences
        </Button>
      </div>
    </Modal>
  );
}
