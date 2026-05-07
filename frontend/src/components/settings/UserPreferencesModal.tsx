import { useEffect, useState } from 'react';
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

/**
 * Per-user preference editor. Sections receive a shared `draft` object and a
 * `setDraft` updater so each can edit its own slice without persisting until
 * the user clicks Save (which writes the merged draft back to localStorage in
 * one call). Cancel discards the draft and reverts to the on-disk values.
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

  // Re-sync draft from on-disk prefs whenever the modal (re)opens. Without
  // this, closing without saving and reopening would still show the
  // unsaved-but-stale draft from the previous session.
  useEffect(() => {
    if (isOpen) setDraft(prefs);
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
    setMany(draft);
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
