import { apiClient } from './client';
import type { PaginatedResponse } from '../types';

export interface Expense {
  id: number;
  company_id: number;
  amount: number;
  currency: string;
  description: string;
  expense_date: string;
  category: string | null;
  receipt_attachment_id: number | null;
  payment_id: number | null;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ExpenseCreate {
  company_id: number;
  amount: number;
  currency?: string;
  description: string;
  expense_date: string;
  category?: string;
  receipt_attachment_id?: number;
  payment_id?: number;
}

export interface ExpenseUpdate {
  amount?: number;
  currency?: string;
  description?: string;
  expense_date?: string;
  category?: string;
}

export interface ExpenseTotals {
  total_amount: number;
  currency: string;
  count: number;
  by_category: Record<string, number>;
}

const BASE = '/api/expenses';

export const listExpenses = async (params: { company_id: number; page?: number; page_size?: number; category?: string }): Promise<PaginatedResponse<Expense>> => {
  const response = await apiClient.get<PaginatedResponse<Expense>>(BASE, { params });
  return response.data;
};

export const createExpense = async (data: ExpenseCreate): Promise<Expense> => {
  const response = await apiClient.post<Expense>(BASE, data);
  return response.data;
};

export const getExpenseTotals = async (companyId: number): Promise<ExpenseTotals> => {
  const response = await apiClient.get<ExpenseTotals>(`${BASE}/totals`, { params: { company_id: companyId } });
  return response.data;
};

export const updateExpense = async (id: number, data: ExpenseUpdate): Promise<Expense> => {
  const response = await apiClient.patch<Expense>(`${BASE}/${id}`, data);
  return response.data;
};

export const deleteExpense = async (id: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const uploadReceipt = async (expenseId: number, file: File): Promise<Expense> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<Expense>(`${BASE}/${expenseId}/receipt`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};
