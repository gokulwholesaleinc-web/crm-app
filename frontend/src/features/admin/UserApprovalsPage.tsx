import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { useAuthStore } from '../../store/authStore';
import {
  getPendingUsers,
  approveUser,
  rejectUser,
  getRejectedEmails,
  unblockRejectedEmail,
} from '../../api/admin';
import type { ApprovalRole } from '../../api/admin';
import type { PendingUser, RejectedEmail } from '../../types';
import { formatDate } from '../../utils/formatters';

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
    <Modal
      isOpen
      onClose={onCancel}
      title={`Reject ${user.full_name || user.email}`}
      description="Optionally provide a reason. The email will be added to the reject list."
      size="md"
      closeOnOverlayClick={!isPending}
    >
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
      <div className="mt-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 sm:gap-3">
        <Button
          variant="secondary"
          onClick={onCancel}
          disabled={isPending}
          className="w-full sm:w-auto min-h-[44px] sm:min-h-0"
        >
          Cancel
        </Button>
        <Button
          variant="danger"
          isLoading={isPending}
          onClick={() => onConfirm(reason)}
          className="w-full sm:w-auto min-h-[44px] sm:min-h-0"
        >
          Reject
        </Button>
      </div>
    </Modal>
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
  // Confirm gate for granting admin — non-admin roles approve in one click.
  const [adminApprovalTarget, setAdminApprovalTarget] = useState<PendingUser | null>(null);

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

  useEffect(() => {
    if (!isAdmin) {
      toast.error('Access denied');
      navigate('/', { replace: true });
    }
  }, [isAdmin, navigate]);

  if (!isAdmin) return null;

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
                        {formatDate(u.created_at, 'short')}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={getRoleForUser(u.id)}
                          onChange={(e) =>
                            setSelectedRoles((prev) => ({ ...prev, [u.id]: e.target.value as ApprovalRole }))
                          }
                          className="text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-2 py-2 sm:py-1 min-h-[44px] sm:min-h-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                          aria-label={`Role for ${u.email}`}
                        >
                          <option value="sales_rep">Sales Rep</option>
                          <option value="manager">Manager</option>
                          <option value="admin">Admin</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            size="sm"
                            className="min-h-[44px] sm:min-h-0"
                            isLoading={approveMutation.isPending && approveMutation.variables?.id === u.id}
                            onClick={() => {
                              if (getRoleForUser(u.id) === 'admin') {
                                setAdminApprovalTarget(u);
                              } else {
                                approveMutation.mutate({ id: u.id, role: getRoleForUser(u.id) });
                              }
                            }}
                            disabled={rejectMutation.isPending}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            className="min-h-[44px] sm:min-h-0"
                            onClick={() => setRejectTarget(u)}
                            disabled={approveMutation.isPending || rejectMutation.isPending}
                          >
                            Reject
                          </Button>
                        </div>
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
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{r.rejected_by_email ?? '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(r.rejected_at, 'short')}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{r.reason || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end">
                          <Button
                            size="sm"
                            variant="secondary"
                            className="min-h-[44px] sm:min-h-0"
                            isLoading={unblockMutation.isPending && unblockMutation.variables === r.id}
                            onClick={() => unblockMutation.mutate(r.id)}
                          >
                            Unblock
                          </Button>
                        </div>
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

      <ConfirmDialog
        isOpen={adminApprovalTarget !== null}
        onClose={() => setAdminApprovalTarget(null)}
        onConfirm={() => {
          if (adminApprovalTarget) {
            approveMutation.mutate(
              { id: adminApprovalTarget.id, role: 'admin' },
              { onSettled: () => setAdminApprovalTarget(null) }
            );
          }
        }}
        title="Approve as admin?"
        message={
          adminApprovalTarget ? (
            <>
              Approve <strong>{adminApprovalTarget.email}</strong> as <strong>admin</strong>?
              They will have full access to all data, settings, and other users.
            </>
          ) : (
            ''
          )
        }
        confirmLabel="Approve admin"
        variant="danger"
        isLoading={approveMutation.isPending}
      />
    </div>
  );
}
