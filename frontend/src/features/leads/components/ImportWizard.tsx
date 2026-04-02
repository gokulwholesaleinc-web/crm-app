/**
 * Multi-step import wizard with column mapping for leads, contacts, and companies.
 * Steps: 1) Upload CSV  2) Map columns  3) Preview & confirm  4) Import results
 */

import { useState, useCallback, useMemo } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Modal } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { previewImport, importWithMapping } from '../../../api/importExport';
import type { ImportPreview } from '../../../types';
import {
  ArrowUpTrayIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

type EntityType = 'leads' | 'contacts' | 'companies';

interface ImportWizardProps {
  isOpen: boolean;
  onClose: () => void;
  entityType: EntityType;
  onSuccess?: () => void;
}

type WizardStep = 'upload' | 'mapping' | 'preview' | 'result';

interface ImportResult {
  success: boolean;
  imported_count: number;
  errors: string[];
  duplicates_skipped: number;
}

export function ImportWizard({ isOpen, onClose, entityType, onSuccess }: ImportWizardProps) {
  const [step, setStep] = useState<WizardStep>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const reset = useCallback(() => {
    setStep('upload');
    setFile(null);
    setPreview(null);
    setColumnMapping({});
    setResult(null);
  }, []);

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
    onSuccess: (data) => {
      setResult(data);
      setStep('result');
      if (data.success && data.imported_count > 0) {
        onSuccess?.();
      }
    },
    onError: () => {
      toast.error('Import failed');
    },
  });

  const mappedFieldCount = useMemo(() => {
    return Object.values(columnMapping).filter(v => v && v !== 'skip').length;
  }, [columnMapping]);

  const stepTitle: Record<WizardStep, string> = {
    upload: `Import ${entityType}`,
    mapping: 'Map Columns',
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
          {(['upload', 'mapping', 'preview', 'result'] as WizardStep[]).map((s, i) => {
            const currentIndex = ['upload', 'mapping', 'preview', 'result'].indexOf(step);
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

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => { setStep('upload'); setFile(null); setPreview(null); }}
                leftIcon={<ArrowLeftIcon className="h-4 w-4" />}>
                Back
              </Button>
              <Button variant="primary" onClick={() => setStep('preview')}
                leftIcon={<ArrowRightIcon className="h-4 w-4" />}
                disabled={mappedFieldCount === 0}>
                Preview
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Preview */}
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

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setStep('mapping')}
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

        {/* Step 4: Results */}
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
