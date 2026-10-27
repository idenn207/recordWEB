---
name: ux-patterns
description: Use when designing, building, reviewing or changing any recordWEB screen or flow that has behavior to get right - lists and bulk actions, delete/overwrite confirmations, filters, empty/error states, progress and long jobs, capacity/disk display, agent approval, audit log. Applies and audits against PATTERNS.md; also use when the user says "패턴", "UX 규칙", "PATTERNS.md", or asks to add or change a rule.
---

# ux-patterns

`PATTERNS.md` (repo root) is the behavior rulebook. `DESIGN.md` owns visuals; this owns behavior and states. Do not duplicate one in the other.

## Tags in PATTERNS.md

- `[확인]` verified against a source page. Follow it.
- `[가정]` provisional value. Follow it, but list it in your report as an assumption.
- `[미결]` no rule exists. Do not invent one silently: ask the owner, or implement the smallest reversible default and list it as open.

## Apply (building or changing a screen)

1. Read `PATTERNS.md` whole, then the sections that match the screen. Section 0 holds the two global decisions (wait thresholds, selection scope).
2. Before coding, write a one-line-per-state table for each list or flow you touch: loading, empty, zero-results, error, partial failure, long-running. Fill each from PATTERNS.md; mark gaps `[미결]`.
3. Classify every destructive action by impact (section 1). Recording or locked items get the strictest tier.
4. Build. Keep behavior in shared pieces (`apps/web/src/shared/ui`, `features/*`), not copied per page.

## Audit (reviewing a screen or mockup)

Check each rule that applies and report in this shape:

| Rule (section) | Status | Evidence |
|---|---|---|

Status is pass, fail, or not-applicable. A fail names the file or element. End with the `[가정]` rules you relied on and any `[미결]` the screen ran into.

## Change the rulebook

- Add or edit a rule only with a source URL you opened, or tag it `[가정]` / `[미결]`. Never mark `[확인]` from memory.
- When the owner decides a `[미결]` or `[가정]`, rewrite it as a plain rule, remove the tag, and note the date and decision in section 9.
- Where two sources conflict, record the choice in section 0 with the reason.

## Boundaries

- Visual tokens, color, type, spacing: `DESIGN.md` and the impeccable skill.
- Do not edit the impeccable plugin files; the link to this rulebook lives in `PRODUCT.md`.
