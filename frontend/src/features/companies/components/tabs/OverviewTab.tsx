import { Link, useNavigate } from 'react-router-dom';
import {
  GlobeAltIcon,
  EnvelopeIcon,
  PhoneIcon,
  MapPinIcon,
  UsersIcon,
  LinkIcon,
  DocumentTextIcon,
  UserCircleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../../../components/ui/Button';
import { Spinner } from '../../../../components/ui/Spinner';
import { formatCurrency, formatDate } from '../../../../utils/formatters';
import clsx from 'clsx';
import type { Contact, Company } from '../../../../types';

function DetailItem({
  icon: Icon,
  label,
  value,
  link,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | null | undefined;
  link?: string;
}) {
  if (!value) return null;

  const content = (
    <div className="flex items-start gap-3 py-2">
      <Icon className="h-5 w-5 text-gray-400 mt-0.5" />
      <div>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
        <p className={clsx('text-sm text-gray-900 dark:text-gray-100', link && 'hover:text-primary-600')}>{value}</p>
      </div>
    </div>
  );

  if (link) {
    return (
      <a href={link} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    );
  }

  return content;
}

function ContactRow({ contact }: { contact: Contact }) {
  return (
    <Link
      to={`/contacts/${contact.id}`}
      className="flex flex-col gap-2 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors sm:flex-row sm:items-center sm:gap-4"
    >
      <div className="flex items-center gap-3 sm:gap-4">
        {contact.avatar_url ? (
          <img
            src={contact.avatar_url}
            alt={contact.full_name}
            width={40}
            height={40}
            className="h-10 w-10 rounded-full object-cover flex-shrink-0"
          />
        ) : (
          <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-medium text-gray-600 dark:text-gray-300">
              {contact.first_name[0]}
              {contact.last_name[0]}
            </span>
          </div>
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{contact.full_name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {contact.job_title || 'No title'}
            {contact.department && ` - ${contact.department}`}
          </p>
        </div>
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400 pl-13 sm:pl-0 sm:ml-auto sm:text-right">
        {contact.email && <p className="truncate">{contact.email}</p>}
        {contact.phone && <p>{contact.phone}</p>}
      </div>
    </Link>
  );
}

interface OverviewTabProps {
  company: Company;
  contacts: Contact[];
  isLoadingContacts: boolean;
  companyId: number;
}

export function OverviewTab({ company, contacts, isLoadingContacts, companyId }: OverviewTabProps) {
  const navigate = useNavigate();

  const fullAddress = [
    company.address_line1,
    company.address_line2,
    [company.city, company.state].filter(Boolean).join(', '),
    company.postal_code,
    company.country,
  ]
    .filter(Boolean)
    .join('\n');

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        {company.description && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">About</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">{company.description}</p>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700">
          <div className="px-4 py-4 border-b dark:border-gray-700 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Contacts ({contacts.length})
            </h3>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/contacts?company_id=${companyId}&action=new`)}
              className="w-full sm:w-auto"
            >
              Add Contact
            </Button>
          </div>
          {isLoadingContacts ? (
            <div className="flex items-center justify-center py-8">
              <Spinner />
            </div>
          ) : contacts.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <UsersIcon className="mx-auto h-8 w-8 text-gray-400 mb-2" />
              <p>No contacts associated with this company</p>
            </div>
          ) : (
            <div className="divide-y dark:divide-gray-700">
              {contacts.map((contact) => (
                <ContactRow key={contact.id} contact={contact} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Contact Information</h3>
          <div className="space-y-1">
            <DetailItem
              icon={GlobeAltIcon}
              label="Website"
              value={company.website?.replace(/^https?:\/\//, '')}
              link={company.website || undefined}
            />
            <DetailItem
              icon={EnvelopeIcon}
              label="Email"
              value={company.email}
              link={company.email ? `mailto:${company.email}` : undefined}
            />
            <DetailItem
              icon={PhoneIcon}
              label="Phone"
              value={company.phone}
              link={company.phone ? `tel:${company.phone}` : undefined}
            />
            {fullAddress && (
              <DetailItem icon={MapPinIcon} label="Address" value={fullAddress} />
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Business Details</h3>
          <div className="space-y-3">
            {company.annual_revenue && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500 dark:text-gray-400">Annual Revenue</span>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {formatCurrency(company.annual_revenue)}
                </span>
              </div>
            )}
            {company.employee_count && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500 dark:text-gray-400">Employees</span>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {company.employee_count.toLocaleString()}
                </span>
              </div>
            )}
            {company.company_size && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500 dark:text-gray-400">Company Size</span>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{company.company_size}</span>
              </div>
            )}
          </div>
        </div>

        {(company.link_creative_tier || company.sow_url || company.account_manager) && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Account & Creative</h3>
            <div className="space-y-1">
              <DetailItem
                icon={SparklesIcon}
                label="Link Creative Tier"
                value={company.link_creative_tier ? `Tier ${company.link_creative_tier}` : null}
              />
              <DetailItem
                icon={UserCircleIcon}
                label="Account Manager"
                value={company.account_manager}
              />
              <DetailItem
                icon={DocumentTextIcon}
                label="SOW"
                value={company.sow_url ? 'View SOW' : null}
                link={company.sow_url || undefined}
              />
            </div>
          </div>
        )}

        {(company.linkedin_url || company.twitter_handle) && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Social Links</h3>
            <div className="space-y-2">
              {company.linkedin_url && (
                <a
                  href={company.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400"
                >
                  <LinkIcon className="h-4 w-4" />
                  LinkedIn
                </a>
              )}
              {company.twitter_handle && (
                <a
                  href={`https://twitter.com/${company.twitter_handle.replace('@', '')}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400"
                >
                  <LinkIcon className="h-4 w-4" />
                  {company.twitter_handle}
                </a>
              )}
            </div>
          </div>
        )}

        {company.tags && company.tags.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Tags</h3>
            <div className="flex flex-wrap gap-2">
              {company.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="text-xs px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                  style={tag.color ? { backgroundColor: `${tag.color}20`, color: tag.color } : undefined}
                >
                  {tag.name}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">Record Info</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-gray-500 dark:text-gray-400">Created</span>
              <span className="text-gray-900 dark:text-gray-100">{formatDate(company.created_at, 'long')}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500 dark:text-gray-400">Last Updated</span>
              <span className="text-gray-900 dark:text-gray-100">{formatDate(company.updated_at, 'long')}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
