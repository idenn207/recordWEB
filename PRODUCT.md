# Product

## Register

product

## Users
The NAS owner and a small number of trusted household/LAN users. They access recordWEB directly on their local network (no public exposure) to manage automatic live-stream recording — registering channels, checking recording status, adjusting config, and browsing/organizing the resulting video files. This is a personal operations tool, used in short, frequent sessions (checking recording status, cleaning up finished files), not a product anyone signs up for.

## Product Purpose
recordWEB is a self-hosted web UI (FastAPI + Jinja2) for automatically recording live streams (Chzzk, YouTube) to a NAS. It runs 24/7 in Docker on a Synology NAS. Success looks like: recordings start/stop reliably and unattended, and the operator can quickly see what's recording, what finished, and manage the resulting files (multi-GB video files with long Korean titles) without friction.

## Brand Personality
Calm, minimal, quietly capable. This is an operator's tool, not a product being sold — it should feel like a well-made internal dashboard, not a marketing surface. Information-dense where it matters (the file table: many long filenames, sizes, timestamps) and restrained everywhere else. Dark theme by default (personal NAS/ops-tool context, used in short focused checks rather than long reading sessions).

## Anti-references
Not a SaaS marketing dashboard (no gradient hero stats, no cream/sand backgrounds, no upsell-shaped cards). Not a loud "gamer RGB" NAS-tool aesthetic. Not glassmorphism-heavy. Avoid decorative flourishes that compete with the actual data (filenames, sizes, recording status) for attention.

## Design Principles
- The file table is the primary surface — filenames (25-50 Korean characters) get the most horizontal room; secondary metadata (type, size, mtime) stays compact and out of the way.
- Actions stay out of the way until requested (menus/icons) rather than crowding every row with buttons.
- Status (recording / locked / idle) must be legible at a glance, not just present.
- Dark theme first; restrained accent color used only for status and primary actions, not decoration.
- Korean-first typography: line-height and weight tuned for Korean text legibility, not an English-first font stack with Korean as an afterthought.

## Accessibility & Inclusion
Standard WCAG AA contrast throughout (body text ≥4.5:1). No stated assistive-tech requirements beyond that; keyboard operability for table row actions (dropdown menu) is expected since this is a daily-use tool for the operator.
