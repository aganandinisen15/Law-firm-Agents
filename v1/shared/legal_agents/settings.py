from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://legal:legal@localhost:5432/legal_agents"
    database_url_sync: str = "postgresql://legal:legal@localhost:5432/legal_agents"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    lexisnexis_base_url: str = "https://api.lexisnexis.example"
    lexisnexis_api_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    gmail_mailbox_user: str = "me"
    gmail_default_query: str = "in:inbox -category:promotions -category:social"

    google_service_account_json_path: str = ""
    google_workspace_impersonation_user: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    alert_sms_to: str = ""

    email_triage_use_claude: bool = False
    email_triage_save_draft_stub: bool = True
    email_triage_label_processed: str = "Processed"
    email_triage_label_pending_review: str = "Drafts Pending Review"
    email_triage_label_manual_review: str = "NEEDS_MANUAL_REVIEW"
    email_triage_urgent_threshold: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
