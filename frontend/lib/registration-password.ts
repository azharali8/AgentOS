export const REGISTRATION_PASSWORD_MESSAGE = 'Use 8 to 20 characters and at least one special character (such as !, @, # or $).';

export function registrationPasswordChecks(password: string) {
  const length = Array.from(password).length;
  return {length: length >= 8 && length <= 20, special: /[!-/:-@\[-`{-~]/.test(password), count: length};
}

export function registrationPasswordError(password: string): string {
  const checks = registrationPasswordChecks(password);
  return checks.length && checks.special ? '' : REGISTRATION_PASSWORD_MESSAGE;
}
