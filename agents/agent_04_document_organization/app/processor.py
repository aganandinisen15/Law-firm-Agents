from shared.legal_agents.schemas import GenericAgentRequest

def process(request: GenericAgentRequest):
    payload = request.payload
    filename = payload.get("filename", "document.pdf")
    matter = payload.get("matter_name", "UnknownMatter").replace(" ", "")
    doc_type = payload.get("document_type", "misc")
    new_name = f"{payload.get('document_date', '2026-01-01')}_{matter}_{doc_type}_{payload.get('description', 'FiledDocument')}.pdf"
    return {
        "summary": "Document organization analysis complete.",
        "document_type": doc_type,
        "renamed_file": new_name,
        "target_folder": f"/Clients/{payload.get('client_name', 'Unknown Client')}/{payload.get('matter_name', 'Unknown Matter')}/09 - Miscellaneous/",
        "warnings": [] if payload.get("matter_name") else ["Matter name not supplied; manual review may be required."]
    }
