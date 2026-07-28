# daily-job-search

A daily job-match pipeline for backend/software engineers. It collects recent
LinkedIn postings, hard-filters out the obvious mismatches (wrong discipline,
wrong seniority, staffing aggregators), scores the survivors against *your*
rubric with Claude, and writes a ranked, color-coded `.xlsx` tracker.

This repo is generic — the actual person it searches for lives in a config
file you create locally and never commit. Clone it, plug in your own profile,
and it searches for you instead. Run it locally whenever you want a fresh
batch — no fork, no GitHub account, nothing beyond the clone. If you also
want it running unattended on a schedule (so it keeps going even when your
laptop is off), there's an optional GitHub Actions setup for that further
down — it's a separate, opt-in step, not a requirement.

## Quickstart (run it locally)

```bash
git clone <this repo's URL>
cd daily-job-search
pip install -r requirements.txt
```

Get an [Apify](https://apify.com) API token — you'll need it either way. An
`ANTHROPIC_API_KEY` is optional (see below for both the profile step and the
scoring step) — it's only needed if you'd rather pay for API credits than use
a Claude Code session for those parts.

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

**From your resume, without an Anthropic API key** (same idea as the scoring
split below — uses your Claude subscription instead):

```bash
python scripts/generate_profile.py --resume /path/to/your_resume.pdf --emit-request request.json
```

Answer the same prompts, then ask Claude Code:

> Read `request.json` and follow the `SYSTEM` prompt in
> `scripts/generate_profile.py` to draft a "profile" and a "rubric" string.
> Add those two keys to `request.json` (keep everything else in the file
> unchanged), then tell me when it's done.

Then render it (no API key needed for this step):

```bash
python scripts/generate_profile.py --from-draft request.json --out config/profile.local.yaml
```

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

## Scoring without a separate Anthropic API key

A Claude Pro/Max subscription and an `ANTHROPIC_API_KEY` are different products
with different billing — a subscription doesn't cover raw Messages API calls
a script makes. If you'd rather not pay separately for API credits, split the
run in two and let Claude Code do the scoring, using whatever plan already
grants you Claude Code access.

The normal one-shot run (`python daily_job_search.py`) does collect -> filter
-> score -> render as a single command, with nothing written to disk in
between. Splitting it means those in-between results become real files you
can hand off:

| File | What it is | Who produces it |
|---|---|---|
| `survivors.json` | The postings that survived hard-filtering (title, language, discipline, company denylist) -- real job data, **no score yet** | `--emit-survivors` (script, Apify only, no Anthropic key) |
| `scored.json` | The same list, each job now carrying `_score`/`_why`/`_caveat` | Whoever scores it -- Claude Code here, or the Anthropic API in a normal run |
| `job-matches-*.xlsx` | The final ranked tracker | `--from-scored` (script, no API keys at all) |

```bash
export APIFY_TOKEN=...
python daily_job_search.py --emit-survivors survivors.json
```

Then, in a Claude Code session, ask something like:

> Score `survivors.json` against `config/profile.local.yaml`'s profile and
> rubric, then write `scored.json` with the same list of jobs, each with
> `_score` (int or null), `_why` (one sentence), and `_caveat` added. Follow
> the exact instructions in `build_scoring_system()` in `daily_job_search.py`.

Two things worth knowing, from actually running this:
- **If `survivors.json` is large** (more than a handful of jobs with full
  descriptions), Claude may not be able to read the whole file in one shot.
  Ask it to extract compact per-job summaries first (title/company/years/JD
  text) if it hits a size limit, score from those, then merge the `_score`/
  `_why`/`_caveat` fields back onto the original full job records by index --
  never onto a truncated copy, or the final tracker loses data.
- Claude does the *decision*, not the merge — have it produce a small
  scores-only file (`{"i": 0, "score": 83, ...}` per job) and a short script
  merge that onto `survivors.json`, rather than asking it to hand-edit the
  full 30-job file directly.

Then render the tracker (no API keys needed for this step):

```bash
python daily_job_search.py --from-scored scored.json --out job-matches-YYYY-MM-DD.xlsx
```

## Optional: automate it with GitHub Actions

Everything above already works as a complete, standalone tool — run it by
hand whenever you want a fresh batch. This section is only for the specific
case where you also want it to keep running on a schedule without your
machine being on. Skip it entirely if manual local runs are enough for you.

It requires forking the repo (local use does not) and setting up three repo
secrets, and each fork's workflow is then entirely independent — its own
Actions runs, its own secrets, its own schedule, nothing shared with the
upstream repo.

1. **Fork this repo on GitHub.** Note: GitHub only allows forks of a public repo to also be public (there's no private-fork option), so treat your fork as public too — anything you `git add` in it is world-readable.
2. **Enable Actions on your fork.** GitHub disables Actions by default on new forks — the first visit to your fork's *Actions* tab shows a banner ("I understand my workflows, go ahead and enable them") that you click once.
3. **Add three repo secrets** (Settings → Secrets and variables → Actions → Secrets, or via `gh`):
   ```bash
   gh secret set APIFY_TOKEN
   gh secret set ANTHROPIC_API_KEY
   gh secret set PROFILE_YAML < config/profile.local.yaml
   ```
   `PROFILE_YAML` is the whole contents of your local `config/profile.local.yaml` — the file itself is gitignored and never reaches the Actions runner on its own, so the workflow reconstitutes it from this secret before each run. Without it, the workflow silently falls back to the tracked example/demo profile — same behavior as a local run with no `profile.local.yaml`.
4. **Edit the schedule for your timezone.** The workflow runs weekdays at 07:00 IST by default — edit the `cron:` line in `.github/workflows/daily-job-search.yml` (GitHub reads that file directly to schedule runs; it can't be driven from `profile.local.yaml`).
5. **Trigger it:**
   - **Now, to test:** Actions tab → "daily-job-search" workflow → "Run workflow" button (this is the `workflow_dispatch` trigger, with a `window` choice already wired up). Use this rather than waiting for the cron to confirm secrets are set correctly.
   - **Automatically:** the `cron:` schedule fires on its own from then on, using the secrets you just set.
6. **Get results:** Actions tab → the finished run → its Artifacts section → download `job-matches-*.xlsx`. Or enable email delivery (below) to have it land in your inbox instead.
7. **If you ever edit `profile.local.yaml` locally** (rubric tweak, new referral), re-run the `gh secret set PROFILE_YAML` command — the secret is a snapshot, not a live link to the file.

GitHub Actions on public repos gets **unlimited free minutes** on standard
runners — running this daily costs nothing on the GitHub side; the only real
cost is the Apify/Anthropic API calls (see below).

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
