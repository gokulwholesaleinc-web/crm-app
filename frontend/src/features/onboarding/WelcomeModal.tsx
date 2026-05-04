/**
 * First-login welcome modal pointing the user at the three highest-value
 * tutorials. Replay link lives in /help so users can re-open it any time.
 *
 * Dismiss state is per-browser via safeStorage (see welcomeStorage.ts).
 * Server-side tracking isn't worth the migration cost for a re-show
 * across browsers.
 */

import { useNavigate } from 'react-router-dom';
import {
  AcademicCapIcon,
  CreditCardIcon,
  DocumentCheckIcon,
  CurrencyDollarIcon,
} from '@heroicons/react/24/outline';
import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';
import { markWelcomeSeen } from './welcomeStorage';

interface Tile {
  anchor: string;
  title: string;
  blurb: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const TILES: Tile[] = [
  {
    anchor: 'tutorial-create-invoice',
    title: 'Send an invoice',
    blurb: 'Pick a customer, set the amount, and Stripe emails them a hosted invoice link.',
    Icon: CreditCardIcon,
  },
  {
    anchor: 'tutorial-esign',
    title: 'Get a contract signed',
    blurb: 'Send a Quote or Proposal — clients sign right on the public link. No DocuSign needed.',
    Icon: DocumentCheckIcon,
  },
  {
    anchor: 'tutorial-view-billings',
    title: 'View customer billings',
    blurb: 'Open any contact or company → click Payments tab → see every charge they have.',
    Icon: CurrencyDollarIcon,
  },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function WelcomeModal({ isOpen, onClose }: Props) {
  const navigate = useNavigate();

  const handleDismiss = () => {
    markWelcomeSeen();
    onClose();
  };

  const handleTileClick = (anchor: string) => {
    markWelcomeSeen();
    onClose();
    navigate(`/help#${anchor}`);
  };

  const handleSeeAll = () => {
    markWelcomeSeen();
    onClose();
    // The Tutorials section card is rendered with id="help-section-tutorials"
    // (HelpPage.tsx). Anchor names like "tutorial-create-invoice" target the
    // per-walkthrough articles inside that section.
    navigate('/help#help-section-tutorials');
  };

  return (
    // showCloseButton=false so initial focus lands on the first tile rather
    // than the X — the modal opens unsolicited on first login, and we don't
    // want a keyboard-Enter to dismiss before the user reads anything. Esc
    // and overlay click still dismiss via onClose.
    <Modal isOpen={isOpen} onClose={handleDismiss} size="full" showCloseButton={false}>
      <div className="space-y-5">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400">
            <AcademicCapIcon className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Welcome to your CRM
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Three quick walkthroughs to get you (and your clients) up and running.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {TILES.map(({ anchor, title, blurb, Icon }) => (
            <button
              key={anchor}
              type="button"
              onClick={() => handleTileClick(anchor)}
              className="group flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4 text-left transition-colors hover:border-primary-400 hover:bg-primary-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-primary-500 dark:hover:bg-primary-900/10"
            >
              <Icon className="h-6 w-6 text-primary-600 dark:text-primary-400" aria-hidden="true" />
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {title}
              </span>
              <span className="text-xs text-gray-600 dark:text-gray-400">
                {blurb}
              </span>
              <span className="mt-auto text-xs font-medium text-primary-600 group-hover:text-primary-700 dark:text-primary-400">
                Open walkthrough →
              </span>
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={handleSeeAll}
            className="text-sm text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 self-start"
          >
            See all 6 tutorials →
          </button>
          <Button variant="secondary" onClick={handleDismiss} className="sm:self-end">
            Got it
          </Button>
        </div>
      </div>
    </Modal>
  );
}
