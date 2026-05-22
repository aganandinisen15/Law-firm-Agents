INSERT INTO matters (matter_name, client_name, matter_type, opened_date, status, billing_type, priority_tier)
VALUES
('Sample LLC Governance', 'Sample Client', 'corporate', CURRENT_DATE, 'active', 'hourly', 1),
('Example Lease Dispute', 'Example Client', 'litigation', CURRENT_DATE, 'active', 'hourly', 1)
ON CONFLICT DO NOTHING;
