# Runbook

Operational notes for running and maintaining this pipeline. Nothing here is
personal to any one profile — see `config/profile.example.yaml` (and your own
gitignored `config/profile.local.yaml`) for that.

## Apify gotchas

Each of these cost a failed or wasted run to discover:

- `memory: 1024` is mandatory. The default allocation exceeds the free/starter
  account's concurrent-memory cap and runs are rejected outright.
- `resumeKeywords` breaks the MCP connector call, but works fine through the REST
  API (what this script uses). Its match percentage counts raw string hits —
  useful as a triage hint, never as a score.
- `excludeRecruitingAgencies` doesn't catch every staffing intermediary. Some
  self-classify under an unrelated industry (e.g. "Technology, Information and
  Internet") and post many near-identical listings across sub-districts in a
  single day. The `COMPANY_REJECT` set in `daily_job_search.py` is a manual
  denylist and needs an occasional skim to stay current — add your own extras
  via `search.exclude_companies` in your profile config instead of editing the
  source.
- An unrestricted, country-wide pass tends to be low-yield (a large batch of
  results, very few usable). Restricting one pass to `workType: ["remote"]` and
  another to a specific city works better than one wide pass.
- `publishedAt` only accepts an exact enum: `""` (any time), `r86400` (24h),
  `r604800` (7 days), `r2592000` (30 days) — nothing in between. There's no
  server-side "48h" or "72h" option; sending an arbitrary seconds value 400s
  outright. `--window 48h`/`72h` work by asking Apify for the 7-day bucket and
  letting `hard_filter()`'s own `posted_hours_ago()` check narrow it down
  client-side — which means those windows fetch (and pay for) more raw
  results than a true 48h/72h server-side filter would.

## The 24h / bar / row-count tension

The posting window, the score bar, and the target row count can't all be
satisfied simultaneously. On a slow day, a strict 24-hour window at an 80% bar
might only yield a handful of genuine matches — nowhere near a 20-row target.

The pipeline's answer: **state the real count, don't inflate it.** Rows that
don't clear the bar are labelled Tier 2 (with the specific shortfall) or Tier 3
(not JD-verified), never silently promoted. If you want more rows, the better
lever is `--window 48h` (roughly doubles the qualifying pool while the "Posted"
column still shows you what's actually under 24 hours old) — lowering the score
bar tends to add very few extra rows for a much bigger accuracy cost.

## Non-negotiables (why the filters look the way they do)

**Score from the description text, never the title.** Titles lie. The same
generic title at different companies can describe completely different
disciplines — a "Software Engineer" posting can be a C/C++ networking role, a
"Software Dev Engineer II" title can front either a native mobile role or an
AI/ML role. A title-and-keyword filter alone will ship all of these as top
matches.

**`JD_REJECT` exists because language filters aren't discipline filters.**
Mobile JDs commonly name the same JVM languages this pipeline is filtering
*for* (e.g. Kotlin for Android). The language-acceptance regex alone isn't
enough — description-level discipline detection (Jetpack Compose, Android SDK,
SwiftUI, etc.) is what actually catches these. `tests/test_filters.py` encodes
this and other cases as regression tests; if you touch the filters, keep it
green.

**A JD that names no language isn't evidence against your stack.** `hard_filter()`
only hard-rejects on language when a JD *explicitly commits* to a competing
language (`LANG_REJECT` hits with fewer than 2 `LANG_ACCEPT` mentions) — a JD
naming neither passes through to scoring instead. This matters in practice:
large companies (Amazon is the real example that surfaced it) routinely write
language-agnostic JDs even for JVM-heavy teams — "2+ years of professional
software development experience," CS fundamentals, no language named at all.
An earlier version hard-rejected any JD not explicitly naming Java/Kotlin,
which silently dropped these before scoring ever saw them.

**Never commit secrets.** `APIFY_TOKEN` and `ANTHROPIC_API_KEY` come from the
environment locally and from repo secrets in CI. `config/profile.local.yaml`
and `.env` are gitignored — keep them that way.

## LinkedIn ToS

LinkedIn's Terms of Service prohibit automated scraping of the site. The legal
picture is unsettled — courts have found that scraping publicly accessible data
isn't a CFAA ("hacking") violation, but LinkedIn can still enforce its ToS as a
contract matter (account bans, IP blocks). This script calls a third-party
Apify actor rather than scraping LinkedIn directly, but the underlying
enforcement risk is the same. Use at your own judgment and risk; this isn't
legal advice.
