/**
 * Branding settings section for tenant admins.
 * Allows updating company name, colors, logo URL, and favicon URL.
 */

import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { showSuccess, showError } from '../../../utils/toast';
import { apiClient } from '../../../api/client';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { useTenant } from '../../../providers/TenantProvider';
import { SwatchIcon } from '@heroicons/react/24/outline';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import { isValidHexColor, withAlpha } from '../../../utils/colorValidation';

interface BrandingFormData {
  company_name: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  bg_color_light: string;
  bg_color_dark: string;
  surface_color_light: string;
  surface_color_dark: string;
  logo_url: string;
  favicon_url: string;
  footer_text: string;
  // Email-wrapper extras (migration 034): tagline appears in the
  // branded-email header with gold `|` separators; the six social
  // URLs drive the dark-footer social-icon row.
  tagline: string;
  social_facebook_url: string;
  social_instagram_url: string;
  social_tiktok_url: string;
  social_linkedin_url: string;
  social_youtube_url: string;
  social_website_url: string;
}

// Field keys for the email-template section; the typed tuple drives
// the read-mode grid, edit-mode inputs, and seed loop. EmailField is
// derived from the tuple via ``as const`` so the union and the
// iteration order can't drift.
const EMAIL_FIELDS = [
  'tagline',
  'social_facebook_url',
  'social_instagram_url',
  'social_tiktok_url',
  'social_linkedin_url',
  'social_youtube_url',
  'social_website_url',
] as const;
type EmailField = (typeof EMAIL_FIELDS)[number];

const EMAIL_FIELD_LABELS: Record<EmailField, string> = {
  tagline: 'Email Tagline',
  social_facebook_url: 'Facebook URL',
  social_instagram_url: 'Instagram URL',
  social_tiktok_url: 'TikTok URL',
  social_linkedin_url: 'LinkedIn URL',
  social_youtube_url: 'YouTube URL',
  social_website_url: 'Website URL',
};

const EMAIL_FIELD_PLACEHOLDERS: Record<EmailField, string> = {
  tagline: 'ACCESSIBLE MEDIA | AUTHENTIC STORYTELLING | REAL RESULTS',
  social_facebook_url: 'https://facebook.com/your-page',
  social_instagram_url: 'https://instagram.com/your-handle',
  social_tiktok_url: 'https://tiktok.com/@your-handle',
  social_linkedin_url: 'https://linkedin.com/company/your-org',
  social_youtube_url: 'https://youtube.com/@your-channel',
  social_website_url: 'https://your-domain.com',
};

const NEUTRAL_GRAY = '#94a3b8';

// Default values for every color field. Keyed by the form-data key so
// seeding, dirty-check, read-mode fallback, and the picker placeholder
// all read from the same source. Backend constants in
// `src/core/constants.py` must match; tests cover both ends.
type ColorField =
  | 'primary_color'
  | 'secondary_color'
  | 'accent_color'
  | 'bg_color_light'
  | 'bg_color_dark'
  | 'surface_color_light'
  | 'surface_color_dark';

const COLOR_DEFAULTS: Record<ColorField, string> = {
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  bg_color_light: '#f9fafb',
  bg_color_dark: '#111827',
  surface_color_light: '#ffffff',
  surface_color_dark: '#1f2937',
};

type PaletteField = 'primary_color' | 'secondary_color' | 'accent_color';
type SurfaceField =
  | 'bg_color_light'
  | 'bg_color_dark'
  | 'surface_color_light'
  | 'surface_color_dark';

const PALETTE_FIELDS: readonly PaletteField[] = [
  'primary_color',
  'secondary_color',
  'accent_color',
];
const SURFACE_FIELDS: readonly SurfaceField[] = [
  'bg_color_light',
  'bg_color_dark',
  'surface_color_light',
  'surface_color_dark',
];

