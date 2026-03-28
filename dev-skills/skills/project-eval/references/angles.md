# Evaluation Angle Pool

This is a starting menu, not a constraint. Use these directions and calibration examples as inspiration. You may explore freely within your assigned direction and discover issues outside the predefined list.

## Code

Logic errors, error handling gaps, state inconsistencies, incomplete implementations, concurrency issues.

- `logic` — Wrong conditionals, off-by-one, inverted checks
- `error-handling` — Missing catches, swallowed errors, unhelpful messages
- `state` — Stale references, missing syncs, inconsistent state transitions
- `completeness` — Stubs, TODOs in production paths, half-implemented features
- `concurrency` — Race conditions, partial writes, deadlocks

### Calibration: Code

**REAL ISSUE:**
File: `cart/discount.ts:23`
Code: `discount = price * percentage` where percentage is 0-100
Why real: Math is wrong. $50 at 20% gives $1000 instead of $10. Should be `price * percentage / 100`.
Severity: Critical

**FALSE POSITIVE:**
File: `cart/tax.ts:15`
Code: Tax rate hardcoded to `0.08`
Why false positive: This is a configuration constant, not a bug. Changing it is a product decision.

## Architecture

Module coupling, boundary clarity, pattern consistency, scalability concerns.

- `coupling` — Modules knowing too much about each other's internals
- `boundaries` — Unclear module separation, circular dependencies
- `consistency` — Same problem solved differently across codebase
- `scalability` — Patterns that break under load or growth

### Calibration: Architecture

**REAL ISSUE:**
File: `api/handlers/order.ts:15`
Code: Handler directly imports and calls `db.query("SELECT * FROM users WHERE id = ...")` instead of going through the user service.
Why real: Bypasses the service layer, creating a hidden dependency. If user schema changes, this handler silently breaks. Tight coupling across boundaries.
Severity: Major

**FALSE POSITIVE:**
File: `utils/helpers.ts`
Code: A single utility file with 15 small functions
Why false positive: Utility files are a common, accepted pattern. This becomes an issue only when functions have unrelated concerns or the file grows excessively large.

## Security

Injection vectors, authentication/authorization gaps, secret exposure, data privacy violations.

- `injection` — SQL, command, XSS, template injection
- `auth` — Authentication bypass, authorization gaps, privilege escalation
- `secrets` — Credentials in code, logs, or committed config
- `data-privacy` — PII leaks, missing anonymization, retention violations

### Calibration: Security

**Tool tip:** Use WebSearch to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but WebSearch catches known vulnerabilities in third-party packages.

**REAL ISSUE:**
File: `api/search.ts:34`
Code: `db.query("SELECT * FROM products WHERE name LIKE '%" + userInput + "%'")` with raw string concatenation.
Why real: Classic SQL injection. User can terminate the string and execute arbitrary SQL. Must use parameterized queries.
Severity: Critical

**REAL ISSUE (WebSearch-detected):**
File: `package.json`
Dependency: `jsonwebtoken@8.5.1`
Search result: CVE-2022-23529 — allows attackers to execute arbitrary code via crafted JWS tokens when using a malicious JWK.
Why real: Known critical vulnerability with a published fix (upgrade to 9.0.0+). WebSearch confirmed the CVE; code analysis alone would not surface this.
Severity: Critical

**FALSE POSITIVE:**
File: `config/database.ts:8`
Code: `const DB_HOST = process.env.DB_HOST || "localhost"`
Why false positive: Default localhost for development is standard practice. The production value comes from environment variables, which is correct.

## Frontend & Design

Visual coherence, responsiveness, accessibility, component design consistency.

- `visual-coherence` — Inconsistent spacing, typography, color usage across views
- `responsiveness` — Breakpoint gaps, overflow issues, touch target sizes
- `accessibility` — Missing ARIA labels, contrast ratios, keyboard navigation
- `component-design` — Duplicated UI patterns, inconsistent component APIs

### Calibration: Frontend & Design

**Tool tip:** Use Chrome browser tools to inspect the running UI. Navigate to pages, read page content, check console for errors, and inspect network requests. This catches visual and interaction issues that code-only analysis misses.

**REAL ISSUE:**
File: `components/Modal.tsx:45`
Code: Modal content receives focus but has no `aria-modal="true"` or `role="dialog"`, and pressing Escape does nothing.
Why real: Screen reader users cannot identify this as a modal, and keyboard users are trapped without an exit. WCAG 2.1 Level A violation.
Severity: Major

