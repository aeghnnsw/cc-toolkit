# Dimensions and Angles

A **dimension** is one of the eight areas below. An **angle** is a topic inside one dimension. The angle lists are a start, not a limit: explore freely inside your dimensions, and note issues outside them.

Each dimension has calibration examples. A real issue shows the evidence and impact that a finding needs, in the Location and Evidence fields of the finding format. A false positive shows a concern that is not a finding. Verifiers use the false positives to reject findings.

The examples quote code, but the same rules apply to documents and running apps. For a design document or plan, test its claims: look for contradictions between sections, unstated assumptions, steps that no reader can follow, and claims that the repository or a quick experiment contradicts. Documentation & Convention has a design-document example.

## Code

Logic errors, error handling gaps, state inconsistencies, incomplete implementations, concurrency issues.

- `logic` — Wrong conditionals, off-by-one, inverted checks
- `error-handling` — Missing catches, swallowed errors, unhelpful messages
- `state` — Stale references, missing syncs, inconsistent state transitions
- `completeness` — Stubs, TODOs in production paths, half-implemented features
- `concurrency` — Race conditions, partial writes, deadlocks

### Calibration: Code

**REAL ISSUE:**
Location: `cart/discount.ts:22-23`
Evidence:
```ts
// percentage is 0-100, for example 20 for 20%
const discount = price * percentage;
```
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
Location: `api/handlers/order.ts:15-16`
Evidence:
```ts
const rows = await db.query("SELECT * FROM users WHERE id = $1", [order.userId]);
const user = rows[0];
```
Why real: The handler queries the users table directly and bypasses the user service, creating a hidden dependency. If user schema changes, this handler silently breaks. Tight coupling across boundaries.
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

**Tool tip:** Search the web to check for known CVEs in project dependencies (e.g., search "CVE lodash 4.17.15" or "express 4.18 vulnerabilities"). Code-only analysis catches injection and auth issues, but a web search catches known vulnerabilities in third-party packages.

**REAL ISSUE:**
Location: `api/search.ts:33-34`
Evidence:
```ts
const userInput = String(req.query.q);
const rows = await db.query("SELECT * FROM products WHERE name LIKE '%" + userInput + "%'");
```
Why real: Classic SQL injection. User can terminate the string and execute arbitrary SQL. Must use parameterized queries.
Severity: Critical

**REAL ISSUE (web-search-detected):**
Location: `package.json:17-18` and `auth/verify.ts:9-10`
Evidence:
```text
package.json:17-18
    "express": "4.18.2",
    "jsonwebtoken": "8.5.1",
auth/verify.ts:9-10
  const secret = process.env.JWT_SECRET;
  return jwt.verify(token, secret);
```
Search result: https://github.com/advisories/GHSA-qwph-4952-7xr6 (CVE-2022-23540): "jsonwebtoken vulnerable to signature validation bypass due to insecure default algorithm in jwt.verify()". Patched in 9.0.0.
Why real: Version 8.5.1 is affected. The call names no `algorithms`, and nothing checks that `JWT_SECRET` is set, so an unset secret makes the server accept a token with no signature. The fix is published: upgrade to 9.0.0 or later and pass `algorithms`. A web search found the advisory; code analysis alone would not surface this.
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

**Tool tip:** When you have an app URL, use the browser tools to inspect the running UI. Navigate to pages, read page content, check the console for errors, and inspect network requests. This catches visual and interaction issues that code-only analysis misses.

**REAL ISSUE:**
Location: `components/Modal.tsx:44-46`
Evidence:
```tsx
  useEffect(() => contentRef.current?.focus(), []);
  return (
    <div className="modal" ref={contentRef} tabIndex={-1}>
```
Why real: The focused element has no `role="dialog"` or `aria-modal="true"`, and the file has no Escape key handler. Screen reader users cannot identify this as a modal, and keyboard users are trapped without an exit. WCAG 2.1 Level A violation.
Severity: Major

