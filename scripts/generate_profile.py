#!/usr/bin/env python3
"""
Generate config/profile.local.yaml from a resume PDF plus a short Q&A.

The resume supplies background/stack/experience. The Q&A supplies what a
resume can't: what you're searching FOR right now (locations, company types,
exclusions, referral contacts). Claude drafts the "profile" and "rubric" text
blocks from the two combined; everything structural (tiers, search, referrals)
is built directly from your answers, no LLM guessing involved.

Usage (needs ANTHROPIC_API_KEY -- calls the Anthropic API directly):
    python scripts/generate_profile.py --resume path/to/resume.pdf

Drafting without an Anthropic API key (uses your Claude subscription instead):
    A raw ANTHROPIC_API_KEY bills against the separate Developer Platform
    credit balance, not a Claude Pro/Max subscription. To draft with Claude
    Code instead, split it in two:

        python scripts/generate_profile.py --resume path/to/resume.pdf --emit-request request.json
        # then, in a Claude Code session, ask Claude to read request.json, follow
        # the SYSTEM prompt in this file, and add "profile" and "rubric" string
        # keys to that same file -- see README for the exact instructions.
        python scripts/generate_profile.py --from-draft request.json --out config/profile.local.yaml

Never overwrites an existing output file without asking first.
"""

import argparse
import json
import os
import re
import sys

import requests
import yaml
from pypdf import PdfReader

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("JOBSEARCH_MODEL", "claude-sonnet-5")
DEFAULT_OUT = "config/profile.local.yaml"

SYSTEM = """You turn a resume into two pieces of a job-search config for one candidate.

Given the resume text and the candidate's stated preferences, produce:

1. "profile": a freeform summary in the same voice/shape as this example --
   background, years of experience, core stack, notable work, then explicit
   "Wants" / "Location" / "Company types" / "Does NOT want" lines built from
   the candidate's stated preferences (not invented):

<example>
SDE-2 at Porter, Bengaluru. ~3 years backend experience.
Core stack: Kotlin, Ktor, Java, Kafka, Redis, PostgreSQL, GCP, Kubernetes, Docker, microservices.
Notable work: tax management service (TDS recovery, 25K+ partners), centralized invoicing platform.
B.Tech Electronics & Communication, IIIT Allahabad, 2019-2023.

Wants: backend / distributed systems, or full-stack with a backend lean.
Location: Bengaluru (onsite/hybrid) or genuinely remote-India.
Company types: big tech and GCCs, unicorns / late-stage, funded product startups.
Does NOT want: AI/LLM platform engineering roles, platform/infra/devtooling roles, IT services and consulting firms.
</example>

2. "rubric": a scoring rubric in this exact table shape, with weights that sum
   to 100 and are tailored to the ACTUAL primary stack found in the resume --
   don't invent technologies that aren't present, and don't just copy the
   example's weights or wording:

<example>
Score each job out of 100:
  core_stack   (35) Kotlin/Java + Kafka + Redis/Postgres named in the JD
  system_type  (25) distributed microservices, high-throughput transactional backend
  cloud_infra  (15) GCP or AWS, Kubernetes, Docker
  seniority    (10) 2-5 yrs / SDE-2 equivalent band
  location     (10) Bengaluru onsite/hybrid, or genuinely remote-India
  ai_bonus     ( 5) AI/agentic tooling - bonus only, never a requirement
</example>

Respond with ONLY a JSON object, no prose and no markdown fences:
{"profile": "...", "rubric": "..."}
"""


class _LiteralStr(str):
    """Marks a string to be YAML-dumped in block-literal (|) style."""


def _literal_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_LiteralStr, _literal_str_representer)


def extract_resume_text(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def collect_answers() -> dict:
    print("A few questions about what you're searching for (the resume covers your background).\n")
    # Each location is itself "City, Country" -- a comma. Splitting answers on
    # "," would break that apart, so multiple locations are ";"-separated
    # instead (a single location's internal comma is left alone).
    locations = ask(
        "Onsite/hybrid location(s); separate multiple with ';' "
        "(e.g. 'Bengaluru, India' or 'Bengaluru, India; Pune, India')"
    )
    remote_scope = ask("Remote scope, e.g. 'India' or 'EU' (blank to skip a remote pass)")
    company_types = ask(
        "Company types wanted, comma-separated",
        "big tech and GCCs, unicorns/late-stage, funded product startups",
    )
    exclude_types = ask(
        "Anything explicitly NOT wanted, comma-separated",
        "AI/LLM platform engineering roles, platform/infra/devtooling roles, IT services and consulting firms",
    )
    keywords = ask(
        "Search keywords, comma-separated",
        "Software Engineer, Backend Engineer, Full Stack Engineer",
    )
    target_rows = int(ask("Target rows in the tracker", "20") or "20")
    tier1_bar = int(ask("Tier 1 score bar", "80") or "80")
    tier2_bar = int(ask("Tier 2 score bar", "70") or "70")

    referrals: dict[str, str] = {}
    print("\nReferral contacts (company -> contact note). Leave company blank to stop.")
    while True:
        company = ask("  Company")
        if not company:
            break
        note = ask("  Contact note")
        referrals[company.lower()] = note

    return {
        "locations": [s.strip() for s in locations.split(";") if s.strip()],
        "remote_scope": remote_scope.strip(),
        "company_types": company_types,
        "exclude_types": exclude_types,
        "keywords": [s.strip() for s in keywords.split(",") if s.strip()],
        "target_rows": target_rows,
        "tier1_bar": tier1_bar,
        "tier2_bar": tier2_bar,
        "referrals": referrals,
    }


def draft_profile_and_rubric(api_key: str, resume_text: str, answers: dict) -> tuple[str, str]:
    user_payload = {
        "resume_text": resume_text[:12000],
        "company_types_wanted": answers["company_types"],
        "explicitly_not_wanted": answers["exclude_types"],
        "locations": answers["locations"],
        "remote_scope": answers["remote_scope"],
    }
    r = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2000,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": json.dumps(user_payload)}],
        },
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"] if b["type"] == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    return data["profile"].strip(), data["rubric"].strip()


