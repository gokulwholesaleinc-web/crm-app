import { OnboardingPacketList } from './OnboardingPacketList';

interface ContactOnboardingTabProps {
  contactId: number;
}

/**
 * The contact-page Onboarding tab (D2): the contact's onboarding packets —
 * status, delivery, link recovery, resend, revoke — plus the files the client
 * uploaded. Thin wrapper over the shared {@link OnboardingPacketList} so the
 * packet toolkit stays identical to the staff send panel.
 */
export function ContactOnboardingTab({ contactId }: ContactOnboardingTabProps) {
  return (
    <section className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700 p-5 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Onboarding</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Onboarding packets sent to this contact — status, link recovery, resend, and the files
          the client uploaded. Send a new packet from the Onboarding page.
        </p>
      </div>
      <OnboardingPacketList contactId={contactId} />
    </section>
  );
}

export default ContactOnboardingTab;
