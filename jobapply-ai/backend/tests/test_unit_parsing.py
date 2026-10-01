from datetime import date

import pytest

from app.services.parsing.cv_parser import parse_cv_text
from app.services.parsing.deadlines import days_remaining, extract_deadline, urgency_label
from app.services.parsing.documents import DocumentError, extract_text
from app.services.parsing.job_parser import parse_job_text, split_multiple_jobs
from app.services.parsing.skills import canonicalize, find_skills, similarity
from tests.helpers import FIX, make_pdf

TODAY = date(2026, 10, 2)


def test_cv_parsing_extracts_structure():
    p = parse_cv_text((FIX / "sample_cv.txt").read_text(), TODAY)
    assert p.full_name == "Tarif Ul Haider Rabbi"
    assert p.email == "rabbi@example.com" and p.phone.startswith("+880")
    assert p.location == "Dhaka, Bangladesh"
    assert p.links["linkedin"].endswith("tarif-rabbi") and "github" in p.links
    assert p.educations[0].level == "bachelor" and p.educations[0].grade.startswith("3.31")
    assert p.experiences[0].kind == "internship" and p.experiences[0].is_current and p.experiences[0].company == "Innovative Techworks Group"
    assert {s.name for s in p.skills} >= {"Python", "PyTorch", "Docker", "Django", "PostgreSQL"}
    assert {x.name for x in p.projects} == {"CropXAI-Net", "Blood-Connect"}
    assert p.certifications[0].issuer == "Coursera"
    assert p.languages == ["Bangla (Native)", "English (Fluent)"]
    assert p.years_experience == pytest.approx(0.4, abs=0.1)


def test_cv_parser_never_invents_missing_sections():
    p = parse_cv_text("Jane Roe\njane@roe.org\n\nSKILLS\nPython, SQL\n", TODAY)
    assert p.experiences == [] and p.educations == [] and p.projects == [] and p.certifications == []
    assert [s.name for s in p.skills] == ["Python", "SQL"]


def test_cv_parser_keeps_project_titles_and_stops_before_other_sections():
    text = """Tarif Ul Haider Rabbi
PROJECTS
### Machine Learning - Heart Failure Detection
Data Science & Machine Learning
Data preprocessing, feature engineering, classification models, and accuracy analysis.
GitHub: https://github.com/rabbi2580/Machine-Learning--Heart-Failure-Disease
### Natural Language Processing - AgriBot - AI-Powered Agricultural Assistant
Developed a Bengali AI chatbot using NLP and Sentence-BERT semantic search.
GitHub: https://github.com/rabbi2580/AgriBot_BD
Extra Curricular Activities
Taroonor Progoti Foundation, Advisor
2019 - Present
Certifications & Professional Training
Code to Cloud: Practical DevOps with AWS, Cloudly Infotech Limited
03/2026
Strengths & Interests
* Strong command of English
* Passionate about innovation and creative problem-solving
References
A. K. M. Abdul Halim, Head of Network
"""

    profile = parse_cv_text(text, TODAY)

    assert [project.name for project in profile.projects] == [
        "Machine Learning - Heart Failure Detection",
        "Natural Language Processing - AgriBot - AI-Powered Agricultural Assistant",
    ]
    assert profile.extracurriculars == ["Taroonor Progoti Foundation, Advisor", "2019 - Present"]
    assert all("Strong command" not in project.name for project in profile.projects)


def test_cv_parser_separates_requested_profile_sections():
    text = """Tarif Rabbi
Personal Information / Contact Information
tarif@example.com
Dhaka, Bangladesh
Professional Summary / Career Objective
Computer science graduate interested in machine learning.
Work Experience
Backend Engineer | Example Ltd | 2024 - 2025
* Built APIs with Python.
Internship Experience
Software Engineer Intern | Startup Ltd | 2023 - 2024
* Developed Django features.
Volunteer Experience
Volunteer Tutor | Community Group | 2022 - 2023
* Taught programming.
Projects
### Heart Failure Detection
Built a classification model.
Certifications / Courses
Code to Cloud: Cloudly Infotech | 03/2026
Achievements / Awards
Dean's List
Research / Publications
Efficient Crop Classification, Journal of AI
Extracurricular Activities
Youth Organization, Event Director
Languages
English, Bangla
Strengths & Interests
* Strong communication
* Creative problem-solving
References
Dr. Example, Example University, example@example.com
"""

    profile = parse_cv_text(text, TODAY)

    assert [(item.kind, item.title) for item in profile.experiences] == [
        ("work", "Backend Engineer"),
        ("internship", "Software Engineer Intern"),
        ("volunteer", "Volunteer Tutor"),
    ]
    assert profile.strengths == ["Strong communication", "Creative problem-solving"]
    assert profile.references == ["Dr. Example, Example University, example@example.com"]
    assert profile.achievements == ["Dean's List"]
    assert profile.publications == ["Efficient Crop Classification, Journal of AI"]
    assert profile.extracurriculars == ["Youth Organization, Event Director"]
    assert profile.languages == ["English", "Bangla"]


