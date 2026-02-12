/**
 * Tenant context provider for white-label branding.
 *
 * Fetches tenant branding config and applies CSS custom properties,
 * document title, and favicon updates.
 */

import {
  createContext,
  useContext,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';

// --- Types ---

export interface TenantConfig {
  tenant_slug: string;
  company_name: string | null;
  logo_url: string | null;
  favicon_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  footer_text: string | null;
  privacy_policy_url: string | null;
  terms_of_service_url: string | null;
  default_language: string;
  date_format: string;
  custom_css: string | null;
}

interface TenantContextValue {
  tenant: TenantConfig | null;
  tenantSlug: string | null;
  isLoading: boolean;
  setTenantSlug: (slug: string | null) => void;
  refreshBranding: () => void;
}

// --- Storage Keys ---

const TENANT_SLUG_KEY = 'crm_tenant_slug:v1';

// --- Context ---

const TenantContext = createContext<TenantContextValue>({
  tenant: null,
  tenantSlug: null,
  isLoading: false,
  setTenantSlug: () => {},
  refreshBranding: () => {},
});

// --- Helper: hex to RGB ---

function hexToRgb(hex: string): string {
  const cleaned = hex.replace('#', '');
  const r = parseInt(cleaned.substring(0, 2), 16);
  const g = parseInt(cleaned.substring(2, 4), 16);
  const b = parseInt(cleaned.substring(4, 6), 16);
  if (isNaN(r) || isNaN(g) || isNaN(b)) {
    return '';
  }
  return `${r} ${g} ${b}`;
}

// --- Helper: apply CSS custom properties ---

function applyBrandingToDOM(config: TenantConfig | null) {
  const root = document.documentElement;

  if (!config) {
    // Reset to defaults
    root.style.removeProperty('--color-primary');
    root.style.removeProperty('--color-secondary');
    root.style.removeProperty('--color-accent');
    root.style.removeProperty('--brand-primary');
    root.style.removeProperty('--brand-secondary');
    root.style.removeProperty('--brand-accent');
    return;
  }

  // Set RGB values for Tailwind-compatible usage
  const primaryRgb = hexToRgb(config.primary_color);
  const secondaryRgb = hexToRgb(config.secondary_color);
  const accentRgb = hexToRgb(config.accent_color);

  if (primaryRgb) root.style.setProperty('--color-primary', primaryRgb);
  if (secondaryRgb) root.style.setProperty('--color-secondary', secondaryRgb);
  if (accentRgb) root.style.setProperty('--color-accent', accentRgb);

  // Set hex values for direct usage
  root.style.setProperty('--brand-primary', config.primary_color);
  root.style.setProperty('--brand-secondary', config.secondary_color);
  root.style.setProperty('--brand-accent', config.accent_color);

  // Update document title
  if (config.company_name) {
    document.title = `${config.company_name} - CRM`;
  }

  // Update favicon
  if (config.favicon_url) {
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) {
      link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.href = config.favicon_url;
  }

  // Inject custom CSS
  const existingStyle = document.getElementById('tenant-custom-css');
  if (existingStyle) {
    existingStyle.remove();
  }
  if (config.custom_css) {
    const style = document.createElement('style');
    style.id = 'tenant-custom-css';
    style.textContent = config.custom_css;
    document.head.appendChild(style);
  }
}

// --- Fetch function ---

async function fetchTenantConfig(slug: string): Promise<TenantConfig> {
  const response = await apiClient.get<TenantConfig>(
    `/api/tenants/config/${slug}`
  );
  return response.data;
}

// --- Provider Component ---

interface TenantProviderProps {
  children: ReactNode;
}

export function TenantProvider({ children }: TenantProviderProps) {
  // Read slug from localStorage on mount
  const storedSlug = (() => {
    try {
      return localStorage.getItem(TENANT_SLUG_KEY);
    } catch {
      return null;
    }
  })();

  const queryClient = useQueryClient();

  const { data: tenant, isLoading } = useQuery({
    queryKey: ['tenant', 'config', storedSlug],
    queryFn: () => fetchTenantConfig(storedSlug!),
    enabled: !!storedSlug,
    staleTime: 10 * 60 * 1000, // 10 minutes
    gcTime: 30 * 60 * 1000,
    retry: 1,
  });

  // Apply branding when tenant config changes
  useEffect(() => {
    applyBrandingToDOM(tenant ?? null);
  }, [tenant]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      applyBrandingToDOM(null);
      const existingStyle = document.getElementById('tenant-custom-css');
      if (existingStyle) existingStyle.remove();
    };
  }, []);

  const setTenantSlug = useCallback(
    (slug: string | null) => {
      try {
        if (slug) {
          localStorage.setItem(TENANT_SLUG_KEY, slug);
        } else {
          localStorage.removeItem(TENANT_SLUG_KEY);
          applyBrandingToDOM(null);
        }
      } catch {
        // localStorage not available
      }
      // Invalidate the query to refetch
      queryClient.invalidateQueries({ queryKey: ['tenant', 'config'] });
    },
    [queryClient]
  );

  const refreshBranding = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['tenant', 'config'] });
  }, [queryClient]);

  const contextValue: TenantContextValue = {
    tenant: tenant ?? null,
    tenantSlug: storedSlug,
    isLoading,
    setTenantSlug,
    refreshBranding,
  };

  return (
    <TenantContext.Provider value={contextValue}>
      {children}
    </TenantContext.Provider>
  );
}

// --- Hook ---

export function useTenant() {
  return useContext(TenantContext);
}

// --- Storage helper for login flow ---

export function setTenantSlugOnLogin(slug: string) {
  try {
    localStorage.setItem(TENANT_SLUG_KEY, slug);
  } catch {
    // localStorage not available
  }
}

export function clearTenantSlugOnLogout() {
  try {
    localStorage.removeItem(TENANT_SLUG_KEY);
  } catch {
    // localStorage not available
  }
}
