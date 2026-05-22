# Implementation Notes

## Why separate services?
The brief calls for separate agents with independent triggers and strong auditability. Running each agent as its own service keeps:
- simpler debugging
- easier scaling
- independent deployment
- clearer blast-radius control

## Why Python services under an n8n orchestrator?
Because your earlier issue was installation friction, this scaffold uses:
- Docker for reproducibility
- one pinned root `requirements.txt`
- small FastAPI services
- simple HTTP handoff from n8n to agents

That reduces local setup problems compared with a large custom Node workspace.

## Production hardening next
1. Replace adapter stubs with real Google and Lexis integrations.
2. Add auth between n8n and services.
3. Add audit-log writes for every request.
4. Add real persistence writes in processors.
5. Add Bluebook formatting and verified memo generation.
6. Add background workers and queues if throughput increases.
