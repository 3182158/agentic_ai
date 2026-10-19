PRAGMA foreign_keys = ON;

CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY CHECK (employee_id GLOB 'E[0-9][0-9][0-9]'),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    manager_id TEXT REFERENCES employees(employee_id),
    access_role TEXT NOT NULL CHECK (access_role IN ('employee', 'manager', 'it_admin')),
    office_location TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE tickets (
    ticket_id TEXT PRIMARY KEY CHECK (ticket_id GLOB 'INC-[0-9][0-9][0-9][0-9]'),
    owner_employee_id TEXT NOT NULL REFERENCES employees(employee_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('VPN', 'Network', 'Hardware', 'Software', 'MFA', 'Email', 'Access', 'Printer', 'Other')),
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'pending', 'resolved', 'closed')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    assigned_to TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE leave_balances (
    employee_id TEXT PRIMARY KEY REFERENCES employees(employee_id),
    annual_entitlement REAL NOT NULL CHECK (annual_entitlement >= 0),
    sick_entitlement REAL NOT NULL CHECK (sick_entitlement >= 0),
    carry_forward_entitlement REAL NOT NULL CHECK (carry_forward_entitlement >= 0),
    annual_used REAL NOT NULL CHECK (annual_used >= 0),
    sick_used REAL NOT NULL CHECK (sick_used >= 0),
    carry_forward_used REAL NOT NULL CHECK (carry_forward_used >= 0),
    as_of_date TEXT NOT NULL,
    CHECK (annual_used <= annual_entitlement),
    CHECK (sick_used <= sick_entitlement),
    CHECK (carry_forward_used <= carry_forward_entitlement)
);

CREATE TABLE leave_history (
    request_id TEXT PRIMARY KEY CHECK (request_id GLOB 'LR-[0-9][0-9][0-9][0-9]'),
    employee_id TEXT NOT NULL REFERENCES employees(employee_id),
    leave_type TEXT NOT NULL CHECK (leave_type IN ('annual', 'sick', 'carry_forward')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days REAL NOT NULL CHECK (days > 0),
    status TEXT NOT NULL CHECK (status IN ('approved', 'rejected', 'pending', 'cancelled')),
    submitted_at TEXT NOT NULL,
    decided_at TEXT,
    approver_employee_id TEXT REFERENCES employees(employee_id),
    notes TEXT NOT NULL DEFAULT '',
    CHECK (end_date >= start_date)
);

CREATE TABLE approval_requests (
    approval_id TEXT PRIMARY KEY CHECK (approval_id GLOB 'APR-[0-9][0-9][0-9][0-9]'),
    action_type TEXT NOT NULL CHECK (action_type IN ('create_ticket', 'apply_leave', 'request_access')),
    requester_employee_id TEXT NOT NULL REFERENCES employees(employee_id),
    approver_employee_id TEXT NOT NULL REFERENCES employees(employee_id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    decision_note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_tickets_owner_status ON tickets(owner_employee_id, status);
CREATE INDEX idx_tickets_status_priority ON tickets(status, priority);
CREATE INDEX idx_leave_history_employee_dates ON leave_history(employee_id, start_date DESC);
CREATE INDEX idx_approvals_approver_status ON approval_requests(approver_employee_id, status);

CREATE VIEW leave_balance_summary AS
SELECT
    e.employee_id,
    e.full_name,
    b.as_of_date,
    b.annual_entitlement,
    b.annual_used,
    b.annual_entitlement - b.annual_used AS annual_remaining,
    b.sick_entitlement,
    b.sick_used,
    b.sick_entitlement - b.sick_used AS sick_remaining,
    b.carry_forward_entitlement,
    b.carry_forward_used,
    b.carry_forward_entitlement - b.carry_forward_used AS carry_forward_remaining,
    (b.annual_entitlement - b.annual_used)
      + (b.sick_entitlement - b.sick_used)
      + (b.carry_forward_entitlement - b.carry_forward_used) AS total_remaining
FROM employees AS e
JOIN leave_balances AS b USING (employee_id);
