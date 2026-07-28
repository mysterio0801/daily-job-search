# daily-job-search

A daily job-match pipeline for backend/software engineers. It collects recent
LinkedIn postings, hard-filters out the obvious mismatches (wrong discipline,
wrong seniority, staffing aggregators), scores the survivors against *your*
rubric with Claude, and writes a ranked, color-coded `.xlsx` tracker. Runs
unattended on a scheduled GitHub Actions workflow.

This repo is generic — the actual person it searches for lives in a config
file you create locally and never commit. Fork it, plug in your own profile,
and it searches for you instead.

## Quickstart

```bash
git clone <your fork URL>
cd daily-job-search
pip install -r requirements.txt
```

Get an [Apify](https://apify.com) API token and an
[Anthropic](https://console.anthropic.com) API key — you'll need both either
way.

Then build `config/profile.local.yaml`, either:

**From your resume** (recommended — asks a few questions, has Claude draft the
rest):

```bash
export ANTHROPIC_API_KEY=...
python scripts/generate_profile.py --resume /path/to/your_resume.pdf
```

Answer the prompts (locations, company types wanted/excluded, search
keywords, referral contacts). Review the generated file afterward — especially
the rubric weights and the "Does NOT want" line, since those drive every
filtering decision downstream.

**Or by hand:**

```bash
cp config/profile.example.yaml config/profile.local.yaml
```

Then edit it directly: your background (`profile`), your scoring rubric
(`rubric`), score bar and target row count (`tiers`), search keywords and
locations (`search`), and any referral contacts you want surfaced in the
tracker (`referrals`).

Either way, `config/profile.local.yaml` is gitignored — it stays on your
machine (or in your fork's GitHub secrets, see below) and never gets
committed.

Now run it:

```bash
export APIFY_TOKEN=...
export ANTHROPIC_API_KEY=...
python daily_job_search.py --dry-run   # collect + filter only, no API cost
python daily_job_search.py             # full run, writes job-matches-YYYY-MM-DD.xlsx
```

### Running on a schedule (GitHub Actions)

1. Push your fork to GitHub. Note: GitHub only allows forks of a public repo to also be public (there's no private-fork option), so treat your fork as public too — anything you `git add` in it is world-readable.
2. Add repo secrets (Settings → Secrets and variables → Actions → Secrets): `APIFY_TOKEN`, `ANTHROPIC_API_KEY`.
3. `config/profile.local.yaml` is gitignored and never reaches the Actions runner on its own. Push its contents as a **third secret**, `PROFILE_YAML`, so the workflow can reconstitute the file before each run:
   ```bash
   gh secret set PROFILE_YAML < config/profile.local.yaml
   ```
   Without this secret the workflow silently falls back to the tracked example/demo profile — same behavior as running locally with no `profile.local.yaml`.
4. The workflow runs weekdays at 07:00 IST by default — edit the `cron:` line in `.github/workflows/daily-job-search.yml` for your own timezone (GitHub reads that file directly to schedule runs; it can't be driven from `profile.local.yaml`).
5. Trigger a manual run anytime via the Actions tab (`workflow_dispatch`) to test before waiting for the schedule.
6. **If you ever edit `profile.local.yaml` locally** (rubric tweak, new referral), re-run the `gh secret set` command above — the secret is a snapshot, not a live link to the file.

Optional email delivery of the tracker: set the repo variable
`ENABLE_EMAIL_NOTIFY=true` plus secrets `MAIL_USERNAME`, `MAIL_APP_PASSWORD`
(a Gmail app password, not your regular password), and `MAIL_TO`. Off by
default — otherwise just download the `.xlsx` from the Actions run's
artifacts each morning.

## What it costs to run

Two paid APIs, both pay-as-you-go:

- **Apify** (`cheap_scraper~linkedin-job-scraper`): ~$0.0007/result on the free tier (cheaper on paid tiers) plus a small per-run charge. A typical day's two collection passes cost well under $0.50.
- **Anthropic** (Claude Sonnet 5, the default `JOBSEARCH_MODEL`): scoring a few dozen survivors a day, at current pricing, typically runs a few tens of cents.

Realistic total: **usually under $1/day**, scaling up if you widen the search
(`--window 48h`, more keywords, more locations) or run more often. Check
current pricing on each provider's site before relying on this estimate — it
drifts over time and this isn't a guarantee.

## LinkedIn's Terms of Service

Scraping LinkedIn is against its Terms of Service, though the legal picture
around scraping public data is genuinely unsettled (see
[docs/runbook.md](docs/runbook.md#linkedin-tos) for the longer version). This
tool calls a third-party scraping service rather than scraping LinkedIn
directly, but the underlying risk is the same. Use your own judgment — this
isn't legal advice.

## Layout

```
daily_job_search.py                     collect -> filter -> score -> xlsx
scripts/generate_profile.py             resume + Q&A -> config/profile.local.yaml
config/profile.example.yaml             tracked demo profile (fictional persona)
config/profile.local.yaml               your real profile (gitignored, you create this)
tests/test_filters.py                   hard-filter regression tests (synthetic JDs)
.github/workflows/daily-job-search.yml  scheduled + manual-trigger workflow
docs/runbook.md                         Apify gotchas, cadence rationale, ToS notes
CLAUDE.md                               notes for Claude Code when working in this repo
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
