/**
 * Public Privacy Policy — linked from the Google OAuth consent screen and the
 * sign-in page. Covers the Google sign-in + Gmail scopes the CRM requests and
 * includes the Google API Services User Data Policy "Limited Use" affirmation
 * (which OAuth reviewers specifically check for).
 */
import LegalLayout, { Section } from './LegalLayout';
import { APP_URL, COMPANY_ADDRESS, COMPANY_NAME, LEGAL_ENTITY, PRIVACY_EMAIL } from './companyInfo';

export default function PrivacyPolicyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      intro={
        <p>
          This Privacy Policy explains how {LEGAL_ENTITY} ("{COMPANY_NAME}," "we," "us")
          collects, uses, and protects information in connection with our customer
          relationship management application (the "CRM" or "Service"), available at{' '}
          <a className="text-indigo-600 hover:underline" href={APP_URL}>
            {APP_URL.replace('https://', '')}
          </a>
          . The CRM is a business application used by {COMPANY_NAME} and its authorized
          users to manage client relationships, proposals, onboarding, and communications.
        </p>
      }
    >
      <Section title="1. Information we collect">
        <p>
          <strong>Information you put into the CRM.</strong> Contact and company records,
          leads, proposals, onboarding documents, notes, activities, attachments, and
          similar business data you create or upload.
        </p>
        <p>
          <strong>Account and authentication data.</strong> Your name, email address, and
          login credentials (or Google sign-in identifiers), plus security/audit metadata
          such as timestamps, IP address, and browser user-agent.
        </p>
        <p>
          <strong>Google account data (only if you connect Google).</strong> When you sign
          in with Google or connect a Gmail account, we request only these scopes:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <code>openid</code>, <code>email</code>, <code>profile</code> — to identify you
            and create/secure your CRM account.
          </li>
          <li>
            <code>gmail.send</code> — to send emails from your connected Gmail address on
            your behalf from within the CRM.
          </li>
          <li>
            <code>gmail.readonly</code> — to read message metadata/content so the CRM can
            log and associate your business emails with the matching CRM records.
          </li>
        </ul>
        <p>
          We store the OAuth tokens needed to provide these features and the minimum
          message data required to display and associate emails inside the CRM. We do not
          request access to anything beyond the scopes listed above.
        </p>
      </Section>

      <Section title="2. How we use information">
        <p>
          We use the information solely to operate and provide the CRM's features —
          managing your records, sending and logging emails you initiate, generating
          proposals and onboarding documents, securing accounts, and providing support. We
          do not use Google user data for advertising, and we do not sell it.
        </p>
      </Section>

      <Section title="3. Google API Services User Data Policy — Limited Use">
        <p>
          {COMPANY_NAME}'s use and transfer of information received from Google APIs
          adheres to the{' '}
          <a
            className="text-indigo-600 hover:underline"
            href="https://developers.google.com/terms/api-services-user-data-policy"
          >
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements. Specifically:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            We only use Google user data to provide and improve the user-facing features
            that are visible and prominent in the CRM.
          </li>
          <li>
            We do not transfer or sell Google user data to third parties except as
            necessary to provide or improve those features, to comply with applicable law,
            or as part of a merger or acquisition with appropriate protections.
          </li>
          <li>We do not use Google user data for serving advertisements.</li>
          <li>
            We do not allow humans to read Google user data unless (i) you give explicit
            consent for specific messages, (ii) it is necessary for security purposes,
            (iii) it is required to comply with applicable law, or (iv) the data is
            aggregated and anonymized and used for internal operations.
          </li>
        </ul>
      </Section>

      <Section title="4. How we store and protect information">
        <p>
          Data is transmitted over encrypted connections (HTTPS/TLS). The CRM runs on
          managed cloud infrastructure with access restricted to authorized personnel.
          OAuth tokens and sensitive data are stored with access controls, and you can
          revoke the CRM's access to your Google account at any time (see Section 6).
        </p>
      </Section>

      <Section title="5. Service providers">
        <p>
          We rely on trusted providers to run the Service, including Google
          (authentication and the Gmail API), Railway (application hosting), Neon (managed
          PostgreSQL database), and Cloudflare R2 (file storage). These providers process
          data only to provide their services to us.
        </p>
      </Section>

      <Section title="6. Data retention and deletion">
        <p>
          We retain data for as long as needed to operate the CRM or as required by law.
          You may disconnect a Google account at any time from the CRM settings, or revoke
          access directly at{' '}
          <a
            className="text-indigo-600 hover:underline"
            href="https://myaccount.google.com/permissions"
          >
            myaccount.google.com/permissions
          </a>{' '}
          — revoking access stops further Gmail access and we delete the associated OAuth
          tokens. To request deletion of your account data, contact us at the address
          below.
        </p>
      </Section>

      <Section title="7. Your choices and rights">
        <p>
          You may access, correct, or request deletion of your personal data, and
          disconnect Google access, by contacting us or using the in-app settings. We will
          respond consistent with applicable law.
        </p>
      </Section>

      <Section title="8. Children">
        <p>
          The CRM is a business tool not directed to, or intended for use by, anyone under
          16.
        </p>
      </Section>

      <Section title="9. Changes to this policy">
        <p>
          We may update this policy from time to time; we will revise the "Last updated"
          date and, where appropriate, provide notice. Continued use of the CRM after
          changes means you accept the updated policy.
        </p>
      </Section>

      <Section title="10. Contact">
        <p>
          Questions or requests:{' '}
          <a className="text-indigo-600 hover:underline" href={`mailto:${PRIVACY_EMAIL}`}>
            {PRIVACY_EMAIL}
          </a>
          .
        </p>
        <p>
          {LEGAL_ENTITY}, {COMPANY_ADDRESS}.
        </p>
      </Section>
    </LegalLayout>
  );
}
