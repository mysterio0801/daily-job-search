#!/usr/bin/env python3
"""
Generate config/profile.local.yaml from a resume PDF plus a short Q&A.

The resume supplies background/stack/experience. The Q&A supplies what a
resume can't: what you're searching FOR right now (locations, company types,
exclusions, referral contacts). Claude drafts the "profile" and "rubric" text
blocks from the two combined; everything structural (tiers, search, referrals)
is built directly from your answers, no LLM guessing involved.

Usage:
    python scripts/generate_profile.py --resume path/to/resume.pdf

Requires ANTHROPIC_API_KEY. Never overwrites an existing profile.local.yaml
without asking first.
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
    locations = ask("Onsite/hybrid location(s), comma-separated (e.g. 'Bengaluru, India')")
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
        "locations": [s.strip() for s in locations.split(",") if s.strip()],
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", required=True, help="path to a PDF resume")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    if os.path.exists(args.out):
        confirm = input(f"{args.out} already exists. Overwrite? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1

    resume_text = extract_resume_text(args.resume)
    if not resume_text:
        print("Could not extract any text from that PDF (scanned image? no text layer?).", file=sys.stderr)
        return 1

    answers = collect_answers()
    print("\nDrafting profile and rubric with Claude...", file=sys.stderr)
    profile, rubric = draft_profile_and_rubric(api_key, resume_text, answers)

    config = {
        "profile": _LiteralStr(profile + "\n"),
        "rubric": _LiteralStr(rubric + "\n"),
        "tiers": {
            "target_rows": answers["target_rows"],
            "tier1_bar": answers["tier1_bar"],
            "tier2_bar": answers["tier2_bar"],
        },
        "search": build_search_block(answers),
        "referrals": answers["referrals"],
    }

    with open(args.out, "w") as f:
        f.write("# Generated by scripts/generate_profile.py -- review before relying on it.\n")
        yaml.dump(config, f, sort_keys=False, allow_unicode=True, width=100)

    print(f"\nWrote {args.out}.")
    print("Review it -- especially the rubric weights and the 'Does NOT want' line -- before running the pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