**REAL ISSUE (browser-detected):**
Location: `http://localhost:3000/dashboard`, inspected with browser tools; steps: set the viewport width to 767 px, then reload the page.
Evidence: The navigation menu overflows and covers the main content. The console shows the warning `ResizeObserver loop limit exceeded` 12 times.
Why real: Responsive breakpoint is broken — mobile users see overlapping, unusable layout. Confirmed by reading the page in the browser, not visible from code alone.
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

**Tool tip:** When you have an app URL, use the browser tools to walk through user flows — navigate between pages, check loading states, verify error messages render correctly, and test edge states like empty lists. Console messages and network requests reveal silent failures invisible in code.

**REAL ISSUE:**
Location: `pages/Dashboard.tsx:118-120`
Evidence:
```tsx
  if (data.items.length === 0) {
    return <div className="dashboard-list" />;
  }
```
Why real: The empty branch shows no message and no call to action. Users with no data see a blank screen with no guidance on what to do next. First-time users will think the app is broken.
Severity: Major

**REAL ISSUE (browser-detected):**
Location: `http://localhost:3000/checkout`, inspected with browser tools; steps: enter a card with an expiry date in the past, then click "Place Order".
Evidence: The button is disabled for a moment, then enabled again, and the page shows no error message. The network panel shows `POST /api/orders` with status 422 and the body `{"errors":[{"field":"card","message":"Card expired"}]}`.
Why real: Users have no feedback on what went wrong. Confirmed by navigating the flow in the browser — the error handling gap is invisible from code review alone since the API response is correct but the UI discards it.
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
Location: `api/routes/export.ts:12-13` and `components/ExportButton.tsx:8-10`
Evidence:
```text
api/routes/export.ts:12-13
  res.setHeader("Content-Type", "text/csv");
  res.send(toCsv(rows));
components/ExportButton.tsx:8-10
  <button onClick={downloadExport}>
    Download PDF
  </button>
```
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
Location: `api/routes/frames.ts:25-26`
Evidence:
```ts
router.get('/frames/:frame_id', getFrame);
router.get('/frames/reorder', getReorderPreview);
```
Why real: Route ordering bug: the parametric route is registered first. Express tries routes in order, and both match `GET /frames/reorder`, so the parametric route takes the request with `frame_id = "reorder"`. The reorder preview is unreachable and the request returns 404 or 400.
Severity: Critical

**FALSE POSITIVE:**
File: `api/routes/users.ts:40`
Code: `GET /users` returns all fields including `created_at` and `updated_at`
Why false positive: Internal timestamps are metadata, not secrets. Over-filtering API responses creates maintenance burden without security benefit.

## Documentation & Convention

Project rules compliance, documentation quality, test coverage quality.

- `project-rules` — Compliance with GEMINI.md, AGENTS.md, or CLAUDE.md, project-specific conventions
- `documentation` — Missing or misleading docs at critical decision points
- `test-quality` — Tests that don't actually verify behavior

### Calibration: Documentation & Convention

**REAL ISSUE:**
Location: `tests/auth.test.ts:14-15`
Evidence:
```ts
const result = await login("alice@example.com", "correct-password");
expect(result).toBeTruthy();
```
Why real: Tautological assertion. This passes for any non-null/non-empty return value, including an error object. The test does not verify that login actually succeeded — it verifies that something was returned.
Severity: Minor

**FALSE POSITIVE:**
File: `src/utils/parser.ts`
Code: No JSDoc comments on internal helper functions
Why false positive: Internal helpers with clear names and small scope don't need documentation. Comments on self-evident code add noise.

**REAL ISSUE (design document):**
Location: `docs/design/result-cache.md:42-43`
Evidence:
```markdown
Each worker appends its results to the shared cache file. Readers never
see a partial write.
```
Check: The design names no lock and no atomic rename. In a temporary directory, two processes that append 64 KB records to one file produced interleaved records.
Why real: The guarantee does not hold for the mechanism that the document describes, and implementers will rely on it.
Severity: Major

**FALSE POSITIVE (design document):**
File: `docs/design/result-cache.md`
Observation: The document does not say which hash function names the cache files.
Why false positive: This is an implementation detail outside the decision that the document records. Report a missing detail only when a reader cannot implement or check the design without it.
