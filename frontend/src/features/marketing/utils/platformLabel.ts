/** Human labels for the warehouse `platform` discriminator — one source of truth
 *  so the tab header, allocation donut, and breakdown table agree (incl. Meta). */
export const PLATFORM_LABEL: Record<string, string> = {
  google_ads: 'Google Ads',
  ga4: 'GA4',
  gsc: 'Search Console',
  pagespeed: 'PageSpeed',
  meta_ads: 'Meta',
  instagram: 'Instagram',
  facebook: 'Facebook',
  tiktok: 'TikTok',
  linkedin: 'LinkedIn',
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABEL[platform] ?? platform;
}
