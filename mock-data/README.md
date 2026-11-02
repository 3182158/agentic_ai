# Acme Helpdesk Mock Data

Deterministic, fictional datasets for the Enterprise Helpdesk Agent workshop. Nothing in this folder represents a real company, employee, credential, or policy. Use these records for demos, tests, and retrieval experiments—not as operational guidance.

## Contents

- `sqlite/acme_helpdesk.sqlite3` — ready-to-query SQLite database.
- `sqlite/schema.sql` — tables, constraints, indexes, and the leave-balance summary view.
- `sqlite/seed.sql` — deterministic seed records.
- `sqlite/build_database.py` — rebuilds the database using Python's standard library.
- `documents/policies/` — five long merged handbooks/policies (IT security, IT service desk, people and workplace, travel and expenses) plus one archived superseded FAQ. Each part keeps its original `source_id` (listed in the `includes` front matter and on a `Source ID:` line) for citations.
- `documents/known-issues/` — one merged troubleshooting knowledge base covering six issues.
- `documents/security-training/` — an intentionally poisoned, non-authoritative document for an indirect prompt-injection exercise. Keep it isolated from production policy sources.

## Dataset scale

| Data | Count | Intended level |
|---|---:|---|
| Employees | 10 | L1 onward |
| Tickets | 20 | L1 onward |
| Leave balances | 10 | L1 onward |
| Leave history entries | 30 | L2 onward |
| Approval requests | 8 | L2 onward |
| Policy/handbook Markdown documents (4 long merged + travel + 1 archived FAQ) | 6 | L4 onward |
| Troubleshooting knowledge base (6 merged articles) | 1 | L4 onward |
| Poisoned training fixture | 1 | L5 security exercise only |

## Rebuild the SQLite file

From the repository root, run:

```bash
python mock-data/sqlite/build_database.py
```

This recreates `mock-data/sqlite/acme_helpdesk.sqlite3` from the checked-in SQL fixtures. To build elsewhere, pass `--output /path/to/file.sqlite3`.

Example queries:

```sql
SELECT ticket_id, status, priority FROM tickets WHERE ticket_id = 'INC-1042';
SELECT * FROM leave_balance_summary WHERE employee_id = 'E104';
SELECT * FROM leave_balance_summary WHERE total_remaining = 0;
```

## Scenario coverage

- `INC-1042` is Asha Raman's in-progress, high-priority VPN ticket.
- All five ticket statuses and all four priorities are represented.
- `INC-9999` is intentionally absent to exercise a not-found result.
- Asha is `E104`; her identity should come from the application/session, not user-supplied text.
- Priya Nair is `E107`; use her record only in an authorization-denial exercise, never to teach unrestricted HR lookups.
- Imani Okafor (`E109`) has zero annual, sick, and carry-forward leave remaining.
- The leave policy defines a five-day carry-forward maximum and includes expiry and notice rules.
- The travel policy and IT security policy deliberately do not answer whether personal devices may be used abroad, so the correct RAG behavior is to abstain.
- Approval fixtures cover pending, approved, rejected, and cancelled states. The records are examples, not evidence of real approvals.

## Data model notes

- Employee IDs, emails, and all records use reserved `.test` domains and fictional names.
- Timestamps are ISO 8601 UTC strings. Dates are fixed to make tests reproducible; they are not relative to the current date.
- `leave_balance_summary` computes the remaining balances. Enforce ownership authorization in application code; the view is not an authorization boundary.
- `leave_history` is a deliberately small sample of past requests, not a complete transaction ledger; balances are the current source of truth and need not equal the displayed sample totals.
- `approval_requests.payload_json` contains synthetic action drafts only. It intentionally includes no passwords, tokens, or other secrets.
- The SQL schema uses foreign keys, `CHECK` constraints, uniqueness, and indexes as teaching examples. It is not a production HR schema.
- Markdown `source_id`, version, and section headings can be used as citation metadata. The poisoned fixture is explicitly not an authoritative source and should only be ingested when intentionally demonstrating indirect prompt injection.
