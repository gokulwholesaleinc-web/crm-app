import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor } from '../../utils/colorValidation';
import { formatDate } from '../../utils/formatters';

// Bare axios instance for public (unauthenticated) contract endpoints.
// Deliberately does NOT attach the CRM Bearer token — customers clicking
// a contract link aren't logged in.
const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

interface ContractBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  footer_text: string | null;
  privacy_policy_url: string | null;
  terms_of_service_url: string | null;
}

interface PublicContract {
  id: number;
  title: string;
  scope: string | null;
  value: number | null;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  company_name: string | null;
  contact_name: string | null;
  signer_email: string | null;
  expires_at: string | null;
  signed_at: string | null;
  signed_by_name: string | null;
  branding: ContractBranding;
}

const DEFAULT_BRANDING: ContractBranding = {
  company_name: null,
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  footer_text: null,
  privacy_policy_url: null,
  terms_of_service_url: null,
};

function formatContractValue(value: number | null, currency: string): string | null {
  if (value == null) return null;
  const sym = ({ USD: '$', EUR: '€', GBP: '£', CAD: '$', AUD: '$' } as Record<string, string>)[currency.toUpperCase()] ?? '';
  const num = value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return sym ? `${sym}${num}` : `${currency} ${num}`;
}

// Inline signature canvas — native canvas + pointer events; no extra deps.
function SignatureCanvas({
  canvasRef,
  disabled,
}: {
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  disabled: boolean;
}) {
  const drawing = useRef(false);

  const getPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const { x, y } = getPos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current || disabled) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const { x, y } = getPos(e);
    ctx.lineTo(x, y);
    ctx.stroke();
  };

  const onUp = () => { drawing.current = false; };

  return (
    <canvas
      ref={canvasRef}
      width={480}
      height={160}
      aria-label="Signature pad — draw your signature"
      style={{ display: 'block', touchAction: 'none', cursor: disabled ? 'default' : 'crosshair' }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerLeave={onUp}
    />
  );
}

