import type { Contact, ContactCreate, ContactUpdate } from '../../../types';

export interface ContactFormData {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company_id?: number | null;
  jobTitle?: string;
  salesCode?: string;
  address?: string;
  city?: string;
  state?: string;
  zipCode?: string;
  country?: string;
  notes?: string;
  tags?: string[];
}

export function contactFormDataToCreate(data: ContactFormData): ContactCreate {
  return {
    first_name: data.firstName,
    last_name: data.lastName,
    email: data.email || undefined,
    phone: data.phone || undefined,
    job_title: data.jobTitle || undefined,
    company_id: data.company_id ?? undefined,
    sales_code: data.salesCode || undefined,
    address_line1: data.address || undefined,
    city: data.city || undefined,
    state: data.state || undefined,
    postal_code: data.zipCode || undefined,
    country: data.country || undefined,
    description: data.notes || undefined,
    status: 'active',
  };
}

export function contactFormDataToUpdate(data: ContactFormData): ContactUpdate {
  return {
    first_name: data.firstName,
    last_name: data.lastName,
    email: data.email || undefined,
    phone: data.phone || undefined,
    job_title: data.jobTitle || undefined,
    company_id: data.company_id ?? undefined,
    sales_code: data.salesCode || undefined,
    address_line1: data.address || undefined,
    city: data.city || undefined,
    state: data.state || undefined,
    postal_code: data.zipCode || undefined,
    country: data.country || undefined,
    description: data.notes || undefined,
  };
}

export function contactToFormData(contact: Contact): Partial<ContactFormData> {
  return {
    firstName: contact.first_name,
    lastName: contact.last_name,
    email: contact.email || '',
    phone: contact.phone || '',
    jobTitle: contact.job_title || '',
    company_id: contact.company_id ?? null,
    salesCode: contact.sales_code || '',
    address: contact.address_line1 || '',
    city: contact.city || '',
    state: contact.state || '',
    zipCode: contact.postal_code || '',
    country: contact.country || '',
    notes: contact.description || '',
  };
}
