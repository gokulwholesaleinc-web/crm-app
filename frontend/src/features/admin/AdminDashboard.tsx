import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Table } from '../../components/ui/Table';
import { Spinner } from '../../components/ui/Spinner';
import {
  useSystemStats,
  useTeamOverview,
  useActivityFeed,
} from '../../hooks/useAdmin';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useAuthStore } from '../../store/authStore';
import UserManagement from './UserManagement';
import type { TeamMemberOverview } from '../../types';
import type { Column } from '../../components/ui/Table';
import {
  UsersIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  ClockIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline';

const currencyFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

type BadgeVariant = 'green' | 'blue' | 'red' | 'gray' | 'indigo';

const ACTION_BADGE_VARIANT: Record<string, BadgeVariant> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
};

const ROLE_BADGE_VARIANT: Record<string, BadgeVariant> = {
  admin: 'indigo',
  manager: 'blue',
  sales_rep: 'green',
};

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

function StatCard({ label, value, icon: Icon, color }: StatCardProps) {
  return (
    <Card padding="sm" className="flex items-center gap-4">
      <div className={`flex-shrink-0 p-3 rounded-lg ${color}`}>
        <Icon className="h-6 w-6 text-white" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{label}</p>
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {value.toLocaleString()}
        </p>
      </div>
    </Card>
  );
}

const teamColumns: Column<TeamMemberOverview>[] = [
  {
    key: 'user_name',
    header: 'Name',
    sortable: true,
    render: (row) => (
      <span className="font-medium text-gray-900 dark:text-gray-100">{row.user_name}</span>
    ),
  },
  {
    key: 'role',
    header: 'Role',
    sortable: true,
    render: (row) => (
      <Badge variant={ROLE_BADGE_VARIANT[row.role] ?? 'gray'} size="sm">
        {row.role.replace('_', ' ')}
      </Badge>
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
    key: 'opportunity_count',
    header: 'Opps',
    sortable: true,
    render: (row) => (
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.opportunity_count}</span>
    ),
  },
  {
    key: 'total_pipeline_value',
    header: 'Pipeline Value',
    sortable: true,
    render: (row) => (
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
        {currencyFormatter.format(row.total_pipeline_value)}
      </span>
    ),
  },
  {
    key: 'won_deals',
    header: 'Won Deals',
    sortable: true,
    render: (row) => (
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{row.won_deals}</span>
    ),
  },
];

export default function AdminDashboard() {
  usePageTitle('Admin Dashboard');
  const user = useAuthStore((s) => s.user);

  // Client-side role gate. The backend already rejects admin mutations from
  // non-admins, but without this gate a non-admin route-hacking to /admin
  // sees the full dashboard UI (users, stats, activity feed) until they
  // click something and hit a 403. See `settings-admin.md` audit P0 #1.
  const isAdmin = user?.role === 'admin' || user?.is_superuser === true;

  // Hooks must run unconditionally — call them before the early return so
  // React's hook order stays stable. The backend enforces real
  // authorization; the queries will 403 for non-admins and show an empty
  // state below the access-denied banner.
  const { data: stats, isLoading: statsLoading } = useSystemStats();
  const { data: team, isLoading: teamLoading } = useTeamOverview();
  const { data: feed, isLoading: feedLoading } = useActivityFeed(30);

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <LockClosedIcon className="h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" aria-hidden="true" />
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Access Denied
        </h1>
        <p className="max-w-md text-sm text-gray-500 dark:text-gray-400">
          You don&rsquo;t have permission to view the admin dashboard. If you believe this is a mistake, contact your workspace administrator.
        </p>
      </div>
    );
  }

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner />
      </div>
    );
  }

  const statCards: StatCardProps[] = stats
    ? [
        { label: 'Total Users', value: stats.total_users, icon: UsersIcon, color: 'bg-indigo-500' },
        { label: 'Active (7d)', value: stats.active_users_7d, icon: ClockIcon, color: 'bg-green-500' },
        { label: 'Contacts', value: stats.total_contacts, icon: UserGroupIcon, color: 'bg-blue-500' },
        { label: 'Companies', value: stats.total_companies, icon: BuildingOfficeIcon, color: 'bg-purple-500' },
        { label: 'Leads', value: stats.total_leads, icon: FunnelIcon, color: 'bg-yellow-500' },
        { label: 'Opportunities', value: stats.total_opportunities, icon: CurrencyDollarIcon, color: 'bg-emerald-500' },
        { label: 'Quotes', value: stats.total_quotes, icon: DocumentTextIcon, color: 'bg-cyan-500' },
        { label: 'Proposals', value: stats.total_proposals, icon: DocumentDuplicateIcon, color: 'bg-pink-500' },
        { label: 'Payments', value: stats.total_payments, icon: CreditCardIcon, color: 'bg-orange-500' },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Admin Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          System-wide overview and user management
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {statCards.map((card) => (
          <StatCard key={card.label} {...card} />
        ))}
      </div>

      {/* User Management */}
      <UserManagement />

      {/* Team Overview */}
      <Card>
        <CardHeader title="Team Overview" description="Per-user pipeline breakdown" />
        <CardBody>
          <Table
            columns={teamColumns}
            data={team ?? []}
            keyExtractor={(row) => row.user_id}
            isLoading={teamLoading}
            emptyMessage="No active team members"
          />
        </CardBody>
      </Card>

      {/* Activity Feed */}
      <Card>
        <CardHeader title="Recent Activity" description="Latest actions across the system" />
        <CardBody>
          {feedLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : !feed || feed.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-4">No recent activity</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {feed.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-start gap-3 py-2 border-b border-gray-100 dark:border-gray-700 last:border-0"
                >
                  <Badge
                    variant={ACTION_BADGE_VARIANT[entry.action] ?? 'gray'}
                    size="sm"
                  >
                    {entry.action}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-900 dark:text-gray-100">
                      <span className="font-medium">{entry.user_name ?? 'System'}</span>
                      {' '}
                      {entry.action}d a{' '}
                      <span className="font-medium">{entry.entity_type}</span>
                      {' '}
                      <span className="text-gray-500 dark:text-gray-400">#{entry.entity_id}</span>
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {dateFormatter.format(new Date(entry.timestamp))}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
