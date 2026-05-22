# Troubleshooting

## Docker build fails
Run:
```bash
docker compose down -v
docker compose build --no-cache
docker compose up
```

## Postgres connection refused
Wait for the `postgres` healthcheck to pass:
```bash
docker ps
docker logs legal-postgres
```

## n8n cannot connect to Postgres
Verify the `POSTGRES_*` variables in `.env`.

## Google auth errors
Double-check the service account file path or OAuth settings.

## LexisNexis endpoint mismatch
Update `shared/legal_agents/adapters.py` to your tenant's real contract.
The research agent is designed to stop instead of fabricating authority.

## Anthropic model errors
Update `ANTHROPIC_MODEL` in `.env` if your account uses another model name.

## Local import errors
Run with `PYTHONPATH=.` or use Docker.

## OCR
OCR is intentionally optional in this scaffold to avoid system package install issues.
Add Google Vision or Tesseract only when the target environment is confirmed.
