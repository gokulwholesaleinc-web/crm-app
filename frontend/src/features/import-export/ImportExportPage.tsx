/**
 * Import/Export page for CSV data import and export operations.
 * Supports smart column mapping preview before import.
 */

import { useState, useRef, useCallback } from 'react';
import {
  ArrowUpTrayIcon,
  ArrowDownTrayIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  XMarkIcon,
  UserPlusIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/ui';
import {
  importContacts,
  importCompanies,
  importLeads,
  exportContacts,
  exportCompanies,
  exportLeads,
  getTemplate,
  previewImport,
  downloadBlob,
  generateExportFilename,
} from '../../api/importExport';
import { showError } from '../../utils/toast';
import type { ImportResult, ImportPreview, ImportExportEntityType, ContactDecision, ContactMatch } from '../../types';

type OperationStatus = 'idle' | 'loading' | 'previewing' | 'importing' | 'success' | 'error';

interface ExportCardProps {
  title: string;
  description: string;
  entityType: ImportExportEntityType;
  onExport: () => Promise<void>;
  onTemplate: () => Promise<void>;
  isExporting: boolean;
}

function ExportCard({ title, description, onExport, onTemplate, isExporting }: ExportCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-start gap-3">
        <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
          <ArrowDownTrayIcon className="h-6 w-6 text-blue-600 dark:text-blue-400" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{description}</p>
          <div className="flex flex-col sm:flex-row gap-2 mt-3">
            <Button
              size="sm"
              onClick={onExport}
              isLoading={isExporting}
              leftIcon={<ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />}
            >
              Export CSV
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onTemplate}
              leftIcon={<DocumentTextIcon className="h-4 w-4" aria-hidden="true" />}
            >
              Download Template
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface ImportState {
  status: OperationStatus;
  result: ImportResult | null;
  preview: ImportPreview | null;
  file: File | null;
  error: string | null;
}

const INITIAL_IMPORT_STATE: ImportState = {
  status: 'idle',
  result: null,
  preview: null,
  file: null,
  error: null,
};

interface ImportSectionProps {
  entityType: ImportExportEntityType;
  label: string;
  state: ImportState;
  contactDecisions: Record<string, ContactDecision>;
  onContactDecisionChange: (csvName: string, decision: ContactDecision) => void;
  onFileSelect: (file: File) => void;
  onConfirmImport: () => void;
  onCancel: () => void;
}

function ImportSection({ entityType, label, state, contactDecisions, onContactDecisionChange, onFileSelect, onConfirmImport, onCancel }: ImportSectionProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileSelect(file);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-start gap-3">
        <div className="p-2 bg-green-50 dark:bg-green-900/30 rounded-lg">
          <ArrowUpTrayIcon className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Import {label}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Upload a CSV file to import {label.toLowerCase()}
          </p>

          <div className="mt-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="hidden"
              id={`import-${entityType}`}
              aria-label={`Choose CSV file to import ${label.toLowerCase()}`}
            />
            {state.status === 'idle' || state.status === 'success' || state.status === 'error' ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                leftIcon={<ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />}
              >
                Choose CSV File
              </Button>
            ) : null}
          </div>

          {/* Preview */}
          {state.status === 'previewing' && (
            <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-md">
              <div className="flex items-center gap-2">
                <ArrowPathIcon className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" aria-hidden="true" />
                <span className="text-sm text-blue-800 dark:text-blue-300">Analyzing CSV...</span>
              </div>
            </div>
          )}

          {state.preview && (state.status === 'loading' || state.status === 'importing') && (
            <PreviewPanel
              preview={state.preview}
              fileName={state.file?.name ?? ''}
              isImporting={state.status === 'importing'}
              contactDecisions={contactDecisions}
              onContactDecisionChange={onContactDecisionChange}
              onConfirm={onConfirmImport}
              onCancel={onCancel}
            />
          )}

          {/* Success */}
          {state.status === 'success' && state.result && (
            <div className="mt-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-md" role="status" aria-live="polite">
              <div className="flex items-center gap-2">
                <CheckCircleIcon className="h-5 w-5 text-green-600 dark:text-green-400" aria-hidden="true" />
                <span className="text-sm font-medium text-green-800 dark:text-green-300">
                  Successfully imported {state.result.imported_count} record{state.result.imported_count !== 1 ? 's' : ''}
                </span>
              </div>
              {(state.result.contacts_created ?? 0) > 0 && (
                <p className="text-xs text-blue-700 dark:text-blue-400 mt-1">
                  {state.result.contacts_created} contact{state.result.contacts_created !== 1 ? 's' : ''} created
                  {(state.result.contacts_linked ?? 0) > 0 && `, ${state.result.contacts_linked} linked to existing`}
                </p>
              )}
              {state.result.duplicates_skipped > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-medium text-yellow-700 dark:text-yellow-400">
                    {state.result.duplicates_skipped} already in CRM (skipped):
                  </p>
                  {state.result.duplicates && state.result.duplicates.length > 0 && (
                    <ul className="mt-1 text-xs text-yellow-600 dark:text-yellow-400 max-h-40 overflow-y-auto space-y-0.5">
                      {state.result.duplicates.map((d, i) => (
                        <li key={i} className="flex justify-between gap-2">
                          <span className="font-medium truncate">{d.label || 'Unknown'}</span>
                          <span className="text-yellow-500 dark:text-yellow-500 flex-shrink-0">{d.email}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {state.result.errors.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-medium text-yellow-700 dark:text-yellow-400">
                    {state.result.errors.length} warning{state.result.errors.length !== 1 ? 's' : ''}:
                  </p>
                  <ul className="mt-1 text-xs text-yellow-600 dark:text-yellow-400 list-disc list-inside max-h-24 overflow-y-auto">
                    {state.result.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Error */}
          {state.status === 'error' && state.error && (
            <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-md" role="alert">
              <div className="flex items-center gap-2">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-600 dark:text-red-400" aria-hidden="true" />
                <span className="text-sm font-medium text-red-800 dark:text-red-300">{state.error}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function getMatchBadgeColor(pct: number): string {
  if (pct >= 90) return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
  if (pct >= 70) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300';
  return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300';
}

interface ContactMatchPanelProps {
  matches: ContactMatch[];
  decisions: Record<string, ContactDecision>;
  onDecisionChange: (csvName: string, decision: ContactDecision) => void;
}

function ContactMatchPanel({ matches, decisions, onDecisionChange }: ContactMatchPanelProps) {
  if (matches.length === 0) return null;

  return (
    <div className="border border-blue-200 dark:border-blue-700 rounded-md p-3 bg-blue-50/50 dark:bg-blue-900/10">
      <div className="flex items-center gap-2 mb-2">
        <UserPlusIcon className="h-4 w-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />
        <p className="text-xs font-semibold text-blue-800 dark:text-blue-300">
          Contact Matching ({matches.length} contact{matches.length !== 1 ? 's' : ''} detected)
        </p>
      </div>
      <div className="space-y-2 max-h-60 overflow-y-auto">
        {matches.map((match) => {
          const decision = decisions[match.csv_name] ?? { csv_name: match.csv_name, action: 'create_new' as const };
          const hasMatches = match.candidates.length > 0;

          return (
            <div key={`${match.row}-${match.csv_name}`} className="flex items-start gap-3 p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                  Row {match.row}: {match.csv_name}
                </p>
                {hasMatches ? (
                  <div className="mt-1 space-y-1">
                    {match.candidates.map((c) => (
                      <label key={c.contact_id} className="flex items-center gap-2 text-xs cursor-pointer group">
                        <input
                          type="radio"
                          name={`contact-${match.csv_name}`}
                          checked={decision.action === 'link_existing' && decision.contact_id === c.contact_id}
                          onChange={() => onDecisionChange(match.csv_name, {
                            csv_name: match.csv_name,
                            action: 'link_existing',
                            contact_id: c.contact_id,
                          })}
                          className="text-blue-600"
                        />
                        <LinkIcon className="h-3 w-3 text-gray-400 group-hover:text-blue-500" aria-hidden="true" />
                        <span className="text-gray-700 dark:text-gray-300 truncate">
                          {c.name}{c.email ? ` (${c.email})` : ''}
                        </span>
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium ${getMatchBadgeColor(c.match_pct)}`}>
                          {c.match_pct}%
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">No existing matches found</p>
                )}
              </div>
              <div className="flex flex-col gap-1 shrink-0">
                <label className="flex items-center gap-1.5 text-[10px] cursor-pointer">
                  <input
                    type="radio"
                    name={`contact-${match.csv_name}`}
                    checked={decision.action === 'create_new'}
                    onChange={() => onDecisionChange(match.csv_name, {
                      csv_name: match.csv_name,
                      action: 'create_new',
                    })}
                    className="text-green-600"
                  />
                  <span className="text-green-700 dark:text-green-400 font-medium">Create new</span>
                </label>
                <label className="flex items-center gap-1.5 text-[10px] cursor-pointer">
                  <input
                    type="radio"
                    name={`contact-${match.csv_name}`}
                    checked={decision.action === 'skip'}
                    onChange={() => onDecisionChange(match.csv_name, {
                      csv_name: match.csv_name,
                      action: 'skip',
                    })}
                    className="text-gray-400"
                  />
                  <span className="text-gray-500 dark:text-gray-400">Skip</span>
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface PreviewPanelProps {
  preview: ImportPreview;
  fileName: string;
  isImporting: boolean;
  contactDecisions: Record<string, ContactDecision>;
  onContactDecisionChange: (csvName: string, decision: ContactDecision) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

function PreviewPanel({ preview, fileName, isImporting, contactDecisions, onContactDecisionChange, onConfirm, onCancel }: PreviewPanelProps) {
  const mappedCount = Object.keys(preview.column_mapping).length;
  const mappingEntries = Object.entries(preview.column_mapping);

  return (
    <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-md space-y-3">
      {/* File info */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
          {fileName} &mdash; {preview.total_rows} row{preview.total_rows !== 1 ? 's' : ''}
        </span>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          aria-label="Cancel import"
        >
          <XMarkIcon className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {/* Column mapping */}
      <div>
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          Column mapping ({mappedCount} matched):
        </p>
        <div className="flex flex-wrap gap-1">
          {mappingEntries.map(([csv, field]) => (
            <span
              key={csv}
              className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300"
            >
              {csv === field ? field : `${csv} \u2192 ${field}`}
            </span>
          ))}
          {preview.contact_person_column && (
            <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300">
              {preview.contact_person_column} &rarr; linked contacts
            </span>
          )}
        </div>
        {preview.unmapped_columns.length > 0 && (
          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
            Ignored columns: {preview.unmapped_columns.join(', ')}
          </p>
        )}
        {preview.missing_fields.length > 0 && (
          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
            Missing fields (will be empty): {preview.missing_fields.join(', ')}
          </p>
        )}
      </div>

      {/* Preview table */}
      {preview.preview_rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead>
              <tr>
                {Object.values(preview.column_mapping).map((field) => (
                  <th
                    key={field}
                    className="px-2 py-1 text-left font-medium text-gray-600 dark:text-gray-400 border-b border-gray-200 dark:border-gray-600"
                  >
                    {field}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.preview_rows.map((row, i) => (
                <tr key={i}>
                  {Object.values(preview.column_mapping).map((field) => (
                    <td
                      key={field}
                      className="px-2 py-1 text-gray-800 dark:text-gray-200 border-b border-gray-100 dark:border-gray-700 max-w-[150px] truncate"
                    >
                      {row[field] || <span className="text-gray-300 dark:text-gray-600">&mdash;</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {preview.total_rows > 5 && (
            <p className="text-xs text-gray-400 mt-1">...and {preview.total_rows - 5} more rows</p>
          )}
        </div>
      )}

      {/* Contact matching for company imports */}
      {preview.contact_matches && preview.contact_matches.length > 0 && (
        <ContactMatchPanel
          matches={preview.contact_matches}
          decisions={contactDecisions}
          onDecisionChange={onContactDecisionChange}
        />
      )}

      {/* Warnings */}
      {preview.warnings.length > 0 && (
        <div className="text-xs text-yellow-600 dark:text-yellow-400">
          {preview.warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" onClick={onConfirm} isLoading={isImporting}>
          Import {preview.total_rows} rows
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isImporting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function ImportExportPage() {
  const [exportingEntity, setExportingEntity] = useState<string | null>(null);
  const [importStates, setImportStates] = useState<Record<ImportExportEntityType, ImportState>>({
    contacts: { ...INITIAL_IMPORT_STATE },
    companies: { ...INITIAL_IMPORT_STATE },
    leads: { ...INITIAL_IMPORT_STATE },
  });
  const [contactDecisions, setContactDecisions] = useState<Record<string, ContactDecision>>({});

  const updateImportState = (entityType: ImportExportEntityType, patch: Partial<ImportState>) => {
    setImportStates((prev) => ({
      ...prev,
      [entityType]: { ...prev[entityType], ...patch },
    }));
  };

  const handleContactDecisionChange = useCallback((csvName: string, decision: ContactDecision) => {
    setContactDecisions((prev) => ({ ...prev, [csvName]: decision }));
  }, []);

  const handleExport = async (entityType: ImportExportEntityType) => {
    setExportingEntity(entityType);
    try {
      const exportFns = { contacts: exportContacts, companies: exportCompanies, leads: exportLeads };
      const blob = await exportFns[entityType]();
      downloadBlob(blob, generateExportFilename(entityType));
    } catch (error) {
      showError(`Failed to export ${entityType}`);
    } finally {
      setExportingEntity(null);
    }
  };

  const handleTemplate = async (entityType: ImportExportEntityType) => {
    try {
      const blob = await getTemplate(entityType);
      downloadBlob(blob, `${entityType}_template.csv`);
    } catch (error) {
      showError(`Failed to download template for ${entityType}`);
    }
  };

  const handleFileSelect = async (entityType: ImportExportEntityType, file: File) => {
    updateImportState(entityType, { status: 'previewing', file, result: null, error: null, preview: null });
    if (entityType === 'companies') {
      setContactDecisions({});
    }
    try {
      const preview = await previewImport(entityType, file);
      // Pre-populate contact decisions as "create_new" for all matches
      if (preview.contact_matches) {
        const defaults: Record<string, ContactDecision> = {};
        for (const match of preview.contact_matches) {
          if (!defaults[match.csv_name]) {
            // Auto-select existing contact if 100% match, otherwise create new
            const exactMatch = match.candidates.find((c) => c.match_pct === 100);
            defaults[match.csv_name] = exactMatch
              ? { csv_name: match.csv_name, action: 'link_existing', contact_id: exactMatch.contact_id }
              : { csv_name: match.csv_name, action: 'create_new' };
          }
        }
        setContactDecisions(defaults);
      }
      updateImportState(entityType, { status: 'loading', preview });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to preview file';
      updateImportState(entityType, { status: 'error', error: message });
    }
  };

  const handleConfirmImport = async (entityType: ImportExportEntityType) => {
    const { file } = importStates[entityType];
    if (!file) return;

    updateImportState(entityType, { status: 'importing' });
    try {
      let result: ImportResult;
      if (entityType === 'companies') {
        const decisions = Object.values(contactDecisions);
        result = await importCompanies(file, true, decisions.length > 0 ? decisions : undefined);
      } else {
        const importFns = { contacts: importContacts, leads: importLeads } as const;
        result = await importFns[entityType](file);
      }
      updateImportState(entityType, { status: 'success', result, preview: null, file: null });
      setContactDecisions({});
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Import failed';
      updateImportState(entityType, { status: 'error', error: message, preview: null, file: null });
    }
  };

  const handleCancel = (entityType: ImportExportEntityType) => {
    updateImportState(entityType, { ...INITIAL_IMPORT_STATE });
    if (entityType === 'companies') {
      setContactDecisions({});
    }
  };

  const entityConfigs: { type: ImportExportEntityType; label: string; description: string }[] = [
    { type: 'contacts', label: 'Contacts', description: 'Export all contacts as a CSV file' },
    { type: 'companies', label: 'Companies', description: 'Export all companies as a CSV file' },
    { type: 'leads', label: 'Leads', description: 'Export all leads as a CSV file' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Import / Export</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Import and export your CRM data as CSV files
        </p>
      </div>

      {/* Export Section */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Export Data</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {entityConfigs.map((config) => (
            <ExportCard
              key={config.type}
              title={`Export ${config.label}`}
              description={config.description}
              entityType={config.type}
              onExport={() => handleExport(config.type)}
              onTemplate={() => handleTemplate(config.type)}
              isExporting={exportingEntity === config.type}
            />
          ))}
        </div>
      </div>

      {/* Import Section */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Import Data</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
          Contacts are auto-created when importing companies via the &quot;Point of Contact&quot; column.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {entityConfigs
            .filter((config) => config.type !== 'contacts')
            .map((config) => (
              <ImportSection
                key={config.type}
                entityType={config.type}
                label={config.label}
                state={importStates[config.type]}
                contactDecisions={contactDecisions}
                onContactDecisionChange={handleContactDecisionChange}
                onFileSelect={(file) => handleFileSelect(config.type, file)}
                onConfirmImport={() => handleConfirmImport(config.type)}
                onCancel={() => handleCancel(config.type)}
              />
            ))}
        </div>
      </div>
    </div>
  );
}

export default ImportExportPage;
