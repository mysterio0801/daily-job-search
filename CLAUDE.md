# CLAUDE.md

Project context for Claude Code. Read this before changing anything.

## What this is

A daily job-match pipeline. It collects LinkedIn postings from a configurable
window, filters them, scores each job description against a rubric, and emits
a ranked `.xlsx` tracker. Runs unattended on a scheduled GitHub Actions
workflow.

This is a generic tool, not tied to one person. The specific profile it
searches for — background, rubric weights, search keywords/locations, and
referral contacts — lives in `config/profile.local.yaml`, which is gitignored
and never committed. `config/profile.example.yaml` is the tracked, fictional
demo profile that keeps the repo runnable out of the box. When editing the
scoring/search logic, treat `profile.local.yaml` as opaque instance data you
should never need to hardcode assumptions about.

## Layout

```
daily_job_search.py                     collect -> filter -> score -> xlsx
config/profile.example.yaml             tracked demo profile
config/profile.local.yaml               real profile (gitignored, not in repo)
tests/test_filters.py                   hard-filter regression tests (synthetic JDs)
.github/workflows/daily-job-search.yml  scheduled + manual-trigger workflow
docs/runbook.md                         Apify gotchas, cadence rationale, ToS notes
```

## Config-driven design

`load_config()` in `daily_job_search.py` reads `config/profile.local.yaml`,
falling back to `config/profile.example.yaml` with a stderr notice if the
former doesn't exist. Everything specific to one job-seeker — `profile`,
`rubric`, `tiers` (target rows / score bars), `search` (keywords, location
passes, extra company denylist entries), `referrals` — comes from this file
and is threaded explicitly through `collect()`, `score_all()`, and
`write_xlsx()` rather than living as module-level constants.

What stays in code as shared, generic logic (not personal, useful to any
fork): `TITLE_REJECT`, `LANG_ACCEPT`/`LANG_REJECT`, `JD_REJECT`, and the base
`COMPANY_REJECT` denylist (staffing aggregators / IT-services firms). A fork
extends the company denylist via `search.exclude_companies` in their own
config rather than editing these.

## Non-negotiables

**Titles lie. Score from the description text, never the title.** This is the
single most important rule in the project. The same generic title can front
completely different disciplines at different companies — a "Software
Engineer" posting can be a C/C++ networking role instead of the JVM backend
role its title implies. A title-and-keyword filter ships all of these as top
matches.

**`JD_REJECT` exists because language filters aren't discipline filters.**
Mobile JDs commonly name the same JVM languages this pipeline's `LANG_ACCEPT`
regex is filtering *for* (e.g. Kotlin for Android). Description-level
discipline detection (Jetpack Compose, Android SDK, SwiftUI, etc.) is what
actually catches these — the language filter alone is not enough. If you
refactor the filters, `tests/test_filters.py` must keep passing; it encodes
these failure modes as synthetic regression cases (see docs/runbook.md for
the reasoning behind each one).

**Never inflate scores to fill the sheet.** The row target is configurable
(`tiers.target_rows`), but some days genuinely yield only a handful of roles
above the top bar. When fewer clear it, label the remainder Tier 2 (with the
specific shortfall reason) and Tier 3 (not JD-verified) rather than promoting
them. State the real count.

**Never commit secrets or personal data.** `APIFY_TOKEN` and
`ANTHROPIC_API_KEY` come from the environment locally and from repo secrets
in CI. `config/profile.local.yaml` and `.env` are gitignored — keep it that
way. This repo is public; anything committed here is public.

## Known open item

The posting window, the score bar, and the target row count can't all be
satisfied simultaneously — see docs/runbook.md for the detailed tradeoff and
why `--window 48h` is the preferred lever over lowering the score bar.
