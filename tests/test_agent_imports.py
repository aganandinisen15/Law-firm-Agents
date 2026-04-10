from fastapi.testclient import TestClient

from agents.agent_01_email_triage.app.main import app as app1
from agents.agent_02_calendar_scheduling.app.main import app as app2
from agents.agent_03_task_priority.app.main import app as app3
from agents.agent_04_document_organization.app.main import app as app4
from agents.agent_05_legal_research.app.main import app as app5
from agents.agent_06_deadline_tracking.app.main import app as app6
from agents.agent_07_contract_review.app.main import app as app7
from agents.agent_08_client_intake.app.main import app as app8
from agents.agent_09_memo_drafting.app.main import app as app9
from agents.agent_10_matter_orchestration.app.main import app as app10


def test_health_routes():
    for app in [app1, app2, app3, app4, app5, app6, app7, app8, app9, app10]:
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
