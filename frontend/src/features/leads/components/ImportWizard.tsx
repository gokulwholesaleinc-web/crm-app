/**
 * Multi-step import wizard with column mapping for leads, contacts, and companies.
 * Steps: 1) Upload CSV  2) Map columns  3) Campaign (optional)  4) Preview & confirm  5) Import results
 */

import { useState, useCallback, useMemo } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { previewImport, importWithMapping } from '../../../api/importExport';
import { listEmailTemplates, createCampaignFromImport } from '../../../api/campaigns';
import type { ImportPreview, EmailTemplate } from '../../../types';
import {
  ArrowUpTrayIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
  MegaphoneIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

type EntityType = 'leads' | 'contacts' | 'companies';

interface ImportWizardProps {
  isOpen: boolean;
  onClose: () => void;
  entityType: EntityType;
  onSuccess?: () => void;
  /** When true, the campaign step is shown by default (e.g. opened from CampaignsPage) */
  defaultCampaignEnabled?: boolean;
}

type WizardStep = 'upload' | 'mapping' | 'campaign' | 'preview' | 'result';

interface ImportResult {
  success: boolean;
  imported_count: number;
  errors: string[];
  duplicates_skipped: number;
  imported_ids?: number[];
}

interface CampaignConfig {
  enabled: boolean;
  name: string;
  template_id: number | null;
  delay_days: number;
}

export function ImportWizard({ isOpen, onClose, entityType, onSuccess, defaultCampaignEnabled = false }: ImportWizardProps) {
  const [step, setStep] = useState<WizardStep>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [campaignConfig, setCampaignConfig] = useState<CampaignConfig>({
    enabled: defaultCampaignEnabled,
    name: `LinkedIn Import - ${new Date().toLocaleDateString()}`,
    template_id: null,
    delay_days: 1,
  });
  const [campaignResult, setCampaignResult] = useState<{ name: string; count: number } | null>(null);

  const { data: templates } = useQuery({
    queryKey: ['campaigns', 'templates'],
    queryFn: () => listEmailTemplates(),
    enabled: isOpen,
  });

  const isLinkedIn = preview?.is_linkedin_format === true;

  const reset = useCallback(() => {
    setStep('upload');
    setFile(null);
    setPreview(null);
    setColumnMapping({});
    setResult(null);
    setCampaignConfig({
      enabled: defaultCampaignEnabled,
      name: `LinkedIn Import - ${new Date().toLocaleDateString()}`,
      template_id: null,
      delay_days: 1,
    });
    setCampaignResult(null);
  }, [defaultCampaignEnabled]);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [reset, onClose]);

  const handleFileSelect = useCallback(async (selectedFile: File) => {
    setFile(selectedFile);
    setIsLoading(true);
    try {
      const previewData = await previewImport(entityType, selectedFile);
      setPreview(previewData);
      setColumnMapping(previewData.column_mapping || {});
      setStep('mapping');
    } catch {
      toast.error('Failed to parse CSV file');
    } finally {
      setIsLoading(false);
    }
  }, [entityType]);

  const handleMappingChange = useCallback((csvHeader: string, targetField: string) => {
    setColumnMapping(prev => ({ ...prev, [csvHeader]: targetField }));
  }, []);

  const importMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('No file selected');
      return importWithMapping(entityType, file, columnMapping);
    },
    onSuccess: async (data) => {
      setResult(data);
      setStep('result');
      if (data.success && data.imported_count > 0) {
        onSuccess?.();
        // Create campaign from imported IDs if enabled
        if (campaignConfig.enabled && data.imported_ids && data.imported_ids.length > 0) {
          try {
            const campaign = await createCampaignFromImport({
              name: campaignConfig.name,
              member_ids: data.imported_ids,
              member_type: entityType === 'leads' ? 'lead' : 'contact',
              template_id: campaignConfig.template_id ?? undefined,
              delay_days: campaignConfig.delay_days,
            });
            setCampaignResult({ name: campaign.name, count: campaign.member_count });
          } catch {
            toast.error('Import succeeded but campaign creation failed');
          }
        }
      }
    },
    onError: () => {
      toast.error('Import failed');
    },
  });

  const mappedFieldCount = useMemo(() => {
    return Object.values(columnMapping).filter(v => v && v !== 'skip').length;
  }, [columnMapping]);

  const allSteps: WizardStep[] = ['upload', 'mapping', 'campaign', 'preview', 'result'];
  const visibleSteps = allSteps.filter(
    (s) => s !== 'campaign' || campaignConfig.enabled || isLinkedIn
  );

  const stepTitle: Record<WizardStep, string> = {
    upload: `Import ${entityType}`,
    mapping: 'Map Columns',
    campaign: 'Campaign Setup',
    preview: 'Preview & Confirm',
    result: 'Import Complete',
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={stepTitle[step]}
      size="lg"
    >
      <div className="p-4 sm:p-6">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {visibleSteps.map((s, i) => {
            const currentIndex = visibleSteps.indexOf(step);
            const color = s === step ? 'bg-primary-600'
              : i < currentIndex ? 'bg-primary-300 dark:bg-primary-700'
              : 'bg-gray-200 dark:bg-gray-700';
            return <div key={s} className={`h-2 w-8 rounded-full ${color}`} />;
          })}
        </div>

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div className="text-center">
            <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-8">
              <ArrowUpTrayIcon className="mx-auto h-12 w-12 text-gray-400" aria-hidden="true" />
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                Drop a CSV file here or click to browse
              </p>
              <input
                type="file"
                accept=".csv"
                className="mt-4 text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileSelect(f);
                }}
              />
            </div>
            {isLoading && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Spinner size="sm" />
                <span className="text-sm text-gray-500">Analyzing CSV...</span>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Column Mapping */}
        {step === 'mapping' && preview && (
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {preview.total_rows} rows found. Map your CSV columns to CRM fields.
              {mappedFieldCount > 0 && ` (${mappedFieldCount} columns mapped)`}
            </p>

            {preview.source_detected === 'monday.com' && (
              <div className="mb-4 flex items-center gap-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 px-3 py-2 text-sm text-blue-700 dark:text-blue-300">
                <CheckCircleIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                Monday.com format detected — columns auto-mapped
              </div>
            )}

            {isLinkedIn && (
              <div className="mb-4 flex items-center gap-2 rounded-lg bg-indigo-50 dark:bg-indigo-900/20 px-3 py-2 text-sm text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                <svg className="h-4 w-4 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                </svg>
                LinkedIn Sales Navigator format detected — columns auto-mapped
              </div>
            )}

            <div className="max-h-80 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">CSV Column</th>
                    <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">Maps To</th>
                    <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">Sample</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {(preview.csv_headers || []).map((header: string) => {
                    const sampleValue = preview.preview_rows?.[0]?.[columnMapping[header] || ''] || '';
                    return (
                      <tr key={header}>
                        <td className="px-3 py-2 text-gray-900 dark:text-gray-100 font-mono text-xs">{header}</td>
                        <td className="px-3 py-2">
                          <select
                            value={columnMapping[header] || 'skip'}
                            onChange={(e) => handleMappingChange(header, e.target.value)}
                            className="w-full rounded border-gray-300 dark:border-gray-600 dark:bg-gray-800 text-sm py-1"
                            aria-label={`Map column ${header}`}
                          >
                            <option value="skip">-- Skip --</option>
                            {(preview.available_fields || []).map((field: string) => (
                              <option key={field} value={field}>{field}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 text-gray-500 text-xs truncate max-w-[150px]">{sampleValue}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {preview.warnings && preview.warnings.length > 0 && (
              <div className="mt-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 text-xs font-medium mb-1">
                  <ExclamationTriangleIcon className="h-4 w-4" aria-hidden="true" />
                  Warnings
                </div>
                <ul className="text-xs text-amber-600 dark:text-amber-300 space-y-0.5">
                  {preview.warnings.slice(0, 5).map((w: string, i: number) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Campaign toggle */}
            {(isLinkedIn || entityType === 'leads') && (
              <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-700">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={campaignConfig.enabled}
                    onChange={(e) => setCampaignConfig(prev => ({ ...prev, enabled: e.target.checked }))}
                    className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      Add imported {entityType} to a new campaign
                    </span>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Configure email campaign settings in the next step
                    </p>
                  </div>
                </label>
              </div>
            )}

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => { setStep('upload'); setFile(null); setPreview(null); }}
                leftIcon={<ArrowLeftIcon className="h-4 w-4" />}>
                Back
              </Button>
              <Button variant="primary" onClick={() => setStep(campaignConfig.enabled ? 'campaign' : 'preview')}
                leftIcon={<ArrowRightIcon className="h-4 w-4" />}
                disabled={mappedFieldCount === 0}>
                {campaignConfig.enabled ? 'Campaign Setup' : 'Preview'}
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Campaign Setup (optional) */}
        {step === 'campaign' && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <MegaphoneIcon className="h-5 w-5 text-primary-500" aria-hidden="true" />
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Configure the campaign for your imported {entityType}.
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="campaign-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Campaign Name
                </label>
                <input
                  id="campaign-name"
                  type="text"
                  value={campaignConfig.name}
                  onChange={(e) => setCampaignConfig(prev => ({ ...prev, name: e.target.value }))}
                  className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                  placeholder="Campaign name..."
                />
              </div>

              <div>
                <label htmlFor="campaign-template" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Email Template (optional)
                </label>
                <select
                  id="campaign-template"
                  value={campaignConfig.template_id ?? ''}
                  onChange={(e) => setCampaignConfig(prev => ({
                    ...prev,
                    template_id: e.target.value ? Number(e.target.value) : null,
                  }))}
                  className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                  aria-label="Select email template"
                >
                  <option value="">-- No template --</option>
                  {(templates ?? []).map((t: EmailTemplate) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="campaign-delay" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Delay Between Steps (days)
                </label>
                <input
                  id="campaign-delay"
                  type="number"
                  min={0}
                  max={30}
                  value={campaignConfig.delay_days}
                  onChange={(e) => setCampaignConfig(prev => ({
                    ...prev,
                    delay_days: Math.max(0, parseInt(e.target.value, 10) || 0),
                  }))}
                  className="mt-1 block w-32 rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                />
              </div>
            </div>

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setStep('mapping')}
                leftIcon={<ArrowLeftIcon className="h-4 w-4" />}>
                Back
              </Button>
              <Button variant="primary" onClick={() => setStep('preview')}
                leftIcon={<ArrowRightIcon className="h-4 w-4" />}
                disabled={!campaignConfig.name.trim()}>
                Preview
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Preview */}
        {step === 'preview' && preview && (
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Ready to import {preview.total_rows} rows with {mappedFieldCount} mapped fields.
            </p>

            <div className="max-h-64 overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0">
                  <tr>
                    {Object.entries(columnMapping)
                      .filter(([, v]) => v && v !== 'skip')
                      .map(([, field]) => (
                        <th key={field} className="text-left px-2 py-1.5 font-medium text-gray-700 dark:text-gray-300">{field}</th>
                      ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {(preview.preview_rows || []).slice(0, 5).map((row: Record<string, string>, i: number) => (
                    <tr key={i}>
                      {Object.entries(columnMapping)
                        .filter(([, v]) => v && v !== 'skip')
                        .map(([, field]) => (
                          <td key={field} className="px-2 py-1.5 text-gray-600 dark:text-gray-400 truncate max-w-[120px]">
                            {row[field] || '-'}
                          </td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Campaign summary in preview */}
            {campaignConfig.enabled && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-primary-50 dark:bg-primary-900/20 px-3 py-2 text-sm text-primary-700 dark:text-primary-300">
                <MegaphoneIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                Campaign &ldquo;{campaignConfig.name}&rdquo; will be created after import
              </div>
            )}

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setStep(campaignConfig.enabled ? 'campaign' : 'mapping')}
                leftIcon={<ArrowLeftIcon className="h-4 w-4" />}>
                Back
              </Button>
              <Button
                variant="primary"
                onClick={() => importMutation.mutate()}
                disabled={importMutation.isPending}
                leftIcon={importMutation.isPending ? <Spinner size="sm" /> : <CheckCircleIcon className="h-4 w-4" />}
              >
                {importMutation.isPending ? 'Importing...' : `Import ${preview.total_rows} rows`}
              </Button>
            </div>
          </div>
        )}

        {/* Step 5: Results */}
        {step === 'result' && result && (
          <div className="text-center">
            {result.success ? (
              <CheckCircleIcon className="mx-auto h-12 w-12 text-green-500" />
            ) : (
              <XCircleIcon className="mx-auto h-12 w-12 text-red-500" />
            )}
            <p className="mt-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
              {result.success ? 'Import Successful' : 'Import Failed'}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 max-w-xs mx-auto">
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                <p className="text-2xl font-bold text-green-600">{result.imported_count}</p>
                <p className="text-xs text-green-700 dark:text-green-400">Imported</p>
              </div>
              <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
                <p className="text-2xl font-bold text-amber-600">{result.duplicates_skipped}</p>
                <p className="text-xs text-amber-700 dark:text-amber-400">Skipped</p>
              </div>
            </div>
            {campaignResult && (
              <div className="mt-4 bg-primary-50 dark:bg-primary-900/20 rounded-lg p-3" role="status" aria-live="polite">
                <div className="flex items-center justify-center gap-2">
                  <MegaphoneIcon className="h-4 w-4 text-primary-600" aria-hidden="true" />
                  <p className="text-sm font-medium text-primary-700 dark:text-primary-300">
                    {campaignResult.count} {entityType} imported and added to campaign &ldquo;{campaignResult.name}&rdquo;
                  </p>
                </div>
              </div>
            )}
            {result.errors.length > 0 && (
              <div className="mt-4 max-h-32 overflow-y-auto text-left bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
                <p className="text-xs font-medium text-red-700 dark:text-red-400 mb-1">Errors ({result.errors.length})</p>
                <ul className="text-xs text-red-600 dark:text-red-300 space-y-0.5">
                  {result.errors.slice(0, 10).map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                  {result.errors.length > 10 && (
                    <li className="text-red-500">...and {result.errors.length - 10} more</li>
                  )}
                </ul>
              </div>
            )}
            <div className="mt-6">
              <Button variant="primary" onClick={handleClose}>
                Done
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
