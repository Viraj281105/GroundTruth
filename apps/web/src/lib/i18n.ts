/**
 * Minimal message catalog. English is the source of truth; a missing key in
 * another locale falls back to English, and a key nobody has returns the key
 * itself (visible, never blank).
 */

export type Locale = 'en' | 'hi' | 'mr';
export const LOCALES: readonly Locale[] = ['en', 'hi', 'mr'];
export const LOCALE_NAMES: Record<Locale, string> = { en: 'English', hi: 'हिन्दी', mr: 'मराठी' };
export const LOCALE_STORAGE_KEY = 'gt-locale';

type Catalog = Record<string, string>;

const en: Catalog = {
  'nav.home': 'Home',
  'nav.cases': 'Cases',
  'nav.workspace': 'Workspace',
  'nav.compare': 'Compare',
  'nav.claims': 'Claims',
  'nav.method': 'Method',
  'nav.status': 'Status',
  'lens.story': 'Story',
  'lens.explorer': 'Explorer',
  'lens.auditor': 'Auditor',
  'theme.light': 'Light',
  'theme.dark': 'Dark',
  'theme.system': 'System',
  'sim.chip': 'Simulated data',
  'sim.explain': 'Every number here comes from a simulated test fixture. No real project has been analysed.',
  'home.cta': 'Explore a case',
  'cases.count': '{n} cases',
  'common.back': 'Back',
  'common.retry': 'Try again',
  'common.loading': 'Loading…',
  'footer.note': 'A divergence between an independent estimate and a claim is a reason for accredited review, never a finding of wrongdoing.',
};

const hi: Catalog = {
  'nav.home': 'मुख्य पृष्ठ',
  'nav.cases': 'मामले',
  'nav.compare': 'तुलना',
  'nav.claims': 'दावे',
  'nav.method': 'पद्धति',
  'nav.status': 'स्थिति',
  'lens.story': 'कहानी',
  'lens.explorer': 'अन्वेषक',
  'lens.auditor': 'लेखा-परीक्षक',
  'theme.light': 'हल्का',
  'theme.dark': 'गहरा',
  'theme.system': 'सिस्टम',
  'sim.chip': 'सिमुलेटेड डेटा',
  'home.cta': 'एक मामला देखें',
  'cases.count': '{n} मामले',
};

const mr: Catalog = {
  'nav.home': 'मुख्यपृष्ठ',
  'nav.cases': 'प्रकरणे',
  'nav.compare': 'तुलना',
  'nav.claims': 'दावे',
  'nav.method': 'पद्धत',
  'nav.status': 'स्थिती',
  'lens.story': 'कथा',
  'lens.explorer': 'शोधक',
  'lens.auditor': 'लेखापरीक्षक',
  'theme.light': 'फिकट',
  'theme.dark': 'गडद',
  'theme.system': 'सिस्टम',
  'sim.chip': 'सिम्युलेटेड डेटा',
  'home.cta': 'एक प्रकरण पहा',
  'cases.count': '{n} प्रकरणे',
};

const CATALOGS: Record<Locale, Catalog> = { en, hi, mr };
let active: Locale = 'en';

export function setLocale(locale: Locale): void {
  active = locale;
}

export function getLocale(): Locale {
  return active;
}

export function t(key: string, vars?: Record<string, string | number>): string {
  const template = CATALOGS[active][key] ?? en[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}