export default function PublicContractView() {
  const { token } = useParams<{ token: string }>();
  const [contract, setContract] = useState<PublicContract | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signerName, setSignerName] = useState('');
  const [signError, setSignError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState(false);
  const [logoError, setLogoError] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => { setLogoError(false); }, [contract?.branding?.logo_url]);

  // Initialise canvas context once mounted
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 1.8;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }, []);

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx?.clearRect(0, 0, canvas.width, canvas.height);
  };

  const isCanvasEmpty = (): boolean => {
    const canvas = canvasRef.current;
    if (!canvas) return true;
    const ctx = canvas.getContext('2d');
    if (!ctx) return true;
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    return !data.some((v, i) => i % 4 === 3 && v > 0);
  };

  const fetchContract = useCallback(async () => {
    if (!token) return;
    try {
      const res = await publicClient.get<PublicContract>(`/api/contracts/public/${token}`);
      setContract(res.data);
    } catch {
      setError('Contract not found or this signing link is no longer valid.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchContract(); }, [fetchContract]);

  const handleSign = async () => {
    if (!contract) return;
    const name = signerName.trim();
    if (!name) {
      setSignError('Please enter your full name.');
      return;
    }
    if (isCanvasEmpty()) {
      setSignError('Please draw your signature before submitting.');
      return;
    }
    const dataUrl = canvasRef.current!.toDataURL('image/png');

    setActionPending(true);
    setSignError(null);
    try {
      await publicClient.post(`/api/contracts/public/${token}/sign`, {
        signer_name: name,
        signer_email: contract.signer_email,
        signature_data_url: dataUrl,
      });
      setActionDone(true);
      setContract((prev) =>
        prev ? { ...prev, status: 'signed', signed_at: new Date().toISOString(), signed_by_name: name } : null
      );
    } catch (err) {
      const detail =
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) || 'Unable to record signature. Please contact your account manager.';
      setSignError(detail);
    } finally {
      setActionPending(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div role="status" aria-label="Loading contract…" className="animate-pulse text-center">
          <div className="h-7 w-40 bg-gray-200 rounded mx-auto mb-3" />
          <div className="h-3 w-24 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !contract) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Contract not found</h1>
          <p className="text-sm text-gray-500 leading-relaxed">
            {error || 'This contract may have been withdrawn or the link is no longer valid. Please contact your account manager.'}
          </p>
        </div>
      </div>
    );
  }

  const rawBranding = contract.branding ?? DEFAULT_BRANDING;
  const branding = {
    ...rawBranding,
    primary_color: sanitizeHexColor(rawBranding.primary_color, DEFAULT_BRANDING.primary_color),
    secondary_color: sanitizeHexColor(rawBranding.secondary_color, DEFAULT_BRANDING.secondary_color),
    accent_color: sanitizeHexColor(rawBranding.accent_color, DEFAULT_BRANDING.accent_color),
  };
  const companyDisplayName = branding.company_name || contract.company_name || 'Contract';
  const primary = branding.primary_color;
  const accent = branding.accent_color;

  const now = new Date();
  const isExpired = contract.expires_at ? new Date(contract.expires_at) < now : false;
  const isAlreadySigned = contract.status === 'signed' || Boolean(contract.signed_at);
  const canSign = !isExpired && !isAlreadySigned && !actionDone && contract.status === 'sent';

  const formattedValue = formatContractValue(contract.value, contract.currency);
  const startDate = contract.start_date ? formatDate(contract.start_date, 'long') : null;
  const endDate = contract.end_date ? formatDate(contract.end_date, 'long') : null;
  const signedDate = contract.signed_at ? formatDate(contract.signed_at, 'long') : null;

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 antialiased">
      <div
        aria-hidden="true"
        style={{ height: 4, backgroundImage: `linear-gradient(90deg, ${primary}, ${accent})` }}
      />

      <header className="bg-white border-b border-gray-200">
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url && !logoError ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                width={180}
                height={30}
                className="object-contain"
                style={{ height: 30, width: 'auto', maxWidth: 180 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <>
                <div
                  className="h-8 w-8 rounded flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold"
                  style={{ backgroundColor: primary }}
                >
                  {companyDisplayName[0]?.toUpperCase() || 'C'}
                </div>
                <span className="text-[15px] font-semibold text-gray-900 truncate">
                  {companyDisplayName}
                </span>
              </>
            )}
          </div>
          <span className="text-xs text-gray-500">Contract</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 sm:px-10 py-10 sm:py-14">
        {/* Cover section */}
        <section className="pb-8 border-b border-gray-200">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">Contract</p>
          <h1 className="text-3xl sm:text-4xl font-semibold text-gray-900 leading-tight tracking-tight">
            {contract.title}
          </h1>
          {contract.contact_name && (
            <p className="mt-3 text-[15px] text-gray-600">
              Prepared for{' '}
              <span className="font-medium text-gray-900">{contract.contact_name}</span>
              {contract.company_name && (
                <span className="text-gray-500"> · {contract.company_name}</span>
              )}
            </p>
          )}
          {(formattedValue || startDate || endDate) && (
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              {formattedValue && (
                <><dt className="text-gray-500">Contract value</dt><dd className="tabular-nums font-medium text-gray-900">{formattedValue}</dd></>
              )}
              {startDate && (
                <><dt className="text-gray-500">Start date</dt><dd className="tabular-nums text-gray-900">{startDate}</dd></>
              )}
              {endDate && (
                <><dt className="text-gray-500">End date</dt><dd className="tabular-nums text-gray-900">{endDate}</dd></>
              )}
            </dl>
          )}
        </section>

        {/* Scope */}
        {contract.scope && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader title="Scope" accent={primary} />
            <p className="text-[15px] leading-[1.7] text-gray-700 whitespace-pre-wrap max-w-[62ch]">
              {contract.scope}
            </p>
          </section>
        )}

        {/* Already signed state */}
        {isAlreadySigned && (
          <section className="mt-10 sm:mt-12 rounded border border-green-200 bg-green-50 px-5 py-4" role="status">
            <div className="flex items-center gap-2.5">
              <CheckIcon className="h-5 w-5 text-green-700 flex-shrink-0" aria-hidden="true" />
              <div>
                <p className="font-semibold text-green-900">Contract signed</p>
                {signedDate && contract.signed_by_name && (
                  <p className="text-sm text-green-800 mt-0.5">
                    Signed on {signedDate} by {contract.signed_by_name}
                  </p>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Expired notice */}
        {isExpired && !isAlreadySigned && (
          <section className="mt-10 sm:mt-12 rounded border border-amber-200 bg-amber-50 px-5 py-4" role="status">
            <p className="text-sm font-medium text-amber-900">
              This signing link has expired. Please contact your account manager for a new link.
            </p>
          </section>
        )}

        {/* Post-sign success */}
        {actionDone && (
          <section
            className="mt-10 sm:mt-12 rounded border border-green-200 bg-green-50 px-5 py-4"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-center gap-2.5">
              <CheckIcon className="h-5 w-5 text-green-700 flex-shrink-0" aria-hidden="true" />
              <div>
                <p className="font-semibold text-green-900">Contract signed — thank you</p>
                <p className="text-sm text-green-800 mt-0.5">
                  A signed copy will be emailed to you shortly for your records.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Signature form */}
        {canSign && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader title="Sign Contract" accent={primary} />
            <p className="text-[15px] leading-[1.7] text-gray-700 mb-6 max-w-[62ch]">
              Please review the contract above, then enter your full name and draw your
              signature to sign electronically.
            </p>

            <div className="mb-4">
              <label htmlFor="signer-name" className="block text-sm font-medium text-gray-700 mb-1">
                Full name
              </label>
              <input
                id="signer-name"
                type="text"
                autoComplete="name"
                value={signerName}
                onChange={(e) => setSignerName(e.target.value)}
                disabled={actionPending}
                className="w-full rounded border border-gray-300 bg-white text-sm text-gray-900 px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50 max-w-sm"
                style={{ outlineColor: primary }}
              />
            </div>

            {contract.signer_email && (
              <div className="mb-6">
                <label htmlFor="signer-email" className="block text-sm font-medium text-gray-700 mb-1">
                  Email address
                </label>
                <input
                  id="signer-email"
                  type="email"
                  value={contract.signer_email}
                  disabled
                  readOnly
                  className="w-full rounded border border-gray-200 bg-gray-50 text-sm text-gray-500 px-3 py-2 shadow-sm max-w-sm"
                />
              </div>
            )}

            <div className="mb-2">
              <p className="text-sm font-medium text-gray-700 mb-2">Signature</p>
              <div
                className="rounded border border-gray-300 bg-white overflow-hidden"
                style={{ maxWidth: 480 }}
              >
                <SignatureCanvas canvasRef={canvasRef} disabled={actionPending} />
              </div>
              <button
                type="button"
                onClick={clearCanvas}
                disabled={actionPending}
                className="mt-1 text-xs text-gray-500 hover:text-gray-700 underline"
              >
                Clear
              </button>
            </div>

            {signError && (
              <p role="alert" aria-live="polite" className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
                {signError}
              </p>
            )}

            <button
              type="button"
              onClick={handleSign}
              disabled={actionPending}
              className="mt-4 inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
              style={{ backgroundColor: accent, outlineColor: accent }}
            >
              <CheckIcon className="h-4 w-4" aria-hidden="true" />
              {actionPending ? 'Recording…' : 'Sign Contract'}
            </button>
          </section>
        )}
      </main>

      {/* ESIGN disclosure footer */}
      <footer
        className="mt-16 bg-white border-t border-gray-200"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 space-y-5">
          <details className="group text-sm">
            <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900 list-none flex items-center gap-2 select-none">
              <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">▸</span>
              Electronic signature disclosure &amp; consent
            </summary>
            <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-gray-600">
              <p>
                By entering your name, drawing your signature, and selecting{' '}
                <em>Sign Contract</em>, you agree that this constitutes your legally binding
                electronic signature under the US ESIGN Act (15 USC §7001) and applicable state
                UETA statutes, with the same legal effect as a handwritten signature.
              </p>
              <p>
                You consent to receive this contract and the countersigned PDF copy
                electronically. A signed copy is emailed to the address on record after signing.
                You may withdraw consent by contacting {companyDisplayName} directly — this does
                not retroactively invalidate signatures already captured.
              </p>
              <p>
                We record your name, IP address, browser user-agent, and timestamp at
                submission. This audit trail is retained alongside the contract for dispute
                resolution.
              </p>
            </div>
          </details>

          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pt-4 border-t border-gray-200">
            <div>
              <p className="text-sm font-semibold text-gray-900">{companyDisplayName}</p>
              {branding.footer_text && (
                <p className="text-xs text-gray-500 leading-relaxed max-w-sm">{branding.footer_text}</p>
              )}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              {branding.terms_of_service_url && (
                <a href={branding.terms_of_service_url} target="_blank" rel="noopener noreferrer" className="hover:text-gray-700">
                  Terms of Service
                </a>
              )}
              {branding.privacy_policy_url && (
                <a href={branding.privacy_policy_url} target="_blank" rel="noopener noreferrer" className="hover:text-gray-700">
                  Privacy Policy
                </a>
              )}
            </div>
          </div>
        </div>
      </footer>

      <style>{`details > summary::-webkit-details-marker { display: none; }`}</style>
    </div>
  );
}

interface PlainSectionHeaderProps {
  title: string;
  accent: string;
}

function PlainSectionHeader({ title, accent }: PlainSectionHeaderProps) {
  return (
    <div className="mb-4">
      <div className="h-0.5 w-8 mb-3" style={{ backgroundColor: accent }} aria-hidden="true" />
      <h2 className="text-xl font-semibold text-gray-900 tracking-tight">{title}</h2>
    </div>
  );
}
