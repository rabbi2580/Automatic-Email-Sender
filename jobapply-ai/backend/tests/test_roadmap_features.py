from types import SimpleNamespace

from app.services.cv_quality import ats_score


def test_ats_score_explains_keyword_gaps():
    profile = SimpleNamespace(full_name="A", email="a@example.com", summary="Builder", experiences=[1], educations=[1], skills=[SimpleNamespace(name="Python", canonical="python")])
    job = SimpleNamespace(required_skills=["Python", "Django"], preferred_skills=["Docker"])
    score, report = ats_score(profile, job)
    assert 0 <= score <= 100
    assert report["matched_keywords"] == ["python"]
    assert report["missing_keywords"] == ["django"]


def test_ats_score_handles_empty_job_requirements():
    profile = SimpleNamespace(full_name="", email="", summary="", experiences=[], educations=[], skills=[])
    job = SimpleNamespace(required_skills=[], preferred_skills=[])
    score, report = ats_score(profile, job)
    assert score == 65.0
    assert report["missing_keywords"] == []
