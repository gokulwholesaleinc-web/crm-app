/**
 * Branding settings section for tenant admins.
 * Allows updating company name, colors, and logo URL.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { apiClient } from '../../../api/client';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { useTenant } from '../../../providers/TenantProvider';
import { SwatchIcon } from '@heroicons/react/24/outline';

interface BrandingFormData {
  company_name: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  logo_url: string;
  favicon_url: string;
  footer_text: string;
}

export function BrandingSection() {
  const { tenant, tenantSlug, refreshBranding } = useTenant();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<BrandingFormData>({
    company_name: '',
    primary_color: '#6366f1',
    secondary_color: '#8b5cf6',
    accent_color: '#22c55e',
    logo_url: '',
    favicon_url: '',
    footer_text: '',
  });

  // Show informational message when no tenant is configured
  if (!tenantSlug) {
    return (
      <Card>
        <CardHeader
          title="Branding"
          description="Customize your organization's appearance"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <SwatchIcon className="h-6 w-6 text-gray-400 dark:text-gray-500 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                White-label branding is available for tenant accounts.
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Once your account is associated with a tenant, you can customize your logo, colors, and company name here.
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    );
  }

  const startEditing = () => {
    setFormData({
      company_name: tenant?.company_name ?? '',
      primary_color: tenant?.primary_color ?? '#6366f1',
      secondary_color: tenant?.secondary_color ?? '#8b5cf6',
      accent_color: tenant?.accent_color ?? '#22c55e',
      logo_url: tenant?.logo_url ?? '',
      favicon_url: tenant?.favicon_url ?? '',
      footer_text: tenant?.footer_text ?? '',
    });
    setIsEditing(true);
  };

  const updateBranding = useMutation({
    mutationFn: async (data: Partial<BrandingFormData>) => {
      // We need the tenant ID. Fetch tenant details to get it.
      const tenantResp = await apiClient.get(`/api/tenants/config/${tenantSlug}`);
      // Use the slug to find the actual tenant - we need to call the settings
      // update via the config slug first to discover the tenant_id
      // Actually, we need to hit the settings endpoint with the tenant ID
      // Let's get the tenant by slug first
      const tenantListResp = await apiClient.get('/api/tenants', {
        params: { active_only: true },
      });
      const tenants = tenantListResp.data as Array<{ id: number; slug: string }>;
      const currentTenant = tenants.find((t) => t.slug === tenantSlug);
      if (!currentTenant) {
        throw { detail: 'Tenant not found' };
      }
      const response = await apiClient.patch(
        `/api/tenants/${currentTenant.id}/settings`,
        data
      );
      return response.data;
    },
    onSuccess: () => {
      toast.success('Branding updated successfully');
      setIsEditing(false);
      refreshBranding();
      queryClient.invalidateQueries({ queryKey: ['tenant', 'config'] });
    },
    onError: () => {
      toast.error('Failed to update branding');
    },
  });

  const handleSave = () => {
    updateBranding.mutate({
      company_name: formData.company_name || undefined,
      primary_color: formData.primary_color || undefined,
      secondary_color: formData.secondary_color || undefined,
      accent_color: formData.accent_color || undefined,
      logo_url: formData.logo_url || undefined,
      favicon_url: formData.favicon_url || undefined,
      footer_text: formData.footer_text || undefined,
    });
  };

  return (
    <Card>
      <CardHeader
        title="Branding"
        description="Customize your organization's appearance"
        action={
          !isEditing ? (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<SwatchIcon className="h-4 w-4" />}
              onClick={startEditing}
            >
              Edit Branding
            </Button>
          ) : undefined
        }
      />
      <CardBody className="p-4 sm:p-6">
        {!isEditing ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Company Name
              </label>
              <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                {tenant?.company_name || 'Not set'}
              </p>
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Logo URL
              </label>
              <p className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-all">
                {tenant?.logo_url || 'Not set'}
              </p>
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Primary Color
              </label>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className="inline-block h-5 w-5 rounded border border-gray-300 dark:border-gray-600"
                  style={{ backgroundColor: tenant?.primary_color ?? '#6366f1' }}
                  aria-hidden="true"
                />
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  {tenant?.primary_color ?? '#6366f1'}
                </span>
              </div>
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Secondary Color
              </label>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className="inline-block h-5 w-5 rounded border border-gray-300 dark:border-gray-600"
                  style={{ backgroundColor: tenant?.secondary_color ?? '#8b5cf6' }}
                  aria-hidden="true"
                />
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  {tenant?.secondary_color ?? '#8b5cf6'}
                </span>
              </div>
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Accent Color
              </label>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className="inline-block h-5 w-5 rounded border border-gray-300 dark:border-gray-600"
                  style={{ backgroundColor: tenant?.accent_color ?? '#22c55e' }}
                  aria-hidden="true"
                />
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  {tenant?.accent_color ?? '#22c55e'}
                </span>
              </div>
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Footer Text
              </label>
              <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                {tenant?.footer_text || 'Not set'}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="branding-company-name" className="form-label">
                  Company Name
                </label>
                <input
                  id="branding-company-name"
                  type="text"
                  className="form-input"
                  name="company_name"
                  autoComplete="organization"
                  value={formData.company_name}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, company_name: e.target.value }))
                  }
                  placeholder="Your company name..."
                />
              </div>
              <div>
                <label htmlFor="branding-logo-url" className="form-label">
                  Logo URL
                </label>
                <input
                  id="branding-logo-url"
                  type="url"
                  className="form-input"
                  name="logo_url"
                  autoComplete="url"
                  value={formData.logo_url}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, logo_url: e.target.value }))
                  }
                  placeholder="https://example.com/logo.png..."
                />
              </div>
              <div>
                <label htmlFor="branding-favicon-url" className="form-label">
                  Favicon URL
                </label>
                <input
                  id="branding-favicon-url"
                  type="url"
                  className="form-input"
                  name="favicon_url"
                  autoComplete="url"
                  value={formData.favicon_url}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, favicon_url: e.target.value }))
                  }
                  placeholder="https://example.com/favicon.ico..."
                />
              </div>
              <div>
                <label htmlFor="branding-footer-text" className="form-label">
                  Footer Text
                </label>
                <input
                  id="branding-footer-text"
                  type="text"
                  className="form-input"
                  name="footer_text"
                  autoComplete="off"
                  value={formData.footer_text}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, footer_text: e.target.value }))
                  }
                  placeholder="Footer text..."
                />
              </div>
            </div>

            {/* Color pickers */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label htmlFor="branding-primary-color" className="form-label">
                  Primary Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="branding-primary-color"
                    type="color"
                    className="h-10 w-14 cursor-pointer rounded border border-gray-300 dark:border-gray-600"
                    value={formData.primary_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, primary_color: e.target.value }))
                    }
                  />
                  <input
                    type="text"
                    className="form-input flex-1"
                    value={formData.primary_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, primary_color: e.target.value }))
                    }
                    aria-label="Primary color hex value"
                    spellCheck={false}
                    autoComplete="off"
                    placeholder="#6366f1"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="branding-secondary-color" className="form-label">
                  Secondary Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="branding-secondary-color"
                    type="color"
                    className="h-10 w-14 cursor-pointer rounded border border-gray-300 dark:border-gray-600"
                    value={formData.secondary_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, secondary_color: e.target.value }))
                    }
                  />
                  <input
                    type="text"
                    className="form-input flex-1"
                    value={formData.secondary_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, secondary_color: e.target.value }))
                    }
                    aria-label="Secondary color hex value"
                    spellCheck={false}
                    autoComplete="off"
                    placeholder="#8b5cf6"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="branding-accent-color" className="form-label">
                  Accent Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id="branding-accent-color"
                    type="color"
                    className="h-10 w-14 cursor-pointer rounded border border-gray-300 dark:border-gray-600"
                    value={formData.accent_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, accent_color: e.target.value }))
                    }
                  />
                  <input
                    type="text"
                    className="form-input flex-1"
                    value={formData.accent_color}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, accent_color: e.target.value }))
                    }
                    aria-label="Accent color hex value"
                    spellCheck={false}
                    autoComplete="off"
                    placeholder="#22c55e"
                  />
                </div>
              </div>
            </div>

            {/* Preview */}
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                Preview
              </p>
              <div className="flex items-center gap-3">
                <span
                  className="inline-block h-8 w-8 rounded-full"
                  style={{ backgroundColor: formData.primary_color }}
                  aria-label="Primary color preview"
                />
                <span
                  className="inline-block h-8 w-8 rounded-full"
                  style={{ backgroundColor: formData.secondary_color }}
                  aria-label="Secondary color preview"
                />
                <span
                  className="inline-block h-8 w-8 rounded-full"
                  style={{ backgroundColor: formData.accent_color }}
                  aria-label="Accent color preview"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300 ml-2">
                  {formData.company_name || 'Company Name'}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsEditing(false)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSave}
                disabled={updateBranding.isPending}
              >
                {updateBranding.isPending ? 'Saving...' : 'Save Branding'}
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