const COLOR_LABELS: Record<ColorField, string> = {
  primary_color: 'Primary Color',
  secondary_color: 'Secondary Color',
  accent_color: 'Accent Color',
  bg_color_light: 'Light Mode Background',
  bg_color_dark: 'Dark Mode Background',
  surface_color_light: 'Light Mode Card Surface',
  surface_color_dark: 'Dark Mode Card Surface',
};

const PALETTE_HINTS: Record<PaletteField, string> = {
  primary_color:
    'Used for buttons, links, active navigation, focus rings, and chart highlights.',
  secondary_color: 'Used as a supporting accent in chart series and category badges.',
  accent_color: 'Used for callouts, accent badges, and the third chart series color.',
};

// Loose shape so we don't have to import the full TenantConfig type just
// for typing fallbacks; color fields and the email-wrapper extras share
// the same `string | null | undefined` shape from the public config.
type TenantConfigLike = Partial<Record<ColorField, string | null | undefined>>
  & Partial<Record<EmailField, string | null | undefined>>
  & {
    company_name?: string | null;
    logo_url?: string | null;
    favicon_url?: string | null;
    footer_text?: string | null;
  };

function tenantColor(tenant: TenantConfigLike | null | undefined, field: ColorField): string {
  return tenant?.[field] ?? COLOR_DEFAULTS[field];
}

function safeColor(value: string, fallback: string): string {
  if (isValidHexColor(value)) return value;
  if (isValidHexColor(fallback)) return fallback;
  return NEUTRAL_GRAY;
}

interface ColorReadoutProps {
  label: string;
  value: string;
}

function ColorReadout({ label, value }: ColorReadoutProps) {
  return (
    <div>
      <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
        {label}
      </label>
      <div className="mt-1 flex items-center gap-2">
        <span
          className="inline-block h-5 w-5 rounded border border-gray-300 dark:border-gray-600"
          style={{ backgroundColor: value }}
          aria-hidden="true"
        />
        <span className="text-sm text-gray-900 dark:text-gray-100">{value}</span>
      </div>
    </div>
  );
}

interface ColorPickerProps {
  field: ColorField;
  label: string;
  value: string;
  onChange: (next: string) => void;
  hint?: string;
}

