/**
 * Import/Export page for CSV data import and export operations
 */

import { useState, useRef } from 'react';
import {
  ArrowUpTrayIcon,
  ArrowDownTrayIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
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
  downloadBlob,
  generateExportFilename,
} from '../../api/importExport';
import type { ImportResult, ImportExportEntityType } from '../../types';

type OperationStatus = 'idle' | 'loading' | 'success' | 'error';

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
    <div className="bg-white rounded-lg shadow-sm border p-5">
      <div className="flex items-start gap-3">
        <div className="p-2 bg-blue-50 rounded-lg">
          <ArrowDownTrayIcon className="h-6 w-6 text-blue-600" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          <p className="text-sm text-gray-500 mt-1">{description}</p>
          <div className="flex flex-col sm:flex-row gap-2 mt-3">
            <Button
              size="sm"
              onClick={onExport}
              isLoading={isExporting}
              leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
            >
              Export CSV
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onTemplate}
              leftIcon={<DocumentTextIcon className="h-4 w-4" />}
            >
              Download Template
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface ImportSectionProps {
  entityType: ImportExportEntityType;
  label: string;
  onImport: (file: File) => Promise<void>;
  status: OperationStatus;
  result: ImportResult | null;
  error: string | null;
}

function ImportSection({ entityType, label, onImport, status, result, error }: ImportSectionProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await onImport(file);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border p-5">
      <div className="flex items-start gap-3">
        <div className="p-2 bg-green-50 rounded-lg">
          <ArrowUpTrayIcon className="h-6 w-6 text-green-600" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900">Import {label}</h3>
          <p className="text-sm text-gray-500 mt-1">
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
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => fileInputRef.current?.click()}
              isLoading={status === 'loading'}
              leftIcon={<ArrowUpTrayIcon className="h-4 w-4" />}
            >
              Choose CSV File
            </Button>
          </div>

          {/* Result */}
          {status === 'success' && result && (
            <div className="mt-3 p-3 bg-green-50 rounded-md">
              <div className="flex items-center gap-2">
                <CheckCircleIcon className="h-5 w-5 text-green-600" />
                <span className="text-sm font-medium text-green-800">
                  Successfully imported {result.imported_count} record{result.imported_count !== 1 ? 's' : ''}
                </span>
              </div>
              {result.errors.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-medium text-yellow-700">
                    {result.errors.length} warning{result.errors.length !== 1 ? 's' : ''}:
                  </p>
                  <ul className="mt-1 text-xs text-yellow-600 list-disc list-inside max-h-24 overflow-y-auto">
                    {result.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {status === 'error' && error && (
            <div className="mt-3 p-3 bg-red-50 rounded-md">
              <div className="flex items-center gap-2">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-600" />
                <span className="text-sm font-medium text-red-800">{error}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ImportExportPage() {
  const [exportingEntity, setExportingEntity] = useState<string | null>(null);

  const [importStates, setImportStates] = useState<
    Record<ImportExportEntityType, { status: OperationStatus; result: ImportResult | null; error: string | null }>
  >({
    contacts: { status: 'idle', result: null, error: null },
    companies: { status: 'idle', result: null, error: null },
    leads: { status: 'idle', result: null, error: null },
  });

  const handleExport = async (entityType: ImportExportEntityType) => {
    setExportingEntity(entityType);
    try {
      let blob: Blob;
      switch (entityType) {
        case 'contacts':
          blob = await exportContacts();
          break;
        case 'companies':
          blob = await exportCompanies();
          break;
        case 'leads':
          blob = await exportLeads();
          break;
      }
      downloadBlob(blob, generateExportFilename(entityType));
    } catch (error) {
      console.error(`Failed to export ${entityType}:`, error);
    } finally {
      setExportingEntity(null);
    }
  };

  const handleTemplate = async (entityType: ImportExportEntityType) => {
    try {
      const blob = await getTemplate(entityType);
      downloadBlob(blob, `${entityType}_template.csv`);
    } catch (error) {
      console.error(`Failed to download template for ${entityType}:`, error);
    }
  };

  const handleImport = async (entityType: ImportExportEntityType, file: File) => {
    setImportStates((prev) => ({
      ...prev,
      [entityType]: { status: 'loading', result: null, error: null },
    }));

    try {
      let result: ImportResult;
      switch (entityType) {
        case 'contacts':
          result = await importContacts(file);
          break;
        case 'companies':
          result = await importCompanies(file);
          break;
        case 'leads':
          result = await importLeads(file);
          break;
      }
      setImportStates((prev) => ({
        ...prev,
        [entityType]: { status: 'success', result, error: null },
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Import failed';
      setImportStates((prev) => ({
        ...prev,
        [entityType]: { status: 'error', result: null, error: message },
      }));
    }
  };

  const entityConfigs: { type: ImportExportEntityType; label: string; description: string }[] = [
    { type: 'contacts', label: 'Contacts', description: 'Export all contacts as a CSV file' },
    { type: 'companies', label: 'Companies', description: 'Export all companies as a CSV file' },
    { type: 'leads', label: 'Leads', description: 'Export all leads as a CSV file' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Import / Export</h1>
        <p className="text-sm text-gray-500 mt-1">
          Import and export your CRM data as CSV files
        </p>
      </div>

      {/* Export Section */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Export Data</h2>
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
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Import Data</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {entityConfigs.map((config) => (
            <ImportSection
              key={config.type}
              entityType={config.type}
              label={config.label}
              onImport={(file) => handleImport(config.type, file)}
              status={importStates[config.type].status}
              result={importStates[config.type].result}
              error={importStates[config.type].error}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default ImportExportPage;