def test_job_parsing_messy_post():
    j = parse_job_text((FIX / "job1.txt").read_text(), TODAY)
    assert j.company == "XYZ Technologies Ltd" and j.job_title == "Junior Software Engineer"
    assert j.application_email == "hr@xyz.com" and j.deadline == date(2026, 10, 12)
    assert (j.min_years, j.max_years) == (1.0, 3.0)
    assert {"Python", "Django", "Docker"} <= set(j.required_skills) and "AWS" in j.preferred_skills
    assert j.workplace_type == "hybrid" and j.education_level == "bachelor" and j.salary.startswith("BDT")


def test_job_parser_does_not_hallucinate():
    j = parse_job_text("Looking for someone good with computers. Call us.", TODAY)
    assert j.company == "" and j.job_title == "" and j.application_email == "" and j.deadline is None
    assert any("Company name" in w for w in j.warnings)


def test_non_job_text_flagged():
    assert parse_job_text("hey are you coming to dinner tonight? bring snacks please").is_job_posting is False


def test_split_multiple_jobs():
    t = "Job 1\nML Engineer at Foo Ltd\nRequirements: Python\nsend cv to a@foo.com\n---\nPosition 2\nData Analyst\nCompany: Bar Inc\nRequirements: SQL, Excel\nApply: https://bar.com/careers/1"
    parts = split_multiple_jobs(t)
    assert len(parts) == 2 and "Bar Inc" in parts[1]


@pytest.mark.parametrize("text,expected", [
    ("Application Deadline: October 12, 2026", date(2026, 10, 12)),
    ("Last date of application: 12th Oct", date(2026, 10, 12)),
    ("apply by 15-10-2026", date(2026, 10, 15)),
    ("Deadline 2026-11-03", date(2026, 11, 3)),
    ("Send CV before 20 January 2027", date(2027, 1, 20)),
    ("Join our party on 5 Oct 2026", None),  # a date without a deadline cue is not a deadline
    ("No date here", None),
])
def test_deadline_extraction(text, expected):
    assert extract_deadline(text, TODAY) == expected


def test_deadline_remaining_and_urgency():
    assert days_remaining(date(2026, 10, 12), TODAY) == 10
    assert days_remaining(None) is None
    assert [urgency_label(d) for d in (None, -1, 2, 6, 20)] == ["none", "expired", "critical", "soon", "ok"]


def test_skill_taxonomy():
    assert canonicalize("postgres") == "PostgreSQL" and canonicalize("k8s") == "Kubernetes"
    assert "C++" in find_skills("Experienced in C++ and C#") and "C#" in find_skills("Experienced in C++ and C#")
    assert "Go" not in find_skills("We love to go home")  # ambiguous token needs a skill-list context
    assert similarity("PostgreSQL", {"MySQL"}) == 0.5 and similarity("PostgreSQL", {"React"}) == 0.0


def test_document_extraction_pdf_and_errors():
    doc = extract_text(make_pdf((FIX / "sample_cv.txt").read_text()), "x.pdf")
    assert "Tarif" in doc.text and doc.kind == "pdf"
    with pytest.raises(DocumentError) as e:
        extract_text(b"", "x.pdf")
    assert e.value.code == "empty"
    with pytest.raises(DocumentError):
        extract_text(b"\x00\x01\x02\xff\xfe binary", "x.bin")
    with pytest.raises(DocumentError) as e:
        extract_text(b"%PDF-1.4 garbage", "x.pdf")
    assert e.value.code in ("corrupt", "too_little_text")
