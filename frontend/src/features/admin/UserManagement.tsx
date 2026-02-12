import { useState, useCallback } from 'react';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Table } from '../../components/ui/Table';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { useAdminUsers, useUpdateAdminUser, useAssignUserRole } from '../../hooks/useAdmin';
import { authApi } from '../../api/auth';
import toast from 'react-hot-toast';
import type { AdminUser } from '../../types';
import type { Column } from '../../components/ui/Table';
import { XMarkIcon } from '@heroicons/react/24/outline';

const ROLE_OPTIONS = ['admin', 'manager', 'sales_rep', 'viewer'] as const;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

interface QuickAddFormData {
  full_name: string;
  email: string;
  password: string;
  role: string;
}

const INITIAL_FORM: QuickAddFormData = {
  full_name: '',
  email: '',
  password: '',
  role: 'sales_rep',
};

export default function UserManagement() {
  const { data: users, isLoading, refetch } = useAdminUsers();
  const updateUser = useUpdateAdminUser();
  const assignRole = useAssignUserRole();

  const [sortColumn, setSortColumn] = useState<string>('full_name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filter, setFilter] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState<QuickAddFormData>(INITIAL_FORM);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const handleQuickAdd = useCallback(async () => {
    if (!addForm.full_name || !addForm.email || !addForm.password) {
      setAddError('All fields are required');
      return;
    }
    setAddLoading(true);
    setAddError(null);
    try {
      const newUser = await authApi.register({
        full_name: addForm.full_name,
        email: addForm.email,
        password: addForm.password,
      });
      if (addForm.role !== 'sales_rep') {
        await assignRole.mutateAsync({ userId: newUser.id, data: { role: addForm.role } });
      }
      toast.success(`User ${addForm.full_name} created successfully`);
      setShowAddModal(false);
      setAddForm(INITIAL_FORM);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create user';
      setAddError(msg);
    } finally {
      setAddLoading(false);
    }
  }, [addForm, assignRole, refetch]);

  const handleSort = useCallback((column: string) => {
    setSortDirection((prev) =>
      sortColumn === column && prev === 'asc' ? 'desc' : 'asc'
    );
    setSortColumn(column);
  }, [sortColumn]);

  const handleRoleChange = useCallback(
    (userId: number, role: string) => {
      updateUser.mutate({ userId, data: { role } });
    },
    [updateUser]
  );

  const handleToggleActive = useCallback(
    (userId: number, currentlyActive: boolean) => {
      updateUser.mutate({ userId, data: { is_active: !currentlyActive } });
    },
    [updateUser]
  );

  const filteredUsers = (users ?? [])
    .filter((u) => {
      if (!filter) return true;
      const lc = filter.toLowerCase();
      return (
        u.full_name.toLowerCase().includes(lc) ||
        u.email.toLowerCase().includes(lc) ||
        u.role.toLowerCase().includes(lc)
      );
    })
    .slice()
    .sort((a, b) => {
      const aVal = String((a as unknown as Record<string, unknown>)[sortColumn] ?? '');
      const bVal = String((b as unknown as Record<string, unknown>)[sortColumn] ?? '');
      const cmp = aVal.localeCompare(bVal);
      return sortDirection === 'asc' ? cmp : -cmp;
    });

  const columns: Column<AdminUser>[] = [
    {
      key: 'full_name',
      header: 'Name',
      sortable: true,
      render: (row) => (
        <div className="min-w-0">
          <p className="font-medium text-gray-900 dark:text-gray-100 truncate">{row.full_name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{row.email}</p>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      sortable: true,
      render: (row) => (
        <select
          value={row.role}
          onChange={(e) => handleRoleChange(row.id, e.target.value)}
          className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          aria-label={`Change role for ${row.full_name}`}
        >
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r.replace('_', ' ')}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      render: (row) => (
        <button
          type="button"
          onClick={() => handleToggleActive(row.id, row.is_active)}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
          aria-label={`${row.is_active ? 'Deactivate' : 'Activate'} ${row.full_name}`}
        >
          <Badge variant={row.is_active ? 'green' : 'red'} dot>
            {row.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </button>
      ),
    },
    {
      key: 'last_login',
      header: 'Last Login',
      sortable: true,
      render: (row) => (
        <span className="text-gray-500 dark:text-gray-400 text-sm">
          {row.last_login ? dateFormatter.format(new Date(row.last_login)) : 'Never'}
        </span>
      ),
    },
    {
      key: 'lead_count',
      header: 'Leads',
      sortable: true,
      render: (row) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.lead_count}</span>
      ),
    },
    {
      key: 'contact_count',
      header: 'Contacts',
      sortable: true,
      render: (row) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.contact_count}</span>
      ),
    },
    {
      key: 'opportunity_count',
      header: 'Opps',
      sortable: true,
      render: (row) => (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.opportunity_count}</span>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader
        title="User Management"
        description="Manage users, roles, and account status"
        action={
          <Button onClick={() => setShowAddModal(true)}>
            Quick Add User
          </Button>
        }
      />
      <CardBody>
        <div className="mb-4">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by name, email, or role..."
            className="w-full max-w-sm text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label="Filter users"
          />
        </div>
        <Table
          columns={columns}
          data={filteredUsers}
          keyExtractor={(row) => row.id}
          sortColumn={sortColumn}
          sortDirection={sortDirection}
          onSort={handleSort}
          isLoading={isLoading}
          emptyMessage="No users found"
        />
      </CardBody>

      {/* Quick Add User Modal */}
      {showAddModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowAddModal(false);
          }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Quick Add User
              </h3>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label="Close modal"
              >
                <XMarkIcon className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            <div className="px-6 py-4 space-y-4">
              {addError && (
                <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                  {addError}
                </p>
              )}

              <div>
                <label
                  htmlFor="quick-add-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Full Name
                </label>
                <input
                  id="quick-add-name"
                  type="text"
                  value={addForm.full_name}
                  onChange={(e) => setAddForm((f) => ({ ...f, full_name: e.target.value }))}
                  placeholder="John Doe..."
                  autoComplete="name"
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
              </div>

              <div>
                <label
                  htmlFor="quick-add-email"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Email
                </label>
                <input
                  id="quick-add-email"
                  type="email"
                  value={addForm.email}
                  onChange={(e) => setAddForm((f) => ({ ...f, email: e.target.value }))}
                  placeholder="john@example.com..."
                  autoComplete="email"
                  spellCheck={false}
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
              </div>

              <div>
                <label
                  htmlFor="quick-add-password"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Password
                </label>
                <input
                  id="quick-add-password"
                  type="password"
                  value={addForm.password}
                  onChange={(e) => setAddForm((f) => ({ ...f, password: e.target.value }))}
                  placeholder="Minimum 8 characters..."
                  autoComplete="new-password"
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
              </div>

              <div>
                <label
                  htmlFor="quick-add-role"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Role
                </label>
                <select
                  id="quick-add-role"
                  value={addForm.role}
                  onChange={(e) => setAddForm((f) => ({ ...f, role: e.target.value }))}
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  aria-label="Select role"
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>
                      {r.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <Button
                variant="secondary"
                onClick={() => {
                  setShowAddModal(false);
                  setAddForm(INITIAL_FORM);
                  setAddError(null);
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleQuickAdd} disabled={addLoading}>
                {addLoading ? 'Creating...' : 'Create User'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