function ColorPicker({ field, label, value, onChange, hint }: ColorPickerProps) {
  const inputId = `branding-${field.replace(/_/g, '-')}`;
  // Treat empty as "leave default" — only mark non-empty bad input as invalid
  // so the field doesn't scream red the moment the user clears it.
  const isInvalid = value.length > 0 && !isValidHexColor(value);
  const errorId = `${inputId}-error`;
  return (
    <div>
      <label htmlFor={inputId} className="form-label">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <input
          id={inputId}
          type="color"
          className="h-10 w-14 cursor-pointer rounded border border-gray-300 dark:border-gray-600"
          // <input type="color"> only accepts strict #rrggbb; feed it the
          // backend default while the user is editing an invalid string so
          // the swatch doesn't snap to black.
          value={isInvalid ? COLOR_DEFAULTS[field] : value}
          onChange={(e) => onChange(e.target.value)}
        />
        <input
          type="text"
          className={`form-input flex-1 ${isInvalid ? 'border-red-500 dark:border-red-400 focus:ring-red-500 focus:border-red-500' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={`${label} hex value`}
          aria-invalid={isInvalid || undefined}
          aria-describedby={isInvalid ? errorId : undefined}
          spellCheck={false}
          autoComplete="off"
          placeholder={COLOR_DEFAULTS[field]}
        />
      </div>
      {isInvalid ? (
        <p id={errorId} className="mt-1 text-xs text-red-500 dark:text-red-400" aria-live="polite">
          Invalid hex — must be #rgb, #rrggbb, or #rrggbbaa.
        </p>
      ) : hint ? (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{hint}</p>
      ) : null}
    </div>
  );
}

export function BrandingSection() {
  const { tenant, tenantSlug, refreshBranding } = useTenant();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [logoPreviewError, setLogoPreviewError] = useState(false);
  const [faviconPreviewError, setFaviconPreviewError] = useState(false);
  const [formData, setFormData] = useState<BrandingFormData>(() => ({
    company_name: '',
    logo_url: '',
    favicon_url: '',
    footer_text: '',
    ...COLOR_DEFAULTS,
    ...(Object.fromEntries(EMAIL_FIELDS.map((f) => [f, ''])) as Record<EmailField, string>),
  }));

  const seededFromTenant = useMemo<BrandingFormData>(() => {
    const colors = Object.fromEntries(
      (Object.keys(COLOR_DEFAULTS) as ColorField[]).map((f) => [f, tenantColor(tenant, f)])
    ) as Record<ColorField, string>;
    const emailFields = Object.fromEntries(
      EMAIL_FIELDS.map((f) => [f, tenant?.[f] ?? ''])
    ) as Record<EmailField, string>;
    return {
      ...colors,
      ...emailFields,
      company_name: tenant?.company_name ?? '',
      logo_url: tenant?.logo_url ?? '',
      favicon_url: tenant?.favicon_url ?? '',
      footer_text: tenant?.footer_text ?? '',
    };
  }, [tenant]);

  // Real dirty check: only warn on unload when the form's actually been
  // mutated, not just because the user clicked Edit and the form was
  // seeded with server values.
  const isDirty = useMemo(() => {
    if (!isEditing) return false;
    return (Object.keys(seededFromTenant) as Array<keyof BrandingFormData>).some(
      (key) => formData[key] !== seededFromTenant[key]
    );
  }, [isEditing, formData, seededFromTenant]);

  useUnsavedChangesWarning(isDirty);

  // Block submission if any color field carries garbage. Backend rejects
  // bad hex with a 422, but blocking here keeps the user in the editor
  // with the offending field highlighted instead of bouncing through a
  // toast and losing their other unsaved edits.
  const invalidColorFields = useMemo<ColorField[]>(() => {
    return (Object.keys(COLOR_DEFAULTS) as ColorField[]).filter((field) => {
      const value = formData[field];
      return value.length > 0 && !isValidHexColor(value);
    });
  }, [formData]);
  const hasInvalidColor = invalidColorFields.length > 0;

  const startEditing = () => {
    setFormData(seededFromTenant);
    setLogoPreviewError(false);
    setFaviconPreviewError(false);
    setIsEditing(true);
  };

  const updateBranding = useMutation({
    mutationFn: async (data: Partial<BrandingFormData>) => {
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
      showSuccess('Branding updated successfully');
      setIsEditing(false);
      refreshBranding();
      queryClient.invalidateQueries({ queryKey: ['tenant', 'config', tenantSlug] });
    },
    onError: (error: unknown) => {
      // Surface the server's validation message verbatim when present so
      // the admin learns which field is bad. Pydantic returns either a
      // plain string detail (older paths) or an array of {loc, msg, ...}
      // entries (validator failures); both are common enough to warrant
      // explicit handling. Unknown shapes fall back to a generic toast.
      const detail = (error as { response?: { data?: { detail?: unknown } } } | undefined)
        ?.response?.data?.detail;
      let message = 'Failed to update branding';
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: unknown; loc?: unknown[] };
        const loc = Array.isArray(first?.loc) ? first.loc.filter((p) => p !== 'body').join('.') : '';
        const msg = typeof first?.msg === 'string' ? first.msg : '';
        if (msg) message = loc ? `${loc}: ${msg}` : msg;
      }
      showError(message);
    },
  });

  const handleSave = () => {
    if (hasInvalidColor) {
      const labels = invalidColorFields.map((f) => COLOR_LABELS[f]).join(', ');
      showError(`Fix invalid hex in: ${labels}`);
      return;
    }
    // Strip empty strings so the backend keeps its defaults instead of
    // overwriting them with "". Object spread preserves explicit field
    // names for type-checking against TenantSettingsUpdate.
    const payload: Partial<BrandingFormData> = {};
    (Object.keys(formData) as Array<keyof BrandingFormData>).forEach((key) => {
      const value = formData[key];
      if (value) payload[key] = value;
    });
    updateBranding.mutate(payload);
  };

  // Stage the documented defaults into formData so the admin sees the reset
  // reflected in pickers + preview and can review before saving. Cancel still
  // reverts; only Save persists.
  const handleResetColors = () => {
    setFormData((prev) => ({ ...prev, ...COLOR_DEFAULTS }));
    showSuccess('Colors reset to defaults — click Save to apply');
  };

  // Show informational message when no tenant is configured.
  // Placed after all hooks to comply with rules-of-hooks.
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
              // Block Edit until tenant has loaded — otherwise startEditing
              // seeds formData with hardcoded defaults, then a delayed tenant
              // refetch flips isDirty true and fires a spurious beforeunload.
              disabled={!tenant}
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
                Logo
              </label>
              {tenant?.logo_url ? (
                <div className="mt-1 flex items-center gap-3">
                  <img
                    src={tenant.logo_url}
                    alt={tenant.company_name || 'Logo'}
                    width={40}
                    height={40}
                    className="h-10 w-10 rounded-lg object-contain border border-gray-200 dark:border-gray-600"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400 break-all">{tenant.logo_url}</span>
                </div>
              ) : (
                <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">Not set</p>
              )}
            </div>
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Favicon
              </label>
              {tenant?.favicon_url ? (
                <div className="mt-1 flex items-center gap-3">
                  <img
                    src={tenant.favicon_url}
                    alt="Favicon"
                    width={20}
                    height={20}
                    className="h-5 w-5 object-contain"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400 break-all">{tenant.favicon_url}</span>
                </div>
              ) : (
                <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">Not set</p>
              )}
            </div>
            {([...PALETTE_FIELDS, ...SURFACE_FIELDS] as ColorField[]).map((field) => (
              <ColorReadout
                key={field}
                label={COLOR_LABELS[field]}
                value={tenantColor(tenant, field)}
              />
            ))}
            <div>
              <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                Footer Text
              </label>
              <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                {tenant?.footer_text || 'Not set'}
              </p>
            </div>
            {EMAIL_FIELDS.map((field) => (
              <div key={field}>
                <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                  {EMAIL_FIELD_LABELS[field]}
                </label>
                <p className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-all">
                  {tenant?.[field] || 'Not set'}
                </p>
              </div>
            ))}
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
                  onChange={(e) => {
                    setFormData((prev) => ({ ...prev, logo_url: e.target.value }));
                    setLogoPreviewError(false);
                  }}
                  placeholder="https://example.com/logo.png..."
                />
                {formData.logo_url && (
                  <div className="mt-2">
                    {!logoPreviewError ? (
                      <img
                        src={formData.logo_url}
                        alt="Logo preview"
                        width={40}
                        height={40}
                        className="h-10 w-10 rounded-lg object-contain border border-gray-200 dark:border-gray-600"
                        onError={() => setLogoPreviewError(true)}
                      />
                    ) : (
                      <p className="text-xs text-red-500 dark:text-red-400">Failed to load image</p>
                    )}
                  </div>
                )}
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
                  onChange={(e) => {
                    setFormData((prev) => ({ ...prev, favicon_url: e.target.value }));
                    setFaviconPreviewError(false);
                  }}
                  placeholder="https://example.com/favicon.ico..."
                />
                {formData.favicon_url && (
                  <div className="mt-2">
                    {!faviconPreviewError ? (
                      <img
                        src={formData.favicon_url}
                        alt="Favicon preview"
                        width={20}
                        height={20}
                        className="h-5 w-5 object-contain border border-gray-200 dark:border-gray-600 rounded"
                        onError={() => setFaviconPreviewError(true)}
                      />
                    ) : (
                      <p className="text-xs text-red-500 dark:text-red-400">Failed to load image</p>
                    )}
                  </div>
                )}
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
              {PALETTE_FIELDS.map((field) => (
                <ColorPicker
                  key={field}
                  field={field}
                  label={COLOR_LABELS[field]}
                  value={formData[field]}
                  onChange={(next) => setFormData((prev) => ({ ...prev, [field]: next }))}
                  hint={PALETTE_HINTS[field]}
                />
              ))}
            </div>

            {/* Background + surface color pickers (light + dark) */}
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Background &amp; Surface Colors
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Page background and card surface for both light and dark modes. The default dark
                background reads slightly blue (gray-900) — pick a flatter hex like {'‘'}#0a0a0a{'’'}
                if you want a true black.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {SURFACE_FIELDS.map((field) => (
                  <ColorPicker
                    key={field}
                    field={field}
                    label={COLOR_LABELS[field]}
                    value={formData[field]}
                    onChange={(next) => setFormData((prev) => ({ ...prev, [field]: next }))}
                  />
                ))}
              </div>
            </div>

            {/* Email template (tagline + footer socials) */}
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Email Template
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Tagline renders in the branded-email header under the logo
                with gold <code>|</code> separators. Social URLs appear as a
                row of circles in the dark email footer; leave any blank to
                omit that platform.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {EMAIL_FIELDS.map((field) => {
                  const inputId = `branding-${field.replace(/_/g, '-')}`;
                  const isUrl = field !== 'tagline';
                  return (
                    <div key={field}>
                      <label htmlFor={inputId} className="form-label">
                        {EMAIL_FIELD_LABELS[field]}
                      </label>
                      <input
                        id={inputId}
                        type={isUrl ? 'url' : 'text'}
                        className="form-input"
                        name={field}
                        autoComplete={isUrl ? 'url' : 'off'}
                        spellCheck={false}
                        value={formData[field]}
                        onChange={(e) =>
                          setFormData((prev) => ({ ...prev, [field]: e.target.value }))
                        }
                        placeholder={EMAIL_FIELD_PLACEHOLDERS[field]}
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Preview */}
            {(() => {
              const effective = (field: ColorField) =>
                safeColor(formData[field], tenantColor(tenant, field));
              const primary = effective('primary_color');
              const secondary = effective('secondary_color');
              const accent = effective('accent_color');
              const bgLight = effective('bg_color_light');
              const bgDark = effective('bg_color_dark');
              const surfaceLight = effective('surface_color_light');
              const surfaceDark = effective('surface_color_dark');
              const swatches: Array<{ label: string; value: string; raw: string }> = [
                { label: 'Primary', value: primary, raw: formData.primary_color },
                { label: 'Secondary', value: secondary, raw: formData.secondary_color },
                { label: 'Accent', value: accent, raw: formData.accent_color },
              ];
              const bars = [
                { color: primary, width: '90%' },
                { color: secondary, width: '70%' },
                { color: accent, width: '55%' },
                { color: NEUTRAL_GRAY, width: '35%' },
              ];
              return (
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      Preview
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      Live — reflects unsaved values
                    </p>
                  </div>

                  {/* Header strip */}
                  <div
                    className="flex items-center justify-between px-4 py-3 rounded-lg"
                    style={{ backgroundColor: primary }}
                  >
                    <div className="flex items-center gap-3">
                      {formData.logo_url && !logoPreviewError ? (
                        <img
                          src={formData.logo_url}
                          alt=""
                          width={28}
                          height={28}
                          className="h-7 w-7 rounded object-contain bg-white/20"
                          onError={() => setLogoPreviewError(true)}
                        />
                      ) : null}
                      <span className="text-sm font-semibold text-white">
                        {formData.company_name || 'Company Name'}
                      </span>
                    </div>
                    <span
                      className="inline-block px-3 py-1 rounded-full text-xs font-medium text-white"
                      style={{ backgroundColor: accent }}
                    >
                      Proposal
                    </span>
                  </div>

                  {/* Swatch cards */}
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {swatches.map((s) => (
                      <div
                        key={s.label}
                        className="rounded-md border border-gray-200 dark:border-gray-700 p-3 flex items-center gap-3"
                      >
                        <span
                          className="inline-block h-16 w-16 rounded border border-gray-300 dark:border-gray-600 flex-shrink-0"
                          style={{ backgroundColor: s.value }}
                          aria-label={`${s.label} color swatch`}
                        />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {s.label}
                          </p>
                          <p className="text-xs font-mono text-gray-500 dark:text-gray-400 truncate">
                            {s.raw || s.value}
                          </p>
                          {s.raw && !isValidHexColor(s.raw) && (
                            <p className="text-xs text-red-500 dark:text-red-400">
                              Invalid hex — using fallback
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Button row */}
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      className="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
                      style={{ backgroundColor: primary }}
                      onClick={(e) => e.preventDefault()}
                    >
                      Primary Button
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium bg-transparent border focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
                      style={{ borderColor: secondary, color: secondary }}
                      onClick={(e) => e.preventDefault()}
                    >
                      Secondary Button
                    </button>
                  </div>

                  {/* Badge row */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-medium"
                      style={{ backgroundColor: withAlpha(primary, '1a'), color: primary }}
                    >
                      Primary
                    </span>
                    <span
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-medium"
                      style={{ backgroundColor: withAlpha(secondary, '1a'), color: secondary }}
                    >
                      Secondary
                    </span>
                    <span
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-medium"
                      style={{ backgroundColor: withAlpha(accent, '1a'), color: accent }}
                    >
                      Accent
                    </span>
                  </div>

                  {/* Mock bar chart */}
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                      Sample chart
                    </p>
                    <div className="space-y-1.5" role="img" aria-label="Sample chart preview">
                      {bars.map((b, i) => (
                        <div key={i} className="h-3 w-full bg-gray-100 dark:bg-gray-800 rounded">
                          <div
                            className="h-full rounded"
                            style={{ width: b.width, backgroundColor: b.color }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Light + dark mode page mockups */}
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                      Page background &amp; cards
                    </p>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div
                        className="rounded-md border border-gray-300 p-3 space-y-2"
                        style={{ backgroundColor: bgLight }}
                        aria-label="Light mode preview"
                      >
                        <p className="text-[10px] font-medium uppercase tracking-wide text-gray-500">
                          Light mode
                        </p>
                        <div
                          className="rounded shadow-sm border border-gray-200 px-3 py-2"
                          style={{ backgroundColor: surfaceLight }}
                        >
                          <p className="text-xs font-semibold" style={{ color: '#111827' }}>
                            Card title
                          </p>
                          <p className="text-[11px]" style={{ color: '#4b5563' }}>
                            Card body content
                          </p>
                        </div>
                      </div>
                      <div
                        className="rounded-md border border-gray-700 p-3 space-y-2"
                        style={{ backgroundColor: bgDark }}
                        aria-label="Dark mode preview"
                      >
                        <p className="text-[10px] font-medium uppercase tracking-wide" style={{ color: '#9ca3af' }}>
                          Dark mode
                        </p>
                        <div
                          className="rounded shadow-sm border border-gray-700 px-3 py-2"
                          style={{ backgroundColor: surfaceDark }}
                        >
                          <p className="text-xs font-semibold" style={{ color: '#f3f4f6' }}>
                            Card title
                          </p>
                          <p className="text-[11px]" style={{ color: '#d1d5db' }}>
                            Card body content
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Actions */}
            <div className="flex flex-col-reverse sm:flex-row sm:justify-between gap-3 pt-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleResetColors}
                title="Restore the seven color fields to their original defaults"
              >
                Reset Colors to Defaults
              </Button>
              <div className="flex justify-end gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => { setIsEditing(false); setLogoPreviewError(false); setFaviconPreviewError(false); }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSave}
                  disabled={updateBranding.isPending || hasInvalidColor}
                  title={hasInvalidColor ? 'Fix invalid hex colors before saving' : undefined}
                >
                  {updateBranding.isPending ? 'Saving...' : 'Save Branding'}
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
