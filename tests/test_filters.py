"""
Regression tests for the hard filters in daily_job_search.py.

These are synthetic job descriptions, not real postings -- fictional companies,
built to reproduce specific failure modes the filters exist to catch. See
docs/runbook.md for the real-world incidents that motivated each one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_job_search import hard_filter, min_years_required  # noqa: E402

MAX_HOURS = 24.0
NO_EXTRA_EXCLUDES = set()

GOOD_JD = """
We're looking for a Backend Engineer to join our platform team. You'll design and
operate distributed microservices handling high-throughput transactional workloads.

Requirements:
- 2-5 years of backend experience with Java or Kotlin
- Experience with Kafka for event streaming
- Postgres and Redis in production
- Kubernetes and Docker on GCP
- Comfortable owning services end to end in a microservices architecture

Location: Bengaluru, hybrid (3 days onsite).
""".strip()


def job(title, company, jd, **overrides):
    # yearsOfExperience matches the real Apify actor's shape: a list of dicts
    # with a free-text "years" range (e.g. "6-9", "6+"), not a single number.
    base = {
        "jobTitle": title,
        "companyName": company,
        "jobDescription": jd,
        "postedTime": "3 hours ago",
        "location": "Bengaluru, India",
        "yearsOfExperience": [{"years": "2-5", "context": "backend experience", "lang": "en"}],
    }
    base.update(overrides)
    return base


def test_android_role_rejected_despite_kotlin_in_title_band():
    jd = (
        GOOD_JD
        + "\n\nStack: Kotlin, Jetpack Compose, AndroidX, native Android development, "
        "Android SDK. You'll build our flagship Android app used by millions of riders."
    )
    j = job("Software Dev Engineer II", "Northwind Mobility", jd)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason is not None
    assert "discipline" in reason


def test_python_ai_role_rejected():
    jd = """
    Join our AI platform team building LLM-powered agentic products. You'll work on
    prompt engineering, RAG pipelines, fine-tuning, and model training with PyTorch
    and TensorFlow. Strong Python required.
    """
    j = job("Software Dev Engineer II", "Globex Labs", jd)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason is not None


def test_cpp_role_rejected_despite_generic_title():
    jd = """
    We build routing protocols and networking stacks in C++. You'll work close to
    the metal on high-performance packet processing systems, BGP, OSPF, and custom
    kernel modules. 3+ years of C++ systems programming required.

    You will own the design and implementation of low-latency packet forwarding
    paths, contribute to our in-house router firmware, and collaborate with the
    silicon team on hardware offload features. Strong systems programming
    fundamentals, deep C++ expertise, and comfort with debugging kernel-level
    issues are essential for this role.
    """
    j = job("Software Engineer", "Initech Networks", jd)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "no JVM language in description"


def test_overqualified_seniority_rejected():
    jd = GOOD_JD + "\n\nRequires 10+ years of professional software engineering experience."
    j = job(
        "Fullstack Java Engineer", "Acme Cloud", jd,
        yearsOfExperience=[{"years": "10+", "context": "professional experience", "lang": "en"}],
    )
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "requires 10+ years"


def test_denylisted_company_rejected_regardless_of_jd_quality():
    j = job("Backend Engineer", "Scoutit", GOOD_JD)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "company excluded"


def test_custom_excluded_company_rejected():
    j = job("Backend Engineer", "Stark Staffing Solutions", GOOD_JD)
    reason = hard_filter(j, MAX_HOURS, {"stark staffing solutions"})
    assert reason == "company excluded"


def test_thin_description_rejected():
    j = job("Backend Engineer", "Acme Cloud", "Join our team. Java required.")
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "description too thin to score"


def test_clean_matching_job_survives():
    j = job("Backend Engineer", "Acme Cloud", GOOD_JD)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason is None


def test_stale_posting_outside_window_rejected():
    j = job("Backend Engineer", "Acme Cloud", GOOD_JD, postedTime="3 days ago")
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "outside posting window"


def test_excluded_title_rejected():
    j = job("Senior Backend Engineer", "Acme Cloud", GOOD_JD)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "title excluded"


def test_underscore_joined_title_still_rejected():
    # Real case from a live pull: a scraped title like
    # "IN_Senior Associate_Guidewire ClaimCenterDev_Guidewire_Advisory_Bangalore"
    # slipped past TITLE_REJECT because "_" counts as a word character, so
    # "\bsenior\b" never found a boundary next to "IN_Senior".
    j = job("IN_Senior Associate_SomeRole_Company_Advisory_Bangalore", "PwC India", GOOD_JD)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason == "title excluded"


def test_automotive_android_rejected_despite_no_exact_mobile_phrasing():
    # Real case: an embedded Android Automotive (AAOS/AOSP) posting used
    # "Android Automotive OS" / "AAOS" / "AOSP" throughout, never the exact
    # "native android" / "android development" phrases JD_REJECT checked for.
    jd = (
        GOOD_JD
        + "\n\nDesign and integrate Apple CarPlay functionality within Android Automotive "
        "OS-based infotainment systems (AAOS). Strong experience in AOSP development, "
        "Binder/AIDL IPC, and Android Automotive platform debugging required."
    )
    j = job("Software Engineer - CarPlay", "HARMAN India", jd)
    reason = hard_filter(j, MAX_HOURS, NO_EXTRA_EXCLUDES)
    assert reason is not None
    assert "discipline" in reason


# min_years_required: real formats observed from a live Apify pull on 2026-07-28
# ("6-9", "3-6", "6+" all seen in the same small sample), plus absent/malformed cases.

def test_years_range_uses_low_end():
    assert min_years_required([{"years": "3-6", "context": "...", "lang": "en"}]) == 3.0


def test_years_high_range_rejected_on_low_end():
    assert min_years_required([{"years": "6-9", "context": "...", "lang": "en"}]) == 6.0


def test_years_open_ended_plus():
    assert min_years_required([{"years": "6+", "context": "...", "lang": "en"}]) == 6.0


def test_years_most_restrictive_entry_wins():
    yoe = [
        {"years": "2-4", "context": "Java", "lang": "en"},
        {"years": "6+", "context": "distributed systems", "lang": "en"},
    ]
    assert min_years_required(yoe) == 6.0


def test_years_absent_field_is_none():
    assert min_years_required(None) is None


def test_years_empty_list_is_none():
    assert min_years_required([]) is None


def test_years_unparseable_string_is_none():
    assert min_years_required([{"years": "not specified"}]) is None


def test_years_not_a_list_is_none():
    # Guards against the actor ever reverting to the single-dict shape this
    # code originally (wrongly) assumed -- should degrade gracefully, not crash.
    assert min_years_required({"years": 3}) is None
