import { describe, it, expect } from 'vitest';
import { contactFormDataToCreate, contactFormDataToUpdate, contactToFormData } from './ContactForm.helpers';
import type { ContactFormData } from './ContactForm.helpers';
import type { Contact } from '../../../types';

const fullFormData: ContactFormData = {
  firstName: 'Jane',
  lastName: 'Doe',
  email: 'jane@example.com',
  phone: '555-1234',
  company_id: 7,
  jobTitle: 'CEO',
  salesCode: 'SC-01',
  address: '123 Main St',
  city: 'Austin',
  state: 'TX',
  zipCode: '78701',
  country: 'US',
  notes: 'VIP client',
};

const minimalFormData: ContactFormData = {
  firstName: 'Bob',
  lastName: 'Smith',
  email: 'bob@example.com',
};

const fullContact: Contact = {
  id: 42,
  first_name: 'Jane',
  last_name: 'Doe',
  email: 'jane@example.com',
  phone: '555-1234',
  company_id: 7,
  job_title: 'CEO',
  sales_code: 'SC-01',
  address_line1: '123 Main St',
  city: 'Austin',
  state: 'TX',
  postal_code: '78701',
  country: 'US',
  description: 'VIP client',
  status: 'active',
  full_name: 'Jane Doe',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  tags: [],
};

describe('contactFormDataToCreate', () => {
  it('maps all fields correctly', () => {
    const result = contactFormDataToCreate(fullFormData);
    expect(result).toMatchObject({
      first_name: 'Jane',
      last_name: 'Doe',
      email: 'jane@example.com',
      phone: '555-1234',
      company_id: 7,
      job_title: 'CEO',
      sales_code: 'SC-01',
      address_line1: '123 Main St',
      city: 'Austin',
      state: 'TX',
      postal_code: '78701',
      country: 'US',
      description: 'VIP client',
      status: 'active',
    });
  });

  it('converts empty strings to undefined for optional fields', () => {
    const result = contactFormDataToCreate(minimalFormData);
    expect(result.phone).toBeUndefined();
    expect(result.job_title).toBeUndefined();
    expect(result.sales_code).toBeUndefined();
    expect(result.address_line1).toBeUndefined();
    expect(result.description).toBeUndefined();
    expect(result.status).toBe('active');
  });

  it('converts null company_id to undefined', () => {
    const result = contactFormDataToCreate({ ...minimalFormData, company_id: null });
    expect(result.company_id).toBeUndefined();
  });
});

describe('contactFormDataToUpdate', () => {
  it('maps all fields correctly', () => {
    const result = contactFormDataToUpdate(fullFormData);
    expect(result).toMatchObject({
      first_name: 'Jane',
      last_name: 'Doe',
      email: 'jane@example.com',
      sales_code: 'SC-01',
      address_line1: '123 Main St',
      postal_code: '78701',
      description: 'VIP client',
    });
    expect((result as Record<string, unknown>).status).toBeUndefined();
  });

  it('converts empty optional strings to undefined', () => {
    const result = contactFormDataToUpdate(minimalFormData);
    expect(result.sales_code).toBeUndefined();
    expect(result.address_line1).toBeUndefined();
  });
});

describe('contactToFormData', () => {
  it('round-trips all fields from a contact object', () => {
    const result = contactToFormData(fullContact);
    expect(result).toEqual({
      firstName: 'Jane',
      lastName: 'Doe',
      email: 'jane@example.com',
      phone: '555-1234',
      company_id: 7,
      jobTitle: 'CEO',
      salesCode: 'SC-01',
      address: '123 Main St',
      city: 'Austin',
      state: 'TX',
      zipCode: '78701',
      country: 'US',
      notes: 'VIP client',
    });
  });

  it('returns empty strings for missing optional fields', () => {
    const sparse: Contact = {
      ...fullContact,
      phone: null,
      job_title: null,
      sales_code: null,
      address_line1: null,
      city: null,
      state: null,
      postal_code: null,
      country: null,
      description: null,
      company_id: null,
    };
    const result = contactToFormData(sparse);
    expect(result.phone).toBe('');
    expect(result.jobTitle).toBe('');
    expect(result.salesCode).toBe('');
    expect(result.address).toBe('');
    expect(result.zipCode).toBe('');
    expect(result.notes).toBe('');
    expect(result.company_id).toBeNull();
  });
});
