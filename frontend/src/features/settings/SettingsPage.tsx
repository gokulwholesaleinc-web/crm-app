/**
 * Settings page with sticky left-side section nav. Each top-level
 * section gets an anchor id so deep links (`/settings#integrations`)
 * still resolve to the right section. Active section is tracked via
 * IntersectionObserver — the deepest section whose top has crossed the
 * viewport's midline wins.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Avatar } from '../../components/ui/Avatar';
import { Spinner } from '../../components/ui/Spinner';
import { Button } from '../../components/ui/Button';
import {
  Cog6ToothIcon,
  BellIcon,
  ShieldCheckIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline';
import { EditProfileModal } from './components/EditProfileModal';
import { BrandingSection } from './components/BrandingSection';
import { AIPreferencesSection } from './components/AIPreferencesSection';
import { PipelineStagesSection } from './components/PipelineStagesSection';
import { LeadSourcesSection } from './components/LeadSourcesSection';
import { WebhooksSection } from './components/WebhooksSection';
import { AssignmentRulesSection } from './components/AssignmentRulesSection';
import { RolesSection } from './components/RolesSection';
import { IntegrationsSection } from './components/IntegrationsSection';
import { EmailSettingsSection } from './components/EmailSettingsSection';

interface NavItem {
  id: string;
  label: string;
}

// Order here drives both the sidebar order and the body order. Keep in
// sync if you reorder sections in the JSX below.
const NAV_ITEMS: readonly NavItem[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'branding', label: 'Branding' },
  { id: 'ai-preferences', label: 'AI Preferences' },
  { id: 'pipeline-stages', label: 'Pipeline Stages' },
  { id: 'lead-sources', label: 'Lead Sources' },
  // IntegrationsSection owns its own `id="integrations"` — link target
  // resolves to that inner div so legacy deep links keep working.
  { id: 'integrations', label: 'Integrations' },
  { id: 'email-settings', label: 'Email Settings' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'roles', label: 'Roles & Permissions' },
  { id: 'assignment-rules', label: 'Auto-Assignment' },
  { id: 'account-settings', label: 'Account Settings' },
  { id: 'account-status', label: 'Account Status' },
] as const;

function SettingsPage() {
  const { user, isLoading } = useAuthStore();
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const { hash } = useLocation();
  const [activeSection, setActiveSection] = useState<string>(NAV_ITEMS[0]?.id ?? 'profile');

  // Refs per section, keyed by id. Used both for IntersectionObserver
  // tracking and for the deep-link scroll on hash change.
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const setSectionRef = useMemo(
    () => (id: string) => (el: HTMLElement | null) => {
      sectionRefs.current[id] = el;
    },
    [],
  );

  // Deep-link scroll: when ?#section is in the URL, scroll to it once
  // we've finished loading the user (so layout has settled).
  useEffect(() => {
    if (isLoading || !hash) return;
    const id = hash.slice(1);
    const target = document.getElementById(id);
    if (!target) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'start',
    });
    setActiveSection(id);
  }, [hash, isLoading]);

  // Track which section the reader is on. We pick the *last* section
  // whose top has crossed below the viewport's mid-line — that
  // matches reading direction and avoids the "section above me is
  // briefly highlighted on scroll-down" jitter that a naive top-edge
  // observer produces.
  useEffect(() => {
    if (isLoading) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .map((e) => e.target.id)
          .filter(Boolean);
        if (visible.length === 0) return;
        // Last in DOM order wins (deepest scrolled-to section).
        setActiveSection((prev) => {
          const navIndex = NAV_ITEMS.findIndex((n) => n.id === prev);
          let candidate = prev;
          let candidateIndex = navIndex;
          for (const id of visible) {
            const idx = NAV_ITEMS.findIndex((n) => n.id === id);
            if (idx > candidateIndex) {
              candidate = id;
              candidateIndex = idx;
            }
          }
          return candidate;
        });
      },
      // Trigger when the section's top crosses ~30% of the viewport
      // from the top. Negative bottom margin pulls the trigger zone
      // up so we don't activate a section that's mostly off-screen.
      { rootMargin: '-30% 0px -55% 0px', threshold: 0 },
    );
    Object.values(sectionRefs.current).forEach((el) => {
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [isLoading]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const handleNavClick = (id: string) => (event: React.MouseEvent<HTMLAnchorElement>) => {
    // Preserve Cmd/Ctrl-click for "open in new tab" — let the browser handle it.
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    const target = document.getElementById(id) ?? sectionRefs.current[id];
    if (!target) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'start',
    });
    // Update the URL hash without reload so the deep-link is shareable.
    window.history.replaceState(null, '', `#${id}`);
    setActiveSection(id);
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Manage your account settings and preferences
        </p>
      </div>

      {/* Mobile: Jump-to selector. On a phone the sidebar is suppressed
          so a quick selector keeps deep navigation cheap. */}
      <div className="lg:hidden">
        <label htmlFor="settings-jump" className="sr-only">
          Jump to section
        </label>
        <select
          id="settings-jump"
          className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500"
          value={activeSection}
          onChange={(e) => {
            const id = e.target.value;
            const target = document.getElementById(id) ?? sectionRefs.current[id];
            if (!target) return;
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            target.scrollIntoView({
              behavior: prefersReducedMotion ? 'auto' : 'smooth',
              block: 'start',
            });
            window.history.replaceState(null, '', `#${id}`);
            setActiveSection(id);
          }}
        >
          {NAV_ITEMS.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <div className="lg:flex lg:gap-8">
        {/* Sidebar nav — desktop only. Sticky so it stays visible while
            the user scrolls through long sections. */}
        <nav
          aria-label="Settings sections"
          className="hidden lg:block lg:w-56 lg:flex-shrink-0"
        >
          <ul
            className="sticky top-6 space-y-1 border-l border-gray-200 dark:border-gray-700"
          >
            {NAV_ITEMS.map((item) => {
              const isActive = item.id === activeSection;
              return (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    onClick={handleNavClick(item.id)}
                    aria-current={isActive ? 'true' : undefined}
                    className={[
                      'block -ml-px border-l-2 px-3 py-1.5 text-sm transition-colors',
                      isActive
                        ? 'border-primary-600 text-primary-700 dark:border-primary-400 dark:text-primary-300 font-medium'
                        : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600',
                    ].join(' ')}
                  >
                    {item.label}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex-1 min-w-0 space-y-4 sm:space-y-6 mt-4 lg:mt-0">
          {/* Profile */}
          <section
            id="profile"
            ref={setSectionRef('profile')}
            className="scroll-mt-6"
          >
            <Card>
              <CardHeader
                title="Profile"
                description="Your personal information"
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    leftIcon={<PencilSquareIcon className="h-4 w-4" />}
                    onClick={() => setIsEditModalOpen(true)}
                  >
                    Edit
                  </Button>
                }
              />
              <CardBody className="p-4 sm:p-6">
                <div className="flex flex-col sm:flex-row sm:items-start gap-4 sm:space-x-6">
                  <div className="flex justify-center sm:justify-start">
                    <Avatar
                      src={user?.avatar_url}
                      name={user?.full_name}
                      size="xl"
                    />
                  </div>
                  <div className="flex-1 space-y-4">
                    <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
                      <div>
                        <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                          Full Name
                        </label>
                        <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                          {user?.full_name || 'Not set'}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                          Email
                        </label>
                        <p className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-all">
                          {user?.email || 'Not set'}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                          Phone
                        </label>
                        <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                          {user?.phone || 'Not set'}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                          Job Title
                        </label>
                        <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                          {user?.job_title || 'Not set'}
                        </p>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">
                        Member Since
                      </label>
                      <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                        {user?.created_at
                          ? new Date(user.created_at).toLocaleDateString(undefined, {
                              year: 'numeric',
                              month: 'long',
                              day: 'numeric',
                            })
                          : 'Unknown'}
                      </p>
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>
          </section>

          {/* Edit Profile Modal */}
          {user && (
            <EditProfileModal
              isOpen={isEditModalOpen}
              onClose={() => setIsEditModalOpen(false)}
              initialData={{
                full_name: user.full_name || '',
                email: user.email || '',
                phone: user.phone || '',
                job_title: user.job_title || '',
              }}
            />
          )}

          <section id="branding" ref={setSectionRef('branding')} className="scroll-mt-6">
            <BrandingSection />
          </section>

          <section
            id="ai-preferences"
            ref={setSectionRef('ai-preferences')}
            className="scroll-mt-6"
          >
            <AIPreferencesSection />
          </section>

          <section
            id="pipeline-stages"
            ref={setSectionRef('pipeline-stages')}
            className="scroll-mt-6"
          >
            <PipelineStagesSection />
          </section>

          <section
            id="lead-sources"
            ref={setSectionRef('lead-sources')}
            className="scroll-mt-6"
          >
            <LeadSourcesSection />
          </section>

          {/* IntegrationsSection holds its own id="integrations" inside,
              which is what existing /settings#integrations links target.
              We attach the ref to a *wrapper without an id* so the
              IntersectionObserver still tracks it without creating a
              duplicate-id conflict. */}
          <section ref={setSectionRef('integrations')} className="scroll-mt-6">
            <IntegrationsSection />
          </section>

          <section
            id="email-settings"
            ref={setSectionRef('email-settings')}
            className="scroll-mt-6"
          >
            <EmailSettingsSection />
          </section>

          <section id="webhooks" ref={setSectionRef('webhooks')} className="scroll-mt-6">
            <WebhooksSection />
          </section>

          <section id="roles" ref={setSectionRef('roles')} className="scroll-mt-6">
            <RolesSection />
          </section>

          <section
            id="assignment-rules"
            ref={setSectionRef('assignment-rules')}
            className="scroll-mt-6"
          >
            <AssignmentRulesSection />
          </section>

          <section
            id="account-settings"
            ref={setSectionRef('account-settings')}
            className="scroll-mt-6"
          >
            <Card>
              <CardHeader
                title="Account Settings"
                description="Manage your account preferences"
              />
              <CardBody className="p-4 sm:p-6">
                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                  {/* Notification Settings */}
                  <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
                    <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                      <div className="flex-shrink-0">
                        <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                          <BellIcon className="h-4 w-4 sm:h-5 sm:w-5 text-blue-600 dark:text-blue-400" />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          Notifications
                        </p>
                        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                          Configure email and push notification preferences
                        </p>
                      </div>
                      <div className="text-xs sm:text-sm text-gray-400 dark:text-gray-500 flex-shrink-0">Coming soon</div>
                    </div>
                  </div>

                  {/* Security Settings */}
                  <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
                    <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                      <div className="flex-shrink-0">
                        <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                          <ShieldCheckIcon className="h-4 w-4 sm:h-5 sm:w-5 text-green-600 dark:text-green-400" />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          Security
                        </p>
                        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                          Password, two-factor authentication, and sessions
                        </p>
                      </div>
                      <div className="text-xs sm:text-sm text-gray-400 dark:text-gray-500 flex-shrink-0">Coming soon</div>
                    </div>
                  </div>

                  {/* Preferences */}
                  <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
                    <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                      <div className="flex-shrink-0">
                        <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
                          <Cog6ToothIcon className="h-4 w-4 sm:h-5 sm:w-5 text-purple-600 dark:text-purple-400" />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          Preferences
                        </p>
                        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                          Language, timezone, and display settings
                        </p>
                      </div>
                      <div className="text-xs sm:text-sm text-gray-400 dark:text-gray-500 flex-shrink-0">Coming soon</div>
                    </div>
                  </div>

                </div>
              </CardBody>
            </Card>
          </section>

          <section
            id="account-status"
            ref={setSectionRef('account-status')}
            className="scroll-mt-6"
          >
            <Card>
              <CardHeader
                title="Account Status"
                description="Your account information"
              />
              <CardBody className="p-4 sm:p-6">
                <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 sm:p-4">
                    <p className="text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">Status</p>
                    <p className="mt-1 flex items-center text-sm text-gray-900 dark:text-gray-100">
                      <span
                        className={`inline-block h-2 w-2 rounded-full mr-2 ${
                          user?.is_active ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      />
                      {user?.is_active ? 'Active' : 'Inactive'}
                    </p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 sm:p-4">
                    <p className="text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">Role</p>
                    <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                      {user?.is_superuser ? 'Administrator' : 'User'}
                    </p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 sm:p-4">
                    <p className="text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400">Last Login</p>
                    <p className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                      {user?.last_login
                        ? new Date(user.last_login).toLocaleDateString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : 'Never'}
                    </p>
                  </div>
                </div>
              </CardBody>
            </Card>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
