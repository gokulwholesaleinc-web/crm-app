import { apiClient } from './client';

export interface CompanyMetaData {
  id: number;
  company_id: number;
  page_id: string | null;
  page_name: string | null;
  followers_count: number | null;
  likes_count: number | null;
  category: string | null;
  about: string | null;
  website: string | null;
  raw_json: Record<string, unknown> | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export const getCompanyMeta = async (companyId: number): Promise<CompanyMetaData> => {
  const response = await apiClient.get<CompanyMetaData>(`/api/meta/companies/${companyId}`);
  return response.data;
};

export const syncCompanyMeta = async (companyId: number, pageId: string): Promise<CompanyMetaData> => {
  const response = await apiClient.post<CompanyMetaData>(`/api/meta/companies/${companyId}/sync`, { page_id: pageId });
  return response.data;
};

export const exportMetaCsv = async (companyId: number): Promise<void> => {
  const response = await apiClient.get(`/api/meta/companies/${companyId}/export-csv`, {
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `meta-company-${companyId}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
