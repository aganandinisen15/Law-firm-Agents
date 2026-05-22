from shared.legal_agents.schemas import GenericAgentRequest

def process(request: GenericAgentRequest):
    payload = request.payload
    citations = payload.get("verified_citations", [])
    if not citations:
        return {
            "summary": "Memo draft blocked.",
            "status": "blocked",
            "warnings": ["Verified citations are required before memo drafting."]
        }
    return {
        "summary": "Memo outline prepared.",
        "sections": ["Question Presented", "Short Answer", "Analysis", "Conclusion"],
        "citation_count": len(citations),
        "warnings": []
    }
