"""
Regression tests for the hard filters in daily_job_search.py.

These are synthetic job descriptions, not real postings -- fictional companies,
built to reproduce specific failure modes the filters exist to catch. See
docs/runbook.md for the real-world incidents that motivated each one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_job_search import hard_filter  # noqa: E402

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
    base = {
        "jobTitle": title,
        "companyName": company,
        "jobDescription": jd,
        "postedTime": "3 hours ago",
        "location": "Bengaluru, India",
        "yearsOfExperience": {"years": 3},
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
        yearsOfExperience={"years": 10},
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
