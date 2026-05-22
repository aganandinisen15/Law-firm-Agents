from fastapi import APIRouter
from .schemas import HealthResponse, GenericAgentRequest, GenericAgentResponse


def build_router(agent_slug: str, agent_title: str, processor):
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", agent=agent_title)

    @router.post("/run", response_model=GenericAgentResponse)
    def run_agent(request: GenericAgentRequest):
        result = processor(request)
        return GenericAgentResponse(
            agent=agent_slug,
            status="ok",
            summary=result.get("summary", f"{agent_title} processed request."),
            data=result,
            warnings=result.get("warnings", []),
        )

    return router
