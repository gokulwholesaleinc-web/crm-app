import { safeStorage } from '../../utils/safeStorage';

const WELCOME_KEY = 'crm:welcome-seen:v1';

export function shouldShowWelcome(): boolean {
  return safeStorage.get(WELCOME_KEY) === null;
}

export function markWelcomeSeen(): void {
  safeStorage.set(WELCOME_KEY, new Date().toISOString());
}

export function resetWelcome(): void {
  safeStorage.remove(WELCOME_KEY);
}
