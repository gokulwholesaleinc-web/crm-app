import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Table } from '../../components/ui/Table';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { useAdminUsers, useUpdateAdminUser } from '../../hooks/useAdmin';
import type { AdminUser } from '../../types';
import type { Column } from '../../components/ui/Table';

const ROLE_OPTIONS = ['admin', 'manager', 'sales_rep', 'viewer'] as const;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export default function UserManagement() {
  const { data: users, isLoading } = useAdminUsers();
  const updateUser = useUpdateAdminUser();
  const navigate = useNavigate();

  const [sortColumn, setSortColumn] = useState<string>('full_name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filter, setFilter] = useState('');

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
          className="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
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
          className="focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
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
          <Button
            onClick={() => navigate('/register')}
          >
            Add User
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
            className="w-full max-w-sm text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
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
    </Card>
  );
}
