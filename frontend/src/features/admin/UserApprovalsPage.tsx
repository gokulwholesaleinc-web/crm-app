import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { useAuthStore } from '../../store/authStore';
import {
  getPendingUsers,
  approveUser,
  rejectUser,
  getRejectedEmails,
  unblockRejectedEmail,
} from '../../api/admin';
import type { PendingUser, RejectedEmail } from '../../types';

type ApprovalRole = 'sales_rep' | 'manager' | 'admin';

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
});

function RejectModal({
  user,
  onConfirm,
  onCancel,
  isPending,
}: {
  user: PendingUser;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [reason, setReason] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">
          Reject {user.full_name || user.email}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Optionally provide a reason. The email will be added to the reject list.
        </p>
        <label htmlFor="reject-reason" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Reason (optional)
        </label>
        <textarea
          id="reject-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          placeholder="Optional reason..."
        />
        <div className="mt-4 flex justify-end gap-3">
          <Button variant="secondary" size="sm" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            isLoading={isPending}
            onClick={() => onConfirm(reason)}
          >
            Reject
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function UserApprovalsPage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();

  const { data: pending, isLoading: loadingPending } = useQuery({
    queryKey: ['admin', 'pending-users'],
    queryFn: getPendingUsers,
  });

  const { data: rejected, isLoading: loadingRejected } = useQuery({
    queryKey: ['admin', 'rejected-emails'],
    queryFn: getRejectedEmails,
  });

  const [selectedRoles, setSelectedRoles] = useState<Record<number, ApprovalRole>>({});
  const [rejectTarget, setRejectTarget] = useState<PendingUser | null>(null);

  const approveMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: ApprovalRole }) => approveUser(id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'pending-users'] });
      toast.success('User approved');
    },
    onError: () => toast.error('Failed to approve user'),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => rejectUser(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'pending-users'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'rejected-emails'] });
      setRejectTarget(null);
      toast.success('User rejected');
    },
    onError: () => toast.error('Failed to reject user'),
  });

  const unblockMutation = useMutation({
    mutationFn: (id: number) => unblockRejectedEmail(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'rejected-emails'] });
      toast.success('Email unblocked');
    },
    onError: () => toast.error('Failed to unblock email'),
  });

  const isAdmin = user?.is_superuser || user?.role === 'admin';
  if (!isAdmin) {
    toast.error('Access denied');
    navigate('/', { replace: true });
    return null;
  }

  const getRoleForUser = (id: number): ApprovalRole => selectedRoles[id] ?? 'sales_rep';

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">User Approvals</h1>
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Manage pending sign-up requests and blocked emails
        </p>
      </div>

      {/* Pending Requests */}
      <Card>
        <CardHeader title="Pending Requests" description="Users who signed in with Google and are awaiting approval" />
        <CardBody>
          {loadingPending ? (
            <div className="flex items-center justify-center py-8">
              <Spinner size="md" />
            </div>
          ) : !pending?.length ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">No pending requests</p>
          ) : (
            <div className="overflow-x-auto -mx-4 sm:mx-0">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Email</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Full Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Requested At</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Role</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {pending.map((u) => (
                    <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">{u.email}</td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{u.full_name || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                        {dateFormatter.format(new Date(u.created_at))}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={getRoleForUser(u.id)}
                          onChange={(e) =>
                            setSelectedRoles((prev) => ({ ...prev, [u.id]: e.target.value as ApprovalRole }))
                          }
                          className="text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                          aria-label={`Role for ${u.email}`}
                        >
                          <option value="sales_rep">Sales Rep</option>
                          <option value="manager">Manager</option>
                          <option value="admin">Admin</option>
                        </select>
                      </td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <Button
                          size="sm"
                          isLoading={approveMutation.isPending && approveMutation.variables?.id === u.id}
                          onClick={() => approveMutation.mutate({ id: u.id, role: getRoleForUser(u.id) })}
                          disabled={rejectMutation.isPending}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => setRejectTarget(u)}
                          disabled={approveMutation.isPending || rejectMutation.isPending}
                        >
                          Reject
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Rejected Emails */}
      <Card>
        <CardHeader title="Rejected Emails" description="Emails that have been blocked from signing in" />
        <CardBody>
          {loadingRejected ? (
            <div className="flex items-center justify-center py-8">
              <Spinner size="md" />
            </div>
          ) : !rejected?.length ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">No rejected emails</p>
          ) : (
            <div className="overflow-x-auto -mx-4 sm:mx-0">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Email</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Rejected By</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Rejected At</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Reason</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {rejected.map((r: RejectedEmail) => (
                    <tr key={r.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">{r.email}</td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{r.rejected_by}</td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                        {dateFormatter.format(new Date(r.rejected_at))}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{r.reason || '—'}</td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          isLoading={unblockMutation.isPending && unblockMutation.variables === r.id}
                          onClick={() => unblockMutation.mutate(r.id)}
                        >
                          Unblock
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {rejectTarget && (
        <RejectModal
          user={rejectTarget}
          isPending={rejectMutation.isPending}
          onConfirm={(reason) => rejectMutation.mutate({ id: rejectTarget.id, reason: reason || undefined })}
          onCancel={() => setRejectTarget(null)}
        />
      )}
    </div>
  );
}
