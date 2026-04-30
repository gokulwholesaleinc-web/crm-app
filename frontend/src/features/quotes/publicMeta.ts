// Helpers for public-facing quote/proposal pages: per-document open-graph tags
// (so Slack/iMessage unfurls show the quote/proposal title instead of the
// generic app title) and a luminance-based text color picker so a tenant who
// sets a pale primary_color doesn't get unreadable white-on-white text.

const META_TAG_NAMES = ['og:title', 'og:description', 'og:type'] as const;
const LINK_REL = 'canonical';

interface PublicMeta {
  title: string;
  description: string;
  type?: 'website' | 'article';
  canonicalUrl?: string;
}

function upsertMeta(name: string, content: string): HTMLMetaElement {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[property="${name}"]`);
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute('property', name);
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', content);
  return tag;
}

function upsertCanonical(href: string): HTMLLinkElement {
  let tag = document.head.querySelector<HTMLLinkElement>(`link[rel="${LINK_REL}"]`);
  if (!tag) {
    tag = document.createElement('link');
    tag.setAttribute('rel', LINK_REL);
    document.head.appendChild(tag);
  }
  tag.setAttribute('href', href);
  return tag;
}

// Set per-page meta and return a cleanup that restores prior content (or
// removes the tags entirely if they didn't previously exist). Designed to be
// used inside a useEffect.
export function setPublicPageMeta({ title, description, type = 'article', canonicalUrl }: PublicMeta): () => void {
  const previous: Array<{ tag: Element; restore: () => void }> = [];
  const created: Element[] = [];

  const trackMeta = (name: string, content: string) => {
    const existing = document.head.querySelector<HTMLMetaElement>(`meta[property="${name}"]`);
    const prevContent = existing?.getAttribute('content') ?? null;
    const tag = upsertMeta(name, content);
    if (existing) {
      previous.push({
        tag,
        restore: () => {
          if (prevContent === null) tag.removeAttribute('content');
          else tag.setAttribute('content', prevContent);
        },
      });
    } else {
      created.push(tag);
    }
  };

  trackMeta('og:title', title);
  trackMeta('og:description', description);
  trackMeta('og:type', type);

  if (canonicalUrl) {
    const existing = document.head.querySelector<HTMLLinkElement>(`link[rel="${LINK_REL}"]`);
    const prevHref = existing?.getAttribute('href') ?? null;
    const tag = upsertCanonical(canonicalUrl);
    if (existing) {
      previous.push({
        tag,
        restore: () => {
          if (prevHref === null) tag.removeAttribute('href');
          else tag.setAttribute('href', prevHref);
        },
      });
    } else {
      created.push(tag);
    }
  }

  return () => {
    for (const { restore } of previous) restore();
    for (const tag of created) tag.remove();
    void META_TAG_NAMES;
  };
}

// Standard relative-luminance calc per WCAG 2.x. Returns a value in [0,1].
function relativeLuminance(hex: string): number {
  const normalized = hex.startsWith('#') ? hex.slice(1) : hex;
  if (normalized.length !== 6) return 0;
  const r = parseInt(normalized.slice(0, 2), 16) / 255;
  const g = parseInt(normalized.slice(2, 4), 16) / 255;
  const b = parseInt(normalized.slice(4, 6), 16) / 255;
  const channel = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

// Pick the higher-contrast text color for a colored surface. The 0.179
// threshold corresponds to where white-on-bg and black-on-bg WCAG contrast
// ratios cross — i.e., it's the standard "is this background light or dark"
// boundary recommended by the W3 WAI working draft.
export function pickReadableText(hex: string): 'white' | 'gray-900' {
  return relativeLuminance(hex) > 0.179 ? 'gray-900' : 'white';
}
