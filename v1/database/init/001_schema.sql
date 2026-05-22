CREATE TABLE IF NOT EXISTS matters (
  matter_id SERIAL PRIMARY KEY,
  matter_name VARCHAR(255),
  client_name VARCHAR(255),
  matter_type VARCHAR(100),
  opened_date DATE,
  status VARCHAR(50),
  billing_type VARCHAR(50),
  priority_tier INT,
  client_tier INT DEFAULT 3
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id SERIAL PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  description TEXT,
  matter_id INT REFERENCES matters(matter_id),
  created_at TIMESTAMP DEFAULT NOW(),
  due_date DATE,
  priority_score INT,
  status VARCHAR(50),
  assigned_to VARCHAR(100),
  source VARCHAR(100),
  parent_task_id INT REFERENCES tasks(task_id),
  completed_at TIMESTAMP,
  tags TEXT[],

  priority_reasoning TEXT,
  recommended_deadline DATE,
  sheet_row_id VARCHAR(100),
  last_synced_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT NOW(),
  manual_priority_override INT,
  manual_priority_note TEXT,
  escalation_level INT DEFAULT 0,
  last_escalated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_log (
  id SERIAL PRIMARY KEY,
  email_id VARCHAR(255) UNIQUE,
  received_at TIMESTAMP,
  sender VARCHAR(255),
  subject TEXT,
  category VARCHAR(100),
  urgency_score INT,
  requires_response BOOLEAN,
  draft_created BOOLEAN,
  action_items JSONB,
  processed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meetings (
  meeting_id SERIAL PRIMARY KEY,
  title TEXT,
  attendees JSONB,
  scheduled_time TIMESTAMP,
  duration INT,
  matter_id INT REFERENCES matters(matter_id),
  calendar_event_id VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  status VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS document_index (
  doc_id SERIAL PRIMARY KEY,
  filename TEXT,
  matter_id INT REFERENCES matters(matter_id),
  doc_type VARCHAR(100),
  file_path TEXT,
  upload_date TIMESTAMP DEFAULT NOW(),
  doc_date DATE,
  extracted_text TEXT,
  parties JSONB,
  contains_deadline BOOLEAN DEFAULT FALSE,
  deadline_date DATE,
  file_size BIGINT,
  file_hash VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS research_requests (
  request_id SERIAL PRIMARY KEY,
  matter_id INT REFERENCES matters(matter_id),
  research_question TEXT,
  jurisdiction VARCHAR(100),
  requested_by VARCHAR(100),
  requested_at TIMESTAMP DEFAULT NOW(),
  status VARCHAR(50),
  completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_citations (
  citation_id SERIAL PRIMARY KEY,
  request_id INT REFERENCES research_requests(request_id),
  case_citation VARCHAR(255),
  case_name TEXT,
  jurisdiction VARCHAR(100),
  court VARCHAR(100),
  decision_date DATE,
  full_text_lexis TEXT,
  headnotes TEXT,
  shepards_status VARCHAR(50),
  negative_treatment BOOLEAN,
  treatment_details TEXT,
  lexis_api_response JSONB,
  pulled_at TIMESTAMP DEFAULT NOW(),
  confidence_score VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS citation_quotes (
  quote_id SERIAL PRIMARY KEY,
  citation_id INT REFERENCES case_citations(citation_id),
  quote_text TEXT,
  quote_verified BOOLEAN,
  page_number VARCHAR(20),
  paragraph_number INT,
  context TEXT,
  used_in_memo BOOLEAN DEFAULT FALSE,
  verification_timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification_log (
  log_id SERIAL PRIMARY KEY,
  citation_id INT REFERENCES case_citations(citation_id),
  stage VARCHAR(50),
  status VARCHAR(50),
  details TEXT,
  confidence_score VARCHAR(20),
  flagged_for_review BOOLEAN DEFAULT FALSE,
  logged_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deadlines (
  deadline_id SERIAL PRIMARY KEY,
  matter_id INT REFERENCES matters(matter_id),
  deadline_type VARCHAR(100),
  deadline_date DATE,
  description TEXT,
  source VARCHAR(100),
  reminder_schedule JSONB,
  status VARCHAR(50),
  completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
  id SERIAL PRIMARY KEY,
  agent_slug VARCHAR(100),
  action VARCHAR(255),
  correlation_id VARCHAR(255),
  payload JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_log (
  id SERIAL PRIMARY KEY,
  agent_slug VARCHAR(100),
  correlation_id VARCHAR(255),
  error_message TEXT,
  payload JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
