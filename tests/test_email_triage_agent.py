from agents.agent_01_email_triage.app.processor import process
from shared.legal_agents.schemas import GenericAgentRequest


def test_email_triage_marks_urgent_court_email():
    request = GenericAgentRequest(
        correlation_id="test-001",
        payload={
            "email_id": "msg-001",
            "from": "clerk@court.gov",
            "subject": "Notice of hearing",
            "body": "A hearing is scheduled for 01/20/2026. Please review immediately.",
            "attachments": [{"filename": "notice.pdf"}],
        },
        metadata={"source": "test"},
    )
    result = process(request)
    assert result["category"] in {"COURT", "URGENT_CLIENT"}
    assert result["urgency_score"] >= 8
    assert result["requires_response"] is True


def test_email_triage_marks_spam():
    request = GenericAgentRequest(
        correlation_id="test-002",
        payload={
            "email_id": "msg-002",
            "from": "marketing@example.com",
            "subject": "Limited offer - SEO for law firms",
            "body": "Unsubscribe here for better rankings.",
        },
        metadata={"source": "test"},
    )
    result = process(request)
    assert result["category"] == "SPAM"
    assert result["requires_response"] is False


def test_email_triage_empty_payload_goes_manual_review():
    request = GenericAgentRequest(correlation_id="test-003", payload={}, metadata={})
    result = process(request)
    assert result["category"] == "NEEDS_MANUAL_REVIEW"
