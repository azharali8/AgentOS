# Authentication and first-impression UX verification

Date: 2026-09-13; final preview verification completed 2026-09-14.

## Implemented

- Light AgentOS login with a Supervisor workflow illustration, responsive desktop/tablet/mobile layouts, reduced-motion support, accessible labels, password visibility, and loading/error feedback.
- Removed browser-embedded demo credentials and quick-access login profiles.
- Email or username plus password uses the existing authentication service and server-assigned roles.
- Session restoration validates the saved token with `/api/v1/auth/me`; cached profile/role claims are discarded. Authentication failures close the workspace. Connection failures offer retry without granting access.
- Logout revokes the server token and clears local session data. A failed revocation is reported honestly while local access is closed.
- Optional local registration uses the existing in-memory account store, prevents duplicate email/username replacement, rejects role injection, and assigns USER. Enable with `AUTH_ALLOW_REGISTRATION=true` for local development only. Production always disables registration. The default is false.
- Authentication validation responses omit submitted credentials. UI errors never render raw server details.

## Verification

- Targeted auth/security and frontend-contract tests: 37 passed.
- Full backend regression: 554 passed, 1 skipped, 3 existing collection warnings.
- Frontend node tests: 24 passed, including six new session/error tests.
- Frontend lint and production build: passed; four existing hook-dependency warnings remain.
- Real browser: invalid login, password visibility, disabled controls while submitting, successful existing-account login, workspace render, session restoration on reload, and logout verified.
- Registration availability and form switching verified in browser. Registration creation, duplicate rejection, password hashing, role restrictions, validation, and production guard verified through API tests.
- Desktop, 768px tablet, and 390px mobile layouts inspected. Mobile line-break issue corrected and verified in the final production build, with no horizontal overflow.
- AssemblyAI calls this phase: **0**. The isolated auth preview backend has an empty provider key; no voice controls were activated.

## Scope and limitations

- Google: NOT IMPLEMENTED. GitHub: NOT IMPLEMENTED. Reserved configuration placeholders are documented in `.env.example`; providers are hidden until a real secure authorization/callback flow exists. Setting the placeholders alone does not enable OAuth.
- Password recovery is not implemented and has no visible dead link.
- Existing accounts/sessions are in memory and development seed accounts remain in the backend. This phase does not establish production identity infrastructure, durable accounts, email recovery, or tenant isolation. Deployments must keep authentication enabled and replace development credential provisioning before public use.
- The temporary local preview enables registration only to inspect that UI. User `.env` was unchanged.
