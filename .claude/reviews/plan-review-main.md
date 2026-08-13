# Plan Review Panel — main (round 5, final automated round this session)

**Plan reviewed at this hash**: sha256:e788b3421a4b4ca731095ee57d4393a78d2c7fe3010cddded6c7cbf9255d2500 (v5)
**Verdict**: divergent via multi-agent (0/3 required passes; 4/4 reviewers failed)
**Quorum**: 4/4 responded, 4/4 distinct roles, 0 passed (required 3)

Session agent budget (`MCCP_ORCHESTRATION_MAX_AGENTS=24`) was exhausted by this round
(5 rounds × 4 reviewers = 20, reconciled). No further automated `/mccp:plan` L2 rounds
were possible in this session.

## Findings (round 5, against v5)

| Perspective | Severity | Claim | Evidence |
|---|---|---|---|
| security | HIGH | Deployed `config.json.loginMode` staying `false` (the repo default) makes the entire global auth dependency a no-op across all 47 routes; no deployment-time check verified this | recordWEB.py:376-377 (`enforceLoginGlobally`→`requireLogin`), json/config.json default `loginMode:false` |
| architect | HIGH | Same finding, framed as "the invariant has two owners: route-registration order AND a mutable config flag" | same |
| invariant | HIGH | Same finding, framed as an unenforced deployment-time invariant | same |
| architect | MEDIUM | `/` exemption justification misquoted — `index()`'s two branches return an identical template; real gating is in `templates/index.html` | recordWEB.py index() handler vs plan text |
| architect | MEDIUM | Mechanical grep only recognizes 4 HTTP-method decorator forms; other route-registration forms (`add_api_route`, `include_router`, `@app.websocket`, etc.) aren't checked | plan's Task 0 validate grep pattern |
| security | MEDIUM | `json/` bind mount being empty at first boot fail-opens to `loginMode:false` default | module/data_manager.py default config |
| security | MEDIUM | `/register` land-grab race between container boot and admin registration persists (loopback binding narrows but does not eliminate it) | recordWEB.py `/register` |
| architect/security | LOW | `GET /login` route did not exist — the global 401→redirect handler dead-ended at a 405 | recordWEB.py (only `@app.post("/login")` existed) |
| security | LOW | Session cookie issued with default options (no explicit `max_age`/`https_only`) | SessionMiddleware call |

## Post-review fixes (v6, NOT re-reviewed by the automated gate)

After this round, the following were fixed directly in code/plan and the plan was bumped
to v6 — but editing the plan changed its hash, and DD13 correctly refuses to reseal a
receipt against a plan the reviewers never read. v6 is **unreviewed**:

- Added `@app.get("/login")` (redirects to `/`) — closes the 405 dead-end (LOW, fixed).
- Corrected the `/` exemption's cited justification in the plan text (MEDIUM, fixed).
- Confirmed via grep that no `add_api_route`/`include_router`/`@app.websocket`/other
  method-decorator forms exist in the file — the MEDIUM coverage-gap concern is currently
  moot in practice, documented in the plan (MEDIUM, addressed/documented).
- Added an explicit Task 5 validate step and Acceptance item requiring the deployed
  `config.json.loginMode` to be confirmed `true` before proceeding — this does not change
  the code (the flag is still mutable/config-driven by design, matching the rest of the
  app's config model) but makes the previously-unverified precondition an explicit,
  checked gate in the deployment procedure (HIGH finding, mitigated but not eliminated —
  the underlying dependency-on-config-value design remains).
- `/register` land-grab race: NOT further mitigated beyond loopback binding (MEDIUM,
  open/accepted risk given session budget exhaustion).
- Session cookie hardening (`https_only`, explicit `max_age`): NOT addressed (LOW, open).

## Refutation attempted

| Perspective | Verdict | What was attacked |
|---|---|---|
| architect | fail | Route-registration ordering claim (survived), FastAPI dependency-inheritance mechanism (survived, unverifiable locally — no fastapi source in workspace), `_PUBLIC_PATHS` staleness (fails safe, no finding), `/register` re-registration abuse (blocked by existing code, no finding), `/` exemption citation (failed — misquoted), config-value dependency (failed — real gap) |
| security | fail | loginMode default/deployment gap (failed — real gap), empty-mount fail-open (failed — real gap), register race window (failed — narrowed not closed), GET /login absence (failed — real bug), session cookie defaults (failed — residual risk) |
| test | fail | Coverage-verification completeness (failed — grep pattern narrow), loginMode deployment verification (failed — absent) |
| invariant | fail | Single-owner claim for the auth invariant (failed — dual-owned by config value) |
