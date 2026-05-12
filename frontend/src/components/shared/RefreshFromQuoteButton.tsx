import { useState } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { Button } from '../ui/Button';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { useRefreshProposalFromQuote } from '../../hooks/useProposals';
import { showSuccess, showError } from '../../utils/toast';

interface RefreshFromQuoteButtonProps {
  proposalId: number;
  hasQuoteLink: boolean;
  isLocked: boolean;
  onRefreshed?: () => void;
}

export function RefreshFromQuoteButton({
  proposalId,
  hasQuoteLink,
  isLocked,
  onRefreshed,
}: RefreshFromQuoteButtonProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const { mutate, isPending } = useRefreshProposalFromQuote();

  if (!hasQuoteLink) {
    return null;
  }

  function handleConfirm() {
    mutate(proposalId, {
      onSuccess: () => {
        setConfirmOpen(false);
        showSuccess('Proposal synced from quote.');
        onRefreshed?.();
      },
      onError: (err: unknown) => {
        setConfirmOpen(false);
        const msg =
          err instanceof Error ? err.message : 'Failed to refresh from quote.';
        showError(msg);
      },
    });
  }

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<ArrowPathIcon className="h-4 w-4" aria-hidden="true" />}
        disabled={isLocked || isPending}
        title={
          isLocked
            ? 'Cannot refresh a locked proposal (signed / accepted / paid).'
            : 'Sync amount and billing terms from the linked quote.'
        }
        onClick={() => setConfirmOpen(true)}
        aria-label="Refresh from quote"
      >
        Refresh from quote
      </Button>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirm}
        title="Refresh from quote?"
        message="This replaces the proposal's amount with the current quote total. Continue?"
        confirmLabel="Refresh"
        cancelLabel="Cancel"
        variant="warning"
        isLoading={isPending}
      />
    </>
  );
}
