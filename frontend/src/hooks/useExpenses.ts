import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listExpenses, createExpense, updateExpense, deleteExpense, getExpenseTotals, uploadReceipt } from '../api/expenses';
import type { ExpenseCreate, ExpenseUpdate } from '../api/expenses';

export const expenseKeys = {
  all: ['expenses'] as const,
  list: (companyId: number, params?: Record<string, unknown>) => [...expenseKeys.all, 'list', companyId, params] as const,
  totals: (companyId: number) => [...expenseKeys.all, 'totals', companyId] as const,
};

export function useExpenses(companyId: number | undefined, page = 1, pageSize = 20, category?: string) {
  return useQuery({
    queryKey: expenseKeys.list(companyId!, { page, pageSize, category }),
    queryFn: () => listExpenses({ company_id: companyId!, page, page_size: pageSize, category }),
    enabled: !!companyId,
  });
}

export function useExpenseTotals(companyId: number | undefined) {
  return useQuery({
    queryKey: expenseKeys.totals(companyId!),
    queryFn: () => getExpenseTotals(companyId!),
    enabled: !!companyId,
  });
}

export function useCreateExpense() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ExpenseCreate) => createExpense(data),
    onSuccess: (expense) => {
      queryClient.invalidateQueries({ queryKey: expenseKeys.list(expense.company_id) });
      queryClient.invalidateQueries({ queryKey: expenseKeys.totals(expense.company_id) });
    },
  });
}

export function useUpdateExpense() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ExpenseUpdate }) => updateExpense(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}

export function useDeleteExpense() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteExpense(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}

export function useUploadReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ expenseId, file }: { expenseId: number; file: File }) => uploadReceipt(expenseId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expenseKeys.all });
    },
  });
}
