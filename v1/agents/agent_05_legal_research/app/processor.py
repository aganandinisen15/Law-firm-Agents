from shared.legal_agents.schemas import GenericAgentRequest
from shared.legal_agents.adapters import LexisNexisAdapter

lexis = LexisNexisAdapter()

def process(request: GenericAgentRequest):
    payload = request.payload
    question = payload.get("research_question", "")
    jurisdiction = payload.get("jurisdiction", "California")
    cases = lexis.search_cases(question, jurisdiction)
    selected = cases[:1]
    pulled = [lexis.pull_case(c["case_id"]) for c in selected]
    verified = []
    for case in pulled:
        shep = lexis.shepardize(case["citation"])
        quote = case["full_text"]
        verified.append({
            "case_name": case["case_name"],
            "citation": case["citation"],
            "quote": quote,
            "page_number": case["page_number"],
            "shepards_status": shep["status"],
            "verified": True
        })
    return {
        "summary": "Research request processed with development-only placeholder verification.",
        "research_question": question,
        "jurisdiction": jurisdiction,
        "verified_citations": verified,
        "memo_ready": all(item["verified"] and item["shepards_status"] == "good_law" for item in verified),
        "warnings": [
            "Replace LexisNexis adapter stubs with real tenant endpoints before production use.",
            "Memo generation must not proceed on unverified citations."
        ]
    }
