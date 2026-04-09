/**
 * Duplicate Management Page - allows scanning for and merging duplicate records.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Spinner, ConfirmDialog } from '../../components/ui';
import { useCheckDuplicates, useMergeEntities } from '../../hooks/useDedup';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useLeads } from '../../hooks/useLeads';
import { useUIStore } from '../../store/uiStore';
import type { DuplicateMatch } from '../../api/dedup';

type EntityType = 'contacts' | 'companies' | 'leads';

interface DuplicateGroup {
  source: { id: number; display_name: string; email?: string | null; phone?: string | null };
  matches: DuplicateMatch[];
}

function DuplicatesPage() {
  const navigate = useNavigate();
  const addToast = useUIStore((state) => state.addToast);
  const [selectedEntityType, setSelectedEntityType] = useState<EntityType>('contacts');
  const [scanning, setScanning] = useState(false);
  const [duplicateGroups, setDuplicateGroups] = useState<DuplicateGroup[]>([]);
  const [mergeConfirm, setMergeConfirm] = useState<{
    primaryId: number;
    secondaryId: number;
    primaryName: string;
    secondaryName: string;
  } | null>(null);

  const checkDuplicatesMutation = useCheckDuplicates();
  const mergeMutation = useMergeEntities();

  // Fetch entity lists for scanning
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: leadsData } = useLeads({ page_size: 100 });

  const handleScan = async () => {
    setScanning(true);
    setDuplicateGroups([]);

    try {
      let entities: Array<{ id: number; display_name: string; email?: string | null; phone?: string | null; data: Record<string, unknown> }> = [];

      if (selectedEntityType === 'contacts' && contactsData?.items) {
        entities = contactsData.items.map((c) => ({
          id: c.id,
          display_name: `${c.first_name} ${c.last_name}`,
          email: c.email,
          phone: c.phone,
          data: { email: c.email, phone: c.phone, first_name: c.first_name, last_name: c.last_name },
        }));
      } else if (selectedEntityType === 'companies' && companiesData?.items) {
        entities = companiesData.items.map((c) => ({
          id: c.id,
          display_name: c.name,
          email: c.email,
          phone: c.phone,
          data: { name: c.name },
        }));
      } else if (selectedEntityType === 'leads' && leadsData?.items) {
        entities = leadsData.items.map((l) => ({
          id: l.id,
          display_name: `${l.first_name} ${l.last_name}`,
          email: l.email,
          phone: l.phone,
          data: { email: l.email, phone: l.phone, first_name: l.first_name, last_name: l.last_name },
        }));
      }

      // Run duplicate checks with bounded concurrency instead of
      // sequentially. The previous loop awaited each mutation one-at-a-time,
      // so scanning 100 records meant 100 serial round-trips (tens of
      // seconds). A concurrency of 5 keeps the backend load reasonable
      // while cutting wall-clock time by ~5x. See interactive-pages.md #6.
      const CONCURRENCY = 5;
      type DuplicateResult = { entity: (typeof entities)[number]; matches: DuplicateMatch[] };
      const results: DuplicateResult[] = [];
      for (let i = 0; i < entities.length; i += CONCURRENCY) {
        const batch = entities.slice(i, i + CONCURRENCY);
        const settled = await Promise.all(
          batch.map(async (entity) => {
            const result = await checkDuplicatesMutation.mutateAsync({
              entityType: selectedEntityType,
              data: entity.data,
            });
            return {
              entity,
              matches: result.duplicates.filter((d) => d.id !== entity.id),
            };
          })
        );
        results.push(...settled);
      }

      // Group results after all checks complete so the "already seen"
      // filter stays stable regardless of request ordering.
      const groups: DuplicateGroup[] = [];
      const seen = new Set<number>();
      for (const { entity, matches } of results) {
        if (seen.has(entity.id) || matches.length === 0) continue;
        groups.push({ source: entity, matches });
        seen.add(entity.id);
        matches.forEach((m) => seen.add(m.id));
      }

      setDuplicateGroups(groups);
      if (groups.length === 0) {
        addToast({
          type: 'success',
          title: 'No Duplicates',
          message: `No duplicate ${selectedEntityType} found.`,
        });
      }
    } catch {
      addToast({
        type: 'error',
        title: 'Scan Failed',
        message: 'Failed to scan for duplicates.',
      });
    } finally {
      setScanning(false);
    }
  };

  const handleMergeConfirm = async () => {
    if (!mergeConfirm) return;

    try {
      await mergeMutation.mutateAsync({
        entityType: selectedEntityType,
        primaryId: mergeConfirm.primaryId,
        secondaryId: mergeConfirm.secondaryId,
      });
      setMergeConfirm(null);
      addToast({
        type: 'success',
        title: 'Merge Complete',
        message: `Successfully merged records.`,
      });
      // Re-scan after merge
      handleScan();
    } catch {
      addToast({
        type: 'error',
        title: 'Merge Failed',
        message: 'Failed to merge records.',
      });
    }
  };

  const getViewUrl = (entityType: EntityType, id: number) => {
    return `/${entityType}/${id}`;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">Duplicate Detection</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Scan for and merge duplicate records to keep your CRM data clean.
        </p>
      </div>

      {/* Controls */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
          <div>
            <label htmlFor="entity-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Entity Type
            </label>
            <select
              id="entity-type"
              value={selectedEntityType}
              onChange={(e) => {
                setSelectedEntityType(e.target.value as EntityType);
                setDuplicateGroups([]);
              }}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="contacts">Contacts</option>
              <option value="companies">Companies</option>
              <option value="leads">Leads</option>
            </select>
          </div>
          <Button onClick={handleScan} isLoading={scanning}>
            {scanning ? 'Scanning...' : 'Scan for Duplicates'}
          </Button>
        </div>
      </div>

      {/* Results */}
      {scanning && (
        <div className="flex items-center justify-center py-8">
          <Spinner size="lg" />
          <span className="ml-3 text-sm text-gray-500 dark:text-gray-400">Scanning for duplicates...</span>
        </div>
      )}

      {!scanning && duplicateGroups.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Found {duplicateGroups.length} potential duplicate group{duplicateGroups.length !== 1 ? 's' : ''}
          </h3>
          {duplicateGroups.map((group, idx) => (
            <div key={idx} className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
              <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-700">
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                  Duplicate Group: {group.source.display_name}
                </p>
              </div>
              <div className="divide-y divide-gray-100 dark:divide-gray-700">
                {/* Primary record */}
                <div className="p-4 flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {group.source.display_name}
                      <span className="ml-2 text-xs text-green-600 dark:text-green-400 font-normal">(Primary)</span>
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {group.source.email} {group.source.phone ? `| ${group.source.phone}` : ''}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => navigate(getViewUrl(selectedEntityType, group.source.id))}
                  >
                    View
                  </Button>
                </div>
                {/* Duplicate matches */}
                {group.matches.map((match) => (
                  <div key={match.id} className="p-4 flex items-center justify-between bg-gray-50 dark:bg-gray-900">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {match.display_name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {match.email} {match.phone ? `| ${match.phone}` : ''}
                      </p>
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">{match.match_reason}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                      <Button
                        variant="secondary"
                        onClick={() => navigate(getViewUrl(selectedEntityType, match.id))}
                      >
                        View
                      </Button>
                      <Button
                        onClick={() =>
                          setMergeConfirm({
                            primaryId: group.source.id,
                            secondaryId: match.id,
                            primaryName: group.source.display_name,
                            secondaryName: match.display_name,
                          })
                        }
                      >
                        Merge
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Merge Confirmation */}
      <ConfirmDialog
        isOpen={!!mergeConfirm}
        onClose={() => setMergeConfirm(null)}
        onConfirm={handleMergeConfirm}
        title="Merge Records"
        message={
          mergeConfirm
            ? `Merge "${mergeConfirm.secondaryName}" into "${mergeConfirm.primaryName}"? All activities, notes, and tags will be transferred to the primary record. The secondary record will be deleted. This cannot be undone.`
            : ''
        }
        confirmLabel="Merge"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={mergeMutation.isPending}
      />
    </div>
  );
}

export default DuplicatesPage;
