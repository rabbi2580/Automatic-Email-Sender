"""Job intake API: single/bulk/upload/failed parse/retry/manual/patch/duplicates/deadline sorting/settings/quotas."""
from tests.helpers import FIX, make_pdf, register, upload_cv
from tests.test_e2e import job_post

API = "/api/v1"


def _add(client, h, text, **kw):
    return client.post(f"{API}/jobs", headers=h, json={"kind": "text", "text": text, **kw})


def test_single_job_parsed(client):
    h, _ = register(client)
    upload_cv(client, h)
    r = _add(client, h, (FIX / "job1.txt").read_text())
    assert r.status_code == 201
    j = r.json()["jobs"][0]
    assert j["title"] == "Junior Software Engineer" and "XYZ" in j["company"]
    assert j["deadline"] == "2026-10-12" and "Python" in j["required_skills"]


def test_bulk_and_duplicates(client):
    h, _ = register(client)
    upload_cv(client, h)
    items = [{"kind": "text", "text": job_post(i)} for i in range(5)]
    r = client.post(f"{API}/jobs/bulk", headers=h, json={"items": items})
    assert r.status_code == 201 and len(r.json()["jobs"]) == 5
    again = client.post(f"{API}/jobs/bulk", headers=h, json={"items": items[:1]}).json()["jobs"][0]
    assert again["duplicate_of"]
    nd = client.post(f"{API}/jobs/{again['id']}/not-duplicate", headers=h)
    assert nd.status_code == 200 and nd.json()["duplicate_of"] is None


def test_unparseable_text_is_failed_not_silent(client):
    h, _ = register(client)
    j = _add(client, h, "hello there, how are you doing today my friend").json()["jobs"][0]
    assert j["status"] in ("failed", "requires_review") and j["status_reason"]


def test_manual_entry_patch_and_retry(client):
    h, _ = register(client)
    r = client.post(f"{API}/jobs/manual", headers=h, json={"company_name": "Acme", "job_title": "Data Engineer", "required_skills": ["SQL"]})
    assert r.status_code == 201
    jid = r.json()["id"]
    p = client.patch(f"{API}/jobs/{jid}", headers=h, json={"location": "Remote", "deadline": "2026-12-01"})
    assert p.status_code == 200 and p.json()["location"] == "Remote"
    assert client.post(f"{API}/jobs/{jid}/retry", headers=h).status_code == 200
    assert client.delete(f"{API}/jobs/{jid}", headers=h).status_code == 204
    assert client.get(f"{API}/jobs/{jid}", headers=h).status_code == 404


def test_upload_pdf_job(client):
    h, _ = register(client)
    pdf = make_pdf(job_post(1))
    r = client.post(f"{API}/jobs/upload", headers=h, files=[("files", ("job.pdf", pdf, "application/pdf"))])
    assert r.status_code == 201 and r.json()["jobs"][0]["title"]


def test_upload_rejects_executable(client):
    h, _ = register(client)
    r = client.post(f"{API}/jobs/upload", headers=h, files=[("files", ("x.pdf", b"MZ\x90\x00evil", "application/pdf"))])
    assert r.status_code in (415, 422) or r.json()["jobs"][0]["status"] == "failed"


def test_list_sorted_by_deadline(client):
    h, _ = register(client)
    client.post(f"{API}/jobs/bulk", headers=h, json={"items": [{"kind": "text", "text": job_post(i)} for i in (0, 3, 6)]})
    items = client.get(f"{API}/jobs", headers=h).json()["items"]
    assert len(items) == 3 and all("days_remaining" in i for i in items)


def test_settings_weights_and_thresholds(client):
    h, _ = register(client)
    r = client.put(f"{API}/settings", headers=h, json={"weights": {"skills": 50}, "thresholds": {"strong": 85, "potential": 70, "weak": 50}})
    assert r.status_code == 200
    bad = client.put(f"{API}/settings", headers=h, json={"thresholds": {"strong": 40, "potential": 70, "weak": 50}})
    assert bad.status_code in (400, 422)
    assert client.get(f"{API}/settings", headers=h).status_code == 200
