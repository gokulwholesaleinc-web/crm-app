import { useState, useRef } from 'react';
import { Button, Spinner, Modal } from '../../../components/ui';
import { PaginationBar } from '../../../components/ui/Pagination';
import {
  useExpenses,
  useExpenseTotals,
  useCreateExpense,
  useDeleteExpense,
  useUploadReceipt,
} from '../../../hooks/useExpenses';
import { formatCurrencyWithCents } from '../../../utils/formatters';
import { TrashIcon, PaperClipIcon } from '@heroicons/react/24/outline';

interface ExpensesTabProps {
  companyId: number;
}

const CATEGORIES = ['Travel', 'Supplies', 'Food', 'Software', 'Marketing', 'Consulting', 'Other'];

export default function ExpensesTab({ companyId }: ExpensesTabProps) {
  const [page, setPage] = useState(1);
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>(undefined);
  const [showAddForm, setShowAddForm] = useState(false);

  const { data: expensesData, isLoading } = useExpenses(companyId, page, 20, categoryFilter);
  const { data: totals } = useExpenseTotals(companyId);
  const createMutation = useCreateExpense();
  const deleteMutation = useDeleteExpense();
  const uploadMutation = useUploadReceipt();

  // Add form state
  const [formAmount, setFormAmount] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formCategory, setFormCategory] = useState('');
  const [formCurrency, setFormCurrency] = useState('USD');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadExpenseId, setUploadExpenseId] = useState<number | null>(null);

  const resetForm = () => {
    setFormAmount('');
    setFormDescription('');
    setFormDate('');
    setFormCategory('');
    setFormCurrency('USD');
  };

  const handleCreate = () => {
    const amount = parseFloat(formAmount);
    if (isNaN(amount) || !formDescription.trim() || !formDate) return;

    createMutation.mutate(
      {
        company_id: companyId,
        amount,
        currency: formCurrency,
        description: formDescription.trim(),
        expense_date: formDate,
        category: formCategory || undefined,
      },
      {
        onSuccess: () => {
          resetForm();
          setShowAddForm(false);
        },
      },
    );
  };

  const handleDelete = (expenseId: number) => {
    deleteMutation.mutate(expenseId);
  };

  const handleReceiptClick = (expenseId: number) => {
    setUploadExpenseId(expenseId);
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && uploadExpenseId) {
      uploadMutation.mutate({ expenseId: uploadExpenseId, file });
    }
    e.target.value = '';
    setUploadExpenseId(null);
  };

  const expenses = expensesData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Hidden file input for receipt upload */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".pdf,.png,.jpg,.jpeg,.gif"
        onChange={handleFileChange}
        aria-label="Upload receipt file"
      />

      {/* Totals Summary */}
      {totals && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <p className="text-sm text-gray-500">Total Expenses</p>
            <p className="text-2xl font-bold text-gray-900 mt-1" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatCurrencyWithCents(totals.total_amount, totals.currency)}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <p className="text-sm text-gray-500">Number of Expenses</p>
            <p className="text-2xl font-bold text-gray-900 mt-1" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {totals.count}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <p className="text-sm text-gray-500">Categories</p>
            <div className="mt-1 space-y-1">
              {Object.entries(totals.by_category).length === 0 ? (
                <p className="text-sm text-gray-400">No expenses yet</p>
              ) : (
                Object.entries(totals.by_category).map(([cat, amount]) => (
                  <div key={cat} className="flex items-center justify-between text-sm">
                    <span className="text-gray-600 truncate">{cat}</span>
                    <span className="text-gray-900 font-medium" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {formatCurrencyWithCents(amount, totals.currency)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <label htmlFor="expense-category-filter" className="text-sm font-medium text-gray-700">
            Category:
          </label>
          <select
            id="expense-category-filter"
            value={categoryFilter ?? ''}
            onChange={(e) => {
              setCategoryFilter(e.target.value || undefined);
              setPage(1);
            }}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value="">All Categories</option>
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={() => setShowAddForm(true)} className="w-full sm:w-auto">
          Add Expense
        </Button>
      </div>

      {/* Expenses Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner />
          </div>
        ) : expenses.length === 0 ? (
          <div className="text-center py-12 px-4">
            <p className="text-sm text-gray-500">No expenses found.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Date
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Description
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Category
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Amount
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {expenses.map((expense) => (
                    <tr key={expense.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {expense.expense_date}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                        {expense.description}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {expense.category ?? '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrencyWithCents(expense.amount, expense.currency)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleReceiptClick(expense.id)}
                            className="p-1.5 text-gray-400 hover:text-primary-600 rounded transition-colors"
                            aria-label={`Upload receipt for ${expense.description}`}
                            title="Upload receipt"
                          >
                            <PaperClipIcon className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(expense.id)}
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded transition-colors"
                            aria-label={`Delete expense: ${expense.description}`}
                            title="Delete"
                            disabled={deleteMutation.isPending}
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {expensesData && (
              <PaginationBar
                page={expensesData.page}
                pages={expensesData.pages}
                total={expensesData.total}
                pageSize={expensesData.page_size}
                onPageChange={setPage}
              />
            )}
          </>
        )}
      </div>

      {/* Add Expense Modal */}
      <Modal isOpen={showAddForm} onClose={() => setShowAddForm(false)} title="Add Expense" size="md">
        <div className="space-y-4">
          <div>
            <label htmlFor="expense-amount" className="block text-sm font-medium text-gray-700 mb-1">
              Amount
            </label>
            <input
              id="expense-amount"
              type="number"
              step="0.01"
              min="0"
              value={formAmount}
              onChange={(e) => setFormAmount(e.target.value)}
              placeholder="0.00"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          <div>
            <label htmlFor="expense-currency" className="block text-sm font-medium text-gray-700 mb-1">
              Currency
            </label>
            <select
              id="expense-currency"
              value={formCurrency}
              onChange={(e) => setFormCurrency(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
            </select>
          </div>
          <div>
            <label htmlFor="expense-description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              id="expense-description"
              type="text"
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              placeholder="Enter description..."
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          <div>
            <label htmlFor="expense-date" className="block text-sm font-medium text-gray-700 mb-1">
              Date
            </label>
            <input
              id="expense-date"
              type="date"
              value={formDate}
              onChange={(e) => setFormDate(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          <div>
            <label htmlFor="expense-category" className="block text-sm font-medium text-gray-700 mb-1">
              Category
            </label>
            <select
              id="expense-category"
              value={formCategory}
              onChange={(e) => setFormCategory(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">No category</option>
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setShowAddForm(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!formAmount || !formDescription.trim() || !formDate || createMutation.isPending}
            >
              {createMutation.isPending ? 'Creating...' : 'Create Expense'}
            </Button>
          </div>
          {createMutation.isError && (
            <p className="text-sm text-red-600" aria-live="polite">
              Failed to create expense. Please try again.
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