def build_search_block(answers: dict) -> dict:
    passes = []
    if answers["locations"]:
        passes.append({"locations": answers["locations"], "remote": False})
    if answers["remote_scope"]:
        passes.append({"locations": [answers["remote_scope"]], "remote": True})
    if not passes:
        passes.append({"locations": [], "remote": False})
    return {"keywords": answers["keywords"], "passes": passes, "exclude_companies": []}


def confirm_overwrite(path: str) -> bool:
    if not os.path.exists(path):
        return True
    confirm = input(f"{path} already exists. Overwrite? [y/N]: ").strip().lower()
    return confirm == "y"


def write_profile_yaml(out_path: str, profile: str, rubric: str, data: dict) -> None:
    config = {
        "profile": _LiteralStr(profile.strip() + "\n"),
        "rubric": _LiteralStr(rubric.strip() + "\n"),
        "tiers": {
            "target_rows": data["target_rows"],
            "tier1_bar": data["tier1_bar"],
            "tier2_bar": data["tier2_bar"],
        },
        "search": build_search_block(data),
        "referrals": data.get("referrals", {}),
    }
    with open(out_path, "w") as f:
        f.write("# Generated by scripts/generate_profile.py -- review before relying on it.\n")
        yaml.dump(config, f, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", help="path to a PDF resume (required unless --from-draft)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument(
        "--emit-request", metavar="PATH",
        help="extract resume text + collect Q&A answers into a JSON request file, then exit "
             "(no ANTHROPIC_API_KEY needed -- have Claude Code draft it from this file, see --from-draft)",
    )
    ap.add_argument(
        "--from-draft", metavar="PATH",
        help="skip resume extraction and Q&A; build the profile YAML from a request file "
             "(see --emit-request) that Claude Code has augmented with \"profile\" and "
             "\"rubric\" string keys (no ANTHROPIC_API_KEY or resume needed)",
    )
    args = ap.parse_args()

    if args.from_draft:
        with open(args.from_draft) as f:
            data = json.load(f)
        if "profile" not in data or "rubric" not in data:
            print(
                f'{args.from_draft} has no "profile"/"rubric" keys yet -- ask Claude Code to '
                f"add them first (see README), then re-run --from-draft.",
                file=sys.stderr,
            )
            return 1
        if not confirm_overwrite(args.out):
            print("Aborted.")
            return 1
        write_profile_yaml(args.out, data["profile"], data["rubric"], data)
        print(f"\nWrote {args.out}.")
        print("Review it -- especially the rubric weights and the 'Does NOT want' line -- before running the pipeline.")
        return 0

    if not args.resume:
        print("--resume is required (unless using --from-draft)", file=sys.stderr)
        return 1

    resume_text = extract_resume_text(args.resume)
    if not resume_text:
        print("Could not extract any text from that PDF (scanned image? no text layer?).", file=sys.stderr)
        return 1

    answers = collect_answers()

    if args.emit_request:
        request = {"resume_text": resume_text, **answers}
        with open(args.emit_request, "w") as f:
            json.dump(request, f, indent=2)
        print(f"\n[done] wrote request to {args.emit_request}")
        print('Ask Claude Code to draft it (see README), which adds "profile" and "rubric"')
        print("keys to this same file, then render with:")
        print(f"  python scripts/generate_profile.py --from-draft {args.emit_request} --out {args.out}")
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set (or use --emit-request to draft without one)", file=sys.stderr)
        return 1

    if not confirm_overwrite(args.out):
        print("Aborted.")
        return 1

    print("\nDrafting profile and rubric with Claude...", file=sys.stderr)
    profile, rubric = draft_profile_and_rubric(api_key, resume_text, answers)
    write_profile_yaml(args.out, profile, rubric, answers)

    print(f"\nWrote {args.out}.")
    print("Review it -- especially the rubric weights and the 'Does NOT want' line -- before running the pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
