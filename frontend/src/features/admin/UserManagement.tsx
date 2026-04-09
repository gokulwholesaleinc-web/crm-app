import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Table } from '../../components/ui/Table';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { useAdminUsers, useUpdateAdminUser, useAssignUserRole } from '../../hooks/useAdmin';
import { useAuthStore } from '../../store/authStore';
import { authApi } from '../../api/auth';
import { deleteUserPermanently } from '../../api/admin';
import toast from 'react-hot-toast';
import type { AdminUser } from '../../types';
import type { Column } from '../../components/ui/Table';
import { PencilSquareIcon, XMarkIcon, TrashIcon } from '@heroicons/react/24/outline';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  manager: 'Manager',
  sales_rep: 'Sales Rep',
  viewer: 'Viewer',
};

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

interface EditUserFormData {
  full_name: string;
  email: string;
}

const INITIAL_FORM: QuickAddFormData = {
  full_name: '',
  email: '',
  password: '',
  role: 'sales_rep',
};

export default function UserManagement() {
  const { data: users, isLoading, refetch } = useAdminUsers();
  const currentUser = useAuthStore((s) => s.user);
  const updateUser = useUpdateAdminUser();
  const assignRole = useAssignUserRole();

  const [sortColumn, setSortColumn] = useState<string>('full_name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filter, setFilter] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState<QuickAddFormData>(INITIAL_FORM);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState<EditUserFormData>({ full_name: '', email: '' });
  const [editError, setEditError] = useState<string | null>(null);
  const [deletingUser, setDeletingUser] = useState<AdminUser | null>(null);
  // Pending role change — held in state so we can show a ConfirmDialog
  // before the mutation runs. Users previously could click the role
  // dropdown and instantly demote themselves from admin. See
  // settings-admin.md audit P0 #2.
  const [pendingRoleChange, setPendingRoleChange] = useState<{
    user: AdminUser;
    newRole: string;
  } | null>(null);
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: (userId: number) => deleteUserPermanently(userId),
    onSuccess: () => {
      toast.success(`User permanently deleted`);
      setDeletingUser(null);
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (err: unknown) => {
      const msg = err && typeof err === 'object' && 'detail' in err ? String((err as { detail: string }).detail) : 'Failed to delete user';
      toast.error(msg);
    },
  });

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

  const handleOpenEdit = useCallback((user: AdminUser) => {
    setEditingUser(user);
    setEditForm({ full_name: user.full_name, email: user.email });
    setEditError(null);
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!editingUser) return;
    if (!editForm.full_name.trim() || !editForm.email.trim()) {
      setEditError('Name and email are required');
      return;
    }
    const updates: Record<string, string> = {};
    if (editForm.full_name !== editingUser.full_name) updates.full_name = editForm.full_name;
    if (editForm.email !== editingUser.email) updates.email = editForm.email;
    if (Object.keys(updates).length === 0) {
      setEditingUser(null);
      return;
    }
    try {
      await updateUser.mutateAsync({ userId: editingUser.id, data: updates });
      toast.success('User updated successfully');
      setEditingUser(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update user';
      setEditError(msg);
    }
  }, [editingUser, editForm, updateUser]);

  const handleSort = useCallback((column: string) => {
    setSortDirection((prev) =>
      sortColumn === column && prev === 'asc' ? 'desc' : 'asc'
    );
    setSortColumn(column);
  }, [sortColumn]);

  const handleRoleChange = useCallback(
    (user: AdminUser, newRole: string) => {
      if (newRole === user.role) return;
      setPendingRoleChange({ user, newRole });
    },
    []
  );

  const handleConfirmRoleChange = useCallback(() => {
    if (!pendingRoleChange) return;
    updateUser.mutate(
      { userId: pendingRoleChange.user.id, data: { role: pendingRoleChange.newRole } },
      {
        onSuccess: () => {
          toast.success(
            `${pendingRoleChange.user.full_name} is now ${ROLE_LABELS[pendingRoleChange.newRole] ?? pendingRoleChange.newRole}`
          );
          setPendingRoleChange(null);
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : 'Failed to change role';
          toast.error(msg);
          setPendingRoleChange(null);
        },
      }
    );
  }, [pendingRoleChange, updateUser]);

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
    .toSorted((a, b) => {
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
        <div className="min-w-0 flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-medium text-gray-900 dark:text-gray-100 truncate">{row.full_name}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{row.email}</p>
          </div>
          <button
            type="button"
            onClick={() => handleOpenEdit(row)}
            className="flex-shrink-0 p-1 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label={`Edit ${row.full_name}`}
          >
            <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
          </button>
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
          onChange={(e) => handleRoleChange(row, e.target.value)}
          className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          aria-label={`Change role for ${row.full_name}`}
        >
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r] ?? r}
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
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <button
          type="button"
          onClick={() => setDeletingUser(row)}
          className="p-1 text-gray-400 hover:text-red-500 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          aria-label={`Delete ${row.full_name}`}
        >
          <TrashIcon className="h-4 w-4" aria-hidden="true" />
        </button>
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
      {/* Edit User Modal */}
      {editingUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setEditingUser(null);
          }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Edit User
              </h3>
              <button
                type="button"
                onClick={() => setEditingUser(null)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label="Close modal"
              >
                <XMarkIcon className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            <div className="px-6 py-4 space-y-4">
              {editError && (
                <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                  {editError}
                </p>
              )}

              <div>
                <label
                  htmlFor="edit-user-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Full Name
                </label>
                <input
                  id="edit-user-name"
                  type="text"
                  value={editForm.full_name}
                  onChange={(e) => setEditForm((f) => ({ ...f, full_name: e.target.value }))}
                  autoComplete="name"
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
              </div>

              <div>
                <label
                  htmlFor="edit-user-email"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Email
                </label>
                <input
                  id="edit-user-email"
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))}
                  autoComplete="email"
                  spellCheck={false}
                  className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <Button
                variant="secondary"
                onClick={() => {
                  setEditingUser(null);
                  setEditError(null);
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleSaveEdit} disabled={updateUser.isPending}>
                {updateUser.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </div>
      )}
      {/* Role Change Confirmation — prevents accidental one-click
          self-demotion or permission escalation. */}
      <ConfirmDialog
        isOpen={pendingRoleChange !== null}
        onClose={() => setPendingRoleChange(null)}
        onConfirm={handleConfirmRoleChange}
        title={
          pendingRoleChange && currentUser?.id === pendingRoleChange.user.id
            ? 'Change your own role?'
            : 'Change user role?'
        }
        message={
          pendingRoleChange ? (
            <>
              Change <strong>{pendingRoleChange.user.full_name}</strong>&rsquo;s role from{' '}
              <strong>{ROLE_LABELS[pendingRoleChange.user.role] ?? pendingRoleChange.user.role}</strong>{' '}
              to <strong>{ROLE_LABELS[pendingRoleChange.newRole] ?? pendingRoleChange.newRole}</strong>?
              {currentUser?.id === pendingRoleChange.user.id && pendingRoleChange.newRole !== 'admin' && (
                <span className="mt-2 block font-medium text-red-600 dark:text-red-400">
                  Warning: you are changing your own role. You may lose access to admin features immediately.
                </span>
              )}
            </>
          ) : (
            ''
          )
        }
        confirmLabel="Change role"
        variant="warning"
        isLoading={updateUser.isPending}
      />

      {/* Delete Confirmation Modal */}
      {deletingUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setDeletingUser(null);
          }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-sm mx-4">
            <div className="px-6 py-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-shrink-0 h-10 w-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <TrashIcon className="h-5 w-5 text-red-600 dark:text-red-400" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    Delete User
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    This action cannot be undone.
                  </p>
                </div>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                Permanently delete <strong>{deletingUser.full_name}</strong> ({deletingUser.email})?
                Their owned records will have the owner cleared.
              </p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <Button variant="secondary" onClick={() => setDeletingUser(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deletingUser.id)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete Permanently'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