**REAL ISSUE (browser-detected):**
Page: `/dashboard` (inspected via Chrome tools)
Observation: Navigation menu overflows on viewport width below 768px, overlapping main content. Console shows repeated `ResizeObserver loop limit exceeded` warnings.
Why real: Responsive breakpoint is broken — mobile users see overlapping, unusable layout. Confirmed by reading the page in Chrome, not visible from code alone.
Severity: Major

**FALSE POSITIVE:**
File: `components/Button.tsx:12`
Code: Button uses `#3B82F6` instead of the design system's `--color-primary`
Why false positive: This may be intentional for a specific variant. Check if the design system actually defines this variant before flagging.

## User Experience

Navigation flow, feedback mechanisms, discoverability, edge state handling.

- `flow` — Confusing navigation, dead ends, unnecessary steps
- `feedback` — Missing loading states, error messages, success confirmations
- `discoverability` — Hidden features, unclear CTAs, unintuitive interactions
- `edge-ux` — Empty states, first-time experience, degraded states

### Calibration: User Experience

**Tool tip:** Use Chrome browser tools to walk through user flows — navigate between pages, check loading states, verify error messages render correctly, and test edge states like empty lists. Console messages and network requests reveal silent failures invisible in code.

**REAL ISSUE:**
File: `pages/Dashboard.tsx:120`
Code: Component renders a blank div when `data.items` is empty. No empty state message, no call to action.
Why real: Users with no data see a blank screen with no guidance on what to do next. First-time users will think the app is broken.
Severity: Major

**REAL ISSUE (browser-detected):**
Page: `/checkout` (inspected via Chrome tools)
Observation: Clicking "Place Order" with an invalid card shows no error message. The button briefly disables then re-enables. Network tab reveals a 422 response with validation errors, but the UI silently swallows them.
Why real: Users have no feedback on what went wrong. Confirmed by navigating the flow in Chrome — the error handling gap is invisible from code review alone since the API response is correct but the UI discards it.
Severity: Major

**FALSE POSITIVE:**
File: `pages/Settings.tsx:80`
Code: Settings page has 12 options on a single page
Why false positive: A flat settings page is fine for 12 options. Premature grouping into tabs or sections can reduce discoverability.

## Product

Feature completeness, requirement alignment, feature coherence, value assessment.

- `feature-gaps` — Missing functionality users would reasonably expect
- `requirement-drift` — Implementation diverging from stated requirements
- `coherence` — Features that contradict each other
- `value` — Features adding complexity with unclear user value

### Calibration: Product

**REAL ISSUE:**
File: `api/routes/export.ts` (entire file)
Code: Export endpoint returns CSV data but the UI only offers a "Download PDF" button.
Why real: The backend and frontend disagree on the export format. Users click "Download PDF" and get a CSV file. Requirement drift between layers.
Severity: Major

**FALSE POSITIVE:**
File: `features/analytics/`
Code: Analytics dashboard only shows last 30 days with no date picker
Why false positive: This may be a deliberate scope decision for v1. Feature absence is only an issue if the spec explicitly requires it.

## Data & API

API contract correctness, schema integrity, input validation, query performance.

- `api-contract` — Route conflicts, parameter mismatches, response shape violations
- `schema` — Migration gaps, orphaned references, type mismatches
- `validation` — Missing input validation at system boundaries
- `performance` — N+1 queries, unnecessary fetches, missing caching

### Calibration: Data & API

**REAL ISSUE:**
File: `api/routes/frames.ts:25`
Code: `PUT /frames/reorder` route defined after `GET /frames/:frame_id`. Express matches "reorder" as a frame_id parameter.
Why real: Route ordering bug. The reorder endpoint is unreachable because the parametric route catches it first. Returns 400 or unexpected results.
Severity: Critical

**FALSE POSITIVE:**
File: `api/routes/users.ts:40`
Code: `GET /users` returns all fields including `created_at` and `updated_at`
Why false positive: Internal timestamps are metadata, not secrets. Over-filtering API responses creates maintenance burden without security benefit.

## Documentation & Convention

Project rules compliance, documentation quality, test coverage quality.

- `project-rules` — CLAUDE.md compliance, project-specific conventions
- `documentation` — Missing or misleading docs at critical decision points
- `test-quality` — Tests that don't actually verify behavior

### Calibration: Documentation & Convention

**REAL ISSUE:**
File: `tests/auth.test.ts:15`
Code: `expect(result).toBeTruthy()` after calling the login function
Why real: Tautological assertion. This passes for any non-null/non-empty return value, including an error object. The test does not verify that login actually succeeded — it verifies that something was returned.
Severity: Minor

**FALSE POSITIVE:**
File: `src/utils/parser.ts`
Code: No JSDoc comments on internal helper functions
Why false positive: Internal helpers with clear names and small scope don't need documentation. Comments on self-evident code add noise.
