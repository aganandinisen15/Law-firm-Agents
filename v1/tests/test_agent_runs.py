from fastapi.testclient import TestClient

from agents.agent_01_email_triage.app.main import app as app1
from agents.agent_05_legal_research.app.main import app as app5
from agents.agent_09_memo_drafting.app.main import app as app9


def test_email_triage_run():
    client = TestClient(app1)
    payload = {"payload": {"subject": "Urgent hearing tomorrow", "body": "Please call me ASAP"}}
    response = client.post("/run", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["category"] == "URGENT_CLIENT"


def test_legal_research_run():
    client = TestClient(app5)
    payload = {"payload": {"research_question": "Can an LLC operating agreement restrict member voting rights in California?", "jurisdiction": "California"}}
    response = client.post("/run", json=payload)
    assert response.status_code == 200
    assert "verified_citations" in response.json()["data"]


def test_memo_drafting_requires_citations():
    client = TestClient(app9)
    response = client.post("/run", json={"payload": {}})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "blocked"
