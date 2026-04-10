# Email Triage Agent Troubleshooting

## 1) Service does not start
Run:
```bash
docker compose logs -f email-triage
```
Check for:
- missing `.env`
- bad `PYTHONPATH`
- package install errors

## 2) Database logging fails
Start database first:
```bash
docker compose up -d postgres
```
Then confirm schema loaded:
```bash
docker compose exec postgres psql -U legal -d legal_agents -c "\dt"
```

## 3) Claude call fails
Keep this off until credentials work:
```env
EMAIL_TRIAGE_USE_CLAUDE=false
```
Once ready, add a real key and restart:
```bash
docker compose up -d --build email-triage
```

## 4) Agent works but Gmail actions are not real
That is expected in this safe build. The Gmail methods are stubs so the project can install and run without OAuth setup failures.

## 5) Run tests
```bash
pytest tests/test_email_triage_agent.py -q
```
