/**
 * Public Terms of Service — linked from the Google OAuth consent screen and
 * the sign-in page. No-auth; depends on no app providers.
 */
import LegalLayout, { Section } from './LegalLayout';
import { APP_URL, COMPANY_NAME, GOVERNING_LAW, LEGAL_EMAIL, LEGAL_ENTITY } from './companyInfo';

export default function TermsOfServicePage() {
  return (
    <LegalLayout
      title="Terms of Service"
      intro={
        <p>
          These Terms of Service ("Terms") govern access to and use of the customer
          relationship management application (the "CRM" or "Service") provided by{' '}
          {LEGAL_ENTITY} ("{COMPANY_NAME}," "we," "us") at{' '}
          <a className="text-indigo-600 hover:underline" href={APP_URL}>
            {APP_URL.replace('https://', '')}
          </a>
          . By accessing or using the CRM, you ("you," "user") agree to these Terms.
        </p>
      }
    >
      <Section title="1. The Service">
        <p>
          The CRM is a business application for managing client relationships, proposals,
          onboarding, documents, and related communications. It is provided to {COMPANY_NAME}
          's authorized users and is not a public/consumer product.
        </p>
      </Section>

      <Section title="2. Eligibility and accounts">
        <p>
          Access is limited to users authorized by {COMPANY_NAME}. You are responsible for
          maintaining the confidentiality of your credentials and for all activity under
          your account. Notify us promptly of any unauthorized use.
        </p>
      </Section>

      <Section title="3. Acceptable use">
        <p>
          You agree not to: use the Service unlawfully; access data you are not authorized
          to access; attempt to disrupt, reverse engineer, or compromise the Service; or
          use it to send unsolicited or unlawful communications.
        </p>
      </Section>

      <Section title="4. Connecting a Google account">
        <p>
          If you connect a Google/Gmail account, you authorize the CRM to access it within
          the scopes you approve, solely to provide the email features described in our
          Privacy Policy. Your use of Google services remains subject to Google's own
          terms. You may revoke access at any time via the CRM or your Google account
          settings.
        </p>
      </Section>

      <Section title="5. Customer data and content">
        <p>
          As between you and {COMPANY_NAME}, the business data entered into the CRM belongs
          to {COMPANY_NAME} and/or its clients. You are responsible for ensuring you have
          the right to upload and process any data (including third-party personal data)
          you put into the CRM, and to do so in compliance with applicable law.
        </p>
      </Section>

      <Section title="6. Intellectual property">
        <p>
          The CRM software, design, and content (excluding your business data) are owned by
          {COMPANY_NAME} or its licensors. These Terms grant you a limited, revocable,
          non-transferable right to use the Service for its intended purpose.
        </p>
      </Section>

      <Section title="7. Disclaimers">
        <p>
          The Service is provided "as is" and "as available," without warranties of any
          kind, express or implied, including merchantability, fitness for a particular
          purpose, and non-infringement, to the fullest extent permitted by law.
        </p>
      </Section>

      <Section title="8. Limitation of liability">
        <p>
          To the maximum extent permitted by law, {COMPANY_NAME} will not be liable for any
          indirect, incidental, special, consequential, or punitive damages, or any loss of
          data, profits, or revenue, arising from or related to your use of the Service.
        </p>
      </Section>

      <Section title="9. Termination">
        <p>
          We may suspend or terminate access at any time, including for violation of these
          Terms. Upon termination, your right to use the Service ends; sections that by
          their nature should survive (e.g., intellectual property, disclaimers, liability)
          will survive.
        </p>
      </Section>

      <Section title="10. Governing law">
        <p>These Terms are governed by {GOVERNING_LAW}, without regard to conflict-of-laws rules.</p>
      </Section>

      <Section title="11. Changes">
        <p>
          We may update these Terms from time to time; we will revise the "Last updated"
          date and, where appropriate, provide notice. Continued use after changes means
          you accept the updated Terms.
        </p>
      </Section>

      <Section title="12. Contact">
        <p>
          Questions:{' '}
          <a className="text-indigo-600 hover:underline" href={`mailto:${LEGAL_EMAIL}`}>
            {LEGAL_EMAIL}
          </a>{' '}
          ({LEGAL_ENTITY}).
        </p>
      </Section>
    </LegalLayout>
  );
}
