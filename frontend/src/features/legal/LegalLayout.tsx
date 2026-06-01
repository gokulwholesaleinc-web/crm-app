/**
 * Public, no-auth layout for the Privacy Policy and Terms of Service pages.
 *
 * These pages must render for anyone (incl. Google's OAuth reviewer hitting
 * the URL directly), so they depend on NO app providers or auth — just the
 * router for in-app links.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { COMPANY_NAME, LAST_UPDATED } from './companyInfo';

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-6 text-gray-700">{children}</div>
    </section>
  );
}

export default function LegalLayout({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <main className="mx-auto max-w-3xl px-5 py-12 sm:py-16">
        <p className="text-sm font-medium text-gray-500">{COMPANY_NAME}</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-balance">{title}</h1>
        <p className="mt-2 text-sm text-gray-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
          Last updated: {LAST_UPDATED}
        </p>
        {intro && <div className="mt-5 text-sm leading-6 text-gray-700">{intro}</div>}

        {children}

        <footer className="mt-12 border-t border-gray-200 pt-6 text-sm text-gray-500">
          <nav className="flex flex-wrap gap-x-6 gap-y-2">
            <Link className="hover:text-gray-900 hover:underline" to="/privacy">
              Privacy Policy
            </Link>
            <Link className="hover:text-gray-900 hover:underline" to="/terms">
              Terms of Service
            </Link>
            <Link className="hover:text-gray-900 hover:underline" to="/login">
              Back to sign in
            </Link>
          </nav>
          <p className="mt-4">
            © {new Date().getFullYear()} {COMPANY_NAME}. All rights reserved.
          </p>
        </footer>
      </main>
    </div>
  );
}
