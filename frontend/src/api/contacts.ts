/**
 * Contacts API
 */

import { apiClient } from './client';
import type {
  Contact,
  ContactCreate,
  ContactUpdate,
  ContactListResponse,
  ContactFilters,
} from '../types';

const CONTACTS_BASE = '/api/contacts';

/**
 * List contacts with pagination and filters
 */
export const listContacts = async (filters: ContactFilters = {}): Promise<ContactListResponse> => {
  const response = await apiClient.get<ContactListResponse>(CONTACTS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a contact by ID
 */
export const getContact = async (contactId: number): Promise<Contact> => {
  const response = await apiClient.get<Contact>(`${CONTACTS_BASE}/${contactId}`);
  return response.data;
};

/**
 * Create a new contact
 */
export const createContact = async (contactData: ContactCreate): Promise<Contact> => {
  const response = await apiClient.post<Contact>(CONTACTS_BASE, contactData);
  return response.data;
};

/**
 * Update a contact
 */
export const updateContact = async (
  contactId: number,
  contactData: ContactUpdate
): Promise<Contact> => {
  const response = await apiClient.patch<Contact>(
    `${CONTACTS_BASE}/${contactId}`,
    contactData
  );
  return response.data;
};

/**
 * Delete a contact
 */
export const deleteContact = async (contactId: number): Promise<void> => {
  await apiClient.delete(`${CONTACTS_BASE}/${contactId}`);
};

// Export all contact functions
export const contactsApi = {
  list: listContacts,
  get: getContact,
  create: createContact,
  update: updateContact,
  delete: deleteContact,
};

export default contactsApi;
