from fastapi import FastAPI
from shared.legal_agents.base_agent import build_router
from shared.legal_agents.logging_utils import configure_logging
from shared.legal_agents.settings import settings
from .processor import process

configure_logging(settings.log_level)

app = FastAPI(title="Matter Orchestration Agent", version="0.1.0")
app.include_router(build_router("matter_orchestration", "Matter Orchestration Agent", process))
