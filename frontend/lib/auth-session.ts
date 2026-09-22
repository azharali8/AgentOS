import { UserProfile, UserRole } from '../types';
export function verifiedProfile(profile: UserProfile): UserProfile {
  const role = profile.role?.toUpperCase() as UserRole;
  if (!profile.is_authenticated || !profile.user_id || !['USER','DEVELOPER','ADMIN','VIEWER'].includes(role)) throw new Error('Invalid profile');
  return {...profile, role};
}
export async function restoreSession(storage: Pick<Storage, 'getItem' | 'removeItem'>, profile: (token: string) => Promise<UserProfile>) {
  storage.removeItem('agentos_user'); // Cached role claims are never authoritative.
  const token = storage.getItem('agentos_token');
  if (!token) return null;
  try { return {token, user: verifiedProfile(await profile(token))}; }
  catch (error) {
    if ((error as {status?: number}).status === 401 || (error as {status?: number}).status === 403) storage.removeItem('agentos_token');
    throw error;
  }
}
export function authError(error: unknown): string {
  const status = (error as {status?: number})?.status;
  if (status === 401) return 'That email, username or password wasn’t recognized. Please try again.';
  if (status === 429) return 'Too many attempts. Please try again later.';
  if (status === 400) return 'We couldn’t create an account with those details. Check your information or contact your workspace administrator.';
  if (status === 422) return 'Please check your details and try again.';
  if (status === 404) return 'This sign-in option is not available for this workspace.';
  return 'We couldn’t reach your workspace. Check your connection and try again.';
}
