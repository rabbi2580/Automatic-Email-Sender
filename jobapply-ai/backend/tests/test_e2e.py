"""End-to-end: account → CV → 20 jobs → match → generate 10 → review → approve 3 → send → track."""
from sqlalchemy import select

from app.models import Application
from tests.helpers import connect_gmail_account, install_fake_gmail, register, upload_cv, FIX

JOB_TEMPLATES = [
    ("Junior Software Engineer", "XYZ Technologies Ltd", "Python, Django, Docker, Git", "hr@xyz.com"),
    ("Backend Developer", "Alpha Systems Ltd", "Python, FastAPI, PostgreSQL, Docker", "jobs@alpha.com"),
    ("Machine Learning Engineer", "Beta AI Limited", "Python, PyTorch, scikit-learn, Pandas", "careers@beta.ai"),
    ("Data Analyst", "Gamma Analytics Ltd", "SQL, Excel, Power BI, Tableau", "apply@gamma.com"),
    ("Senior DevOps Engineer", "Delta Cloud Ltd", "Kubernetes, Terraform, AWS, Jenkins, 6+ years of experience", "hr@delta.com"),
    ("Frontend Developer", "Epsilon Web Ltd", "React, TypeScript, CSS, HTML", "hr@epsilon.com"),
    ("AI Engineer", "Zeta Labs Ltd", "Python, PyTorch, Deep Learning, Computer Vision", "hire@zeta.com"),
    ("Software Engineer", "Eta Software Ltd", "Java, Spring Boot, MySQL, Git", "hr@eta.com"),
]


def job_post(i):
    title, company, skills, email = JOB_TEMPLATES[i % len(JOB_TEMPLATES)]
    if i >= len(JOB_TEMPLATES):  # distinct openings at other employers
        company = company.replace("Ltd", f"{i} Ltd")
        email = email.replace("@", f"{i}@")
    return (f"WE ARE HIRING!!!\n\n{title}\n\nCompany: {company}\nLocation: Dhaka, Bangladesh\n\nResponsibilities:\n- Build and maintain software using {skills.split(',')[0]}\n"
            f"- Work with the team on features and testing\n\nRequirements:\n- B.Sc. in CSE or related field\n- Good knowledge of {skills}\n\n"
            f"Application Deadline: October {10 + (i % 15)}, 2026\nSend your CV to {email}")


def test_full_flow(client, db):
    ch = install_fake_gmail()
    headers, _ = register(client)

    r = upload_cv(client, headers)
    assert r.status_code == 201 and r.json()["status"] in ("completed", "requires_review"), r.text
    prof = client.get("/api/v1/profile", headers=headers).json()
    assert prof["full_name"] == "Tarif Ul Haider Rabbi" and len(prof["skills"]) >= 10
    assert prof["completeness"]["percent"] > 0

    # 20 job posts at once (pasted as separate items)
    items = [{"kind": "text", "text": job_post(i)} for i in range(20)]
    r = client.post("/api/v1/jobs/bulk", headers=headers, json={"items": items})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"]["total"] == 20 and body["summary"]["processed"] == 20, body["summary"]
    assert all(j["match"] for j in body["jobs"])
    scores = sorted((j["match"]["score"], j["title"]) for j in body["jobs"])
    assert scores[0][0] < scores[-1][0]  # scores discriminate

    # pick 10 jobs and generate applications
    best = [j for j in client.get("/api/v1/matches?hide_duplicates=true", headers=headers).json()][:10]
    assert len(best) == 10
    connect_gmail_account(db)
    r = client.post("/api/v1/applications/generate", headers=headers, json={"job_ids": [j["id"] for j in best]})
    assert r.status_code == 202, r.text
    apps = client.get("/api/v1/applications", headers=headers).json()["items"]
    assert len(apps) == 10
    assert all(a["generation_status"] == "completed" and a["status"] == "awaiting_review" for a in apps), [(a["generation_status"], a["status"], a["generation_reason"]) for a in apps]

    # nothing was sent automatically
    assert ch.sent == []

    # review one in detail
    d = client.get(f"/api/v1/applications/{apps[0]['id']}", headers=headers).json()
    assert d["qc"]["passed"], d["qc"]
    assert {x["kind"] for x in d["documents"]} >= {"cv_pdf", "cv_docx", "cv_tex", "cover_letter_pdf"}
    assert d["email"]["to_address"] and d["email"]["subject"].startswith("Application for")
    assert d["cover_letter"]["body"].startswith("Dear Hiring Manager")

    # approve 3
    ids = [a["id"] for a in apps[:3]]
    r = client.post("/api/v1/applications/approve-bulk", headers=headers, json={"application_ids": ids})
    assert r.json()["approved"] == 3, r.text

    # cannot send without preview token / confirmation
    r = client.post("/api/v1/applications/send", headers=headers, json={"application_ids": ids, "confirmation_token": "bogus", "confirm": True})
    assert r.status_code == 409
    prev = client.post("/api/v1/applications/send/preview", headers=headers, json={"application_ids": ids}).json()
    assert prev["count"] == 3 and prev["confirmation_token"] and all(i["to"] and i["attachments"] for i in prev["items"])
    r = client.post("/api/v1/applications/send", headers=headers, json={"application_ids": ids, "confirmation_token": prev["confirmation_token"], "confirm": False})
    assert r.status_code == 422 and ch.sent == []
    r = client.post("/api/v1/applications/send", headers=headers, json={"application_ids": ids, "confirmation_token": prev["confirmation_token"], "confirm": True})
    assert r.status_code == 200 and r.json()["sent"] == 3, r.text
    assert len(ch.sent) == 3 and all(len(m.attachments) == 2 for m in ch.sent)

    # re-sending is idempotent (token reuse can't double send)
    r = client.post("/api/v1/applications/send", headers=headers, json={"application_ids": ids, "confirmation_token": prev["confirmation_token"], "confirm": True})
    assert len(ch.sent) == 3

    # tracking
    a = client.patch(f"/api/v1/applications/{ids[0]}", headers=headers, json={"status": "interview", "notes": "Phone screen Monday"}).json()
    assert a["status"] == "interview"
    an = client.get("/api/v1/analytics", headers=headers).json()["cards"]
    assert an["jobs_added"] == 20 or an["jobs_added"] > 0
    assert an["applications_sent"] == 3 and an["interviews"] == 1 and an["pending_review"] == 7
    assert an["response_rate"] == round(100 * 1 / 3, 1)
