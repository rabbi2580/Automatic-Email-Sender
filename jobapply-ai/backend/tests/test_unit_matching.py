import pytest

from app.services.dedupe import content_hash, find_duplicate, norm_company, norm_url
from app.services.matching.engine import CandidateView, JobView, classify, compute_match, normalise_thresholds, normalise_weights


def cand(**kw):
    base = dict(skills={"Python", "Django", "Docker", "Git", "MySQL", "Machine Learning", "PyTorch", "SQL"}, years_experience=2.0, education_level="bachelor",
                education_text="B.Sc. Computer Science and Engineering", experience_text="Built REST APIs using Python and Django; wrote unit tests",
                project_text="Trained PyTorch model", past_titles=["Software Engineer"], headline="", target_roles=["Software Engineer"], location="Dhaka, Bangladesh",
                preferred_locations=["Dhaka"], has_experience_entries=True, has_projects=True)
    base.update(kw)
    return CandidateView(**base)


def job(**kw):
    base = dict(title="Software Engineer", required_skills=["Python", "Django", "Docker"], preferred_skills=["AWS"], tech_stack=["Python", "Django", "PostgreSQL"],
                responsibilities=["Build REST APIs using Python and Django", "Write unit tests"], min_years=1, max_years=3, education_level="bachelor",
                education_fields=["Computer Science"], location="Dhaka", workplace_type="onsite")
    base.update(kw)
    return JobView(**base)


def test_good_match_is_high_and_explained():
    r = compute_match(cand(), job())
    assert r["score"] >= 85 and r["classification"] in ("potential", "strong")
    assert {"Python", "Django", "Docker"} <= set(r["strong_matches"])
    assert any(m["skill"] == "AWS" for m in r["missing"])
    assert "Match:" in r["explanation"] and "Strong matches" in r["explanation"] and "not a prediction" in r["explanation"]
    assert set(r["dimensions"]) == {"skills", "experience", "education", "responsibilities", "technology", "role", "location"}
    assert r["dimensions"]["technology"]["score"] > 0.5


def test_partial_credit_for_related_skills():
    r = compute_match(cand(), job(required_skills=["PostgreSQL"], preferred_skills=[], tech_stack=[]))
    assert r["partial_matches"] and r["partial_matches"][0]["skill"] == "PostgreSQL" and "MySQL" in r["partial_matches"][0]["via"]


def test_weak_candidate_scores_low():
    weak = cand(skills={"Excel"}, years_experience=0, education_level="secondary", education_text="HSC", experience_text="", project_text="",
                past_titles=["Cashier"], target_roles=["Accountant"], location="Chittagong", preferred_locations=["Chittagong"], has_experience_entries=False, has_projects=False)
    r = compute_match(weak, job(min_years=5, max_years=8))
    assert r["score"] < 40 and r["classification"] == "not_suitable" and r["concerns"]


def test_missing_info_dimensions_are_excluded_not_penalised():
    sparse = job(responsibilities=[], min_years=None, max_years=None, education_level="", education_fields=[], location="", workplace_type="", tech_stack=[])
    r = compute_match(cand(), sparse)
    assert r["dimensions"]["experience"]["score"] is None and r["dimensions"]["experience"]["effective_weight"] == 0
    assert r["score"] >= 80 and "Not scored" in r["explanation"]
    eff = sum(d["effective_weight"] for d in r["dimensions"].values())
    assert eff == pytest.approx(1.0, abs=0.01)


def test_weights_are_configurable():
    only_exp = compute_match(cand(years_experience=0.0), job(min_years=2), {"skills": 0, "experience": 100, "education": 0, "responsibilities": 0, "technology": 0, "role": 0, "location": 0})
    only_skill = compute_match(cand(years_experience=0.0), job(min_years=2), {"skills": 100, "experience": 0, "education": 0, "responsibilities": 0, "technology": 0, "role": 0, "location": 0})
    assert only_exp["score"] < 30 < only_skill["score"]
    assert normalise_weights({"skills": -5})["skills"] == 0
    assert normalise_weights({k: 0 for k in ("skills", "experience", "education", "responsibilities", "technology", "role", "location")})["skills"] == 30  # all-zero → defaults


def test_thresholds_configurable_and_validated():
    assert [classify(s) for s in (95, 80, 65, 40)] == ["strong", "potential", "weak", "not_suitable"]
    assert classify(70, {"strong": 80, "potential": 60, "weak": 40}) == "potential"
    assert normalise_thresholds({"strong": 50, "potential": 70, "weak": 10}) == {"strong": 90.0, "potential": 75.0, "weak": 60.0}  # invalid ordering → defaults


def test_seniority_concern():
    r = compute_match(cand(years_experience=0.5), job(title="Senior Software Engineer", min_years=5))
    assert any("senior" in c.lower() or "Seniority" in c for c in r["concerns"])


def test_remote_preference_conflict():
    r = compute_match(cand(work_preference="remote"), job(location="Dhaka", workplace_type="onsite"))
    assert r["dimensions"]["location"]["score"] <= 0.3


# ---- duplicates
A = dict(id=1, company_name="XYZ Technologies Ltd.", job_title="Junior Software Engineer", application_email="hr@xyz.com", application_url="https://xyz.com/jobs/1?utm_source=fb",
         source_url="", original_content="We need a junior software engineer to build python apis for our team in dhaka send cv", content_hash=content_hash("a"))


def test_duplicates_detected_by_each_signal():
    assert find_duplicate(dict(A, id=2, content_hash="zzz", application_url="https://www.xyz.com/jobs/1/"), [A]).reasons[0] == "same URL"
    d = find_duplicate(dict(A, id=3, company_name="XYZ Technologies Limited", job_title="URGENT: Junior Software Engineer", content_hash="q", original_content="totally different words here", application_url=""), [A])
    assert d and "same company and title" in d.reasons
    d = find_duplicate(dict(A, id=4, company_name="Other Name", content_hash="q", application_url="", job_title="junior software engineer"), [A])
    assert d and "same application email and title" in d.reasons
    d = find_duplicate(dict(A, id=5, company_name="", job_title="", application_email="", application_url="", content_hash="q"), [A])
    assert d and d.score >= 0.82  # near-identical text only


def test_distinct_jobs_not_flagged():
    b = dict(A, id=9, company_name="Other Co", job_title="Data Analyst", application_email="x@o.com", application_url="", content_hash="h2",
             original_content="completely different post about excel reporting duties for finance team")
    assert find_duplicate(b, [A]) is None
    # same text at two different employers with different contacts is two openings, not a duplicate
    c = dict(A, id=10, company_name="Different Employer", application_email="other@e.com", application_url="", content_hash="h3")
    assert find_duplicate(c, [A]) is None


def test_normalisers():
    assert norm_company("ABC Ltd.") == norm_company("abc limited") == "abc"
    assert norm_url("https://www.X.com/a/?utm_source=z&id=3") == "x.com/a?id=3"
