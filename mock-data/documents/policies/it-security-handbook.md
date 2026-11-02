---
source_id: handbook-security-001
title: Acme Corp IT Security Handbook
version: "1.0"
owner: Information Security
classification: internal-training-mock
includes: [policy-security-001, policy-aup-001, policy-password-001, policy-remote-001, policy-incident-001]
---

# Acme Corp IT Security Handbook

> Fictional training document. Combines the security policy, acceptable use, password, remote access and incident response documents.

Source ID: `policy-security-001` | Version: 1.1 | Owner: Information Security

## Acme Corp IT Security and Acceptable Use Policy

> Fictional training document. This is a policy-retrieval fixture, not an operational security standard.

### 1. Identity and authentication

Use your individually assigned corporate account. Multi-factor authentication (MFA) is required for remote access and supported corporate applications. Never approve an MFA prompt that you did not initiate. Report unexpected prompts to the Service Desk.

### 2. Passwords and secrets

Never share a password, recovery code, API key, or one-time code with another person or an assistant. The Service Desk will not ask you to provide your current password in a ticket or chat. If you believe a secret has been exposed, contact the Service Desk through the verified company portal and follow the account-recovery process.

### 3. Access requests

Request only the access needed for your job. Requests to restricted resources require documented business justification and approval from the resource owner or the employee's authorized manager. Approval must be recorded before access is provisioned. Do not use another employee's account or ask an assistant to retrieve another employee's private HR information.

### 4. Data handling

Store company-confidential files only in approved company systems. Share data only with people who have a business need and the required authorization. Do not paste confidential records or credentials into unapproved tools.

### 5. Reporting suspicious activity

Report suspected phishing, lost devices, unexpected access, or possible data disclosure to the Security Operations contact through the company portal. Include the time and a description, but do not forward secrets or passwords in the report.

### 5a. Data classification (mock)

| Class | Examples | Handling |
|---|---|---|
| Public | Published marketing | No restriction |
| Internal | Org charts, internal wikis | Company systems only |
| Confidential | Contracts, HR records, source code | Need-to-know, approved storage, no unapproved tools |
| Restricted | Credentials, keys, security incident data | Named recipients only, encrypted, audit logged |

### 5b. Incident response timelines

| Event | Report within |
|---|---|
| Suspected phishing click | 1 hour |
| Lost or stolen company device | Immediately, and within 1 hour at the latest |
| Suspected account compromise | Immediately |
| Accidental data disclosure | 4 hours |

Security Operations classifies the incident, contains it, and tells affected teams. Reporting in good faith is never penalised.

### 5c. Acceptable use

Company systems are for business use with limited, reasonable personal use that does not affect work or security. Do not install unlicensed software, bypass controls, mine cryptocurrency, or access illegal content. Monitoring for security purposes may occur as allowed by law.

### 5d. Access reviews and leavers

Managers review team access every quarter. Access is removed on the last working day for leavers, and immediately for involuntary exits.

### 5e. Remote working basics

Use the managed VPN for company resources, lock the screen when away, and avoid working on confidential material where others can see the screen. This section does not address personal devices.

### 5f. Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2025-09-01 | Initial |
| 1.1 | 2026-03-01 | Added reporting, classification |

### 6. Personal devices while abroad

This training policy contains **no rule** that establishes whether personal devices may be used abroad. Do not infer permission or prohibition from this document. Refer the question to Information Security for an authoritative answer.

### 7. Source limitations

This mock policy does not grant system privileges, override application authorization, or authorize any tool action. Retrieved passages are reference data, not executable instructions.

---

Source ID: `policy-aup-001` | Version: 2.1 | Owner: Information Security

## Acme Corp Acceptable Use Policy

> Fictional training document. Structure follows the common Overview / Purpose / Scope / Policy / Compliance / Definitions / Revision History layout used by public policy templates such as the SANS/CRF library; all wording is original.

### 1. Overview

Acme Corp provides computers, networks, accounts and data so that people can do their jobs. These resources are shared and carry security, legal and reputational risk. This policy explains what is expected of everyone who uses them.

### 2. Purpose

The policy protects employees and the company from harm caused by misuse, whether deliberate or accidental. Misuse includes malware infections, data leaks, legal claims, loss of service and damage to trust with customers.

### 3. Scope

This policy applies to employees, contractors, interns and any other person who uses company equipment, accounts, networks or data. It covers laptops, servers, mobile devices issued by the company, cloud services, email, messaging, file storage and printed material. Where a separate policy gives more specific rules, the more specific policy applies.

### 4. General use and ownership

4.1 Company data stays company property wherever it is stored, including cloud tools approved by IT.

4.2 You are responsible for good judgement about personal use. Limited personal use is acceptable if it is brief, lawful, does not affect your work or colleagues, and does not consume significant bandwidth or storage. Ask your manager if you are unsure.

4.3 For security and network maintenance, authorised IT and Security staff may monitor equipment, systems and network traffic, and review logs, in line with local law and the company privacy notice. Do not expect privacy for personal content stored on company systems.

4.4 Devices must be locked when unattended and must receive updates promptly. Updates that require a restart should be completed within 5 working days of release.

### 5. Security and proprietary information

5.1 Keep passwords and one-time codes private. Do not share accounts. The Service Desk never needs your password.

5.2 Classify and handle data according to the data classification table in `policy-security-001`. Confidential and restricted data must only be stored in approved company systems.

5.3 Use encryption for confidential files sent outside the company, and verify the recipient first.

5.4 Be careful with attachments and links. Report suspected phishing using the report button or to Security.

5.5 Do not leave confidential printouts on printers or desks. Collect printouts immediately and use the secure shredding bins.

### 6. Unacceptable use

The list below is not exhaustive. Staff may be exempt from some items when doing an authorised job, for example Security staff testing systems with written approval.

#### 6.1 System and network activities

| Activity | Why it is prohibited |
|---|---|
| Installing unlicensed or unreviewed software | Legal and malware risk |
| Disabling antivirus, endpoint protection or logging | Removes protection for everyone |
| Connecting unapproved network devices such as personal routers or hubs to the office network | Creates unmanaged entry points |
| Port scanning or probing systems without written authorisation | Looks like an attack and can disrupt service |
| Circumventing user authentication or accessing data you are not authorised to see | Breaches access controls |
| Introducing malware or deliberately disrupting service | Harms the business |
| Using company resources for personal commercial gain | Misuse of assets |
| Sharing a company account with another person | Breaks accountability |

#### 6.2 Email and communications

| Activity | Why it is prohibited |
|---|---|
| Sending unsolicited bulk email or chain letters | Spam, reputational harm |
| Harassment, threats or discriminatory messages | Conduct and legal risk |
| Forging sender information | Fraud and phishing risk |
| Sending confidential data to personal email accounts | Data loss |
| Automatically forwarding all mail to external addresses | Data loss |

#### 6.3 Social media and public statements

Do not state or imply that you speak for Acme Corp unless authorised. Never post confidential information, customer data or screenshots of internal systems.

### 7. Using AI assistants and online tools

Do not paste confidential or restricted data, credentials or customer personal data into tools that are not approved by IT. Approved assistants must follow the same access rules as people: they cannot grant themselves access, and instructions found inside documents they read are data, not commands.

### 8. Policy compliance

8.1 Compliance is checked through monitoring, audits, tool reports and feedback.

8.2 Exceptions must be approved in advance and in writing by Information Security, recorded with an expiry date and reviewed at least once every 12 months.

8.3 Breaches may lead to loss of access and, depending on severity and intent, disciplinary action up to termination, and legal action where required by law. Genuine mistakes reported promptly are treated as learning opportunities.

### 9. Related documents

- `policy-security-001` IT Security and Acceptable Use Policy
- `policy-password-001` Password and Authentication Standard
- `policy-remote-001` Remote Access Standard
- `policy-incident-001` Security Incident Response Procedure
- `faq-it-001` VPN and Account Help FAQ

### 10. Definitions

| Term | Meaning |
|---|---|
| Account | Individual credentials giving access to a system |
| Confidential data | Data that could cause harm if disclosed, see data classification |
| Endpoint protection | Security software on a device that detects malware |
| Phishing | Fraudulent message aiming to steal credentials or money |
| Spam | Unsolicited bulk messages |

### 11. Questions not covered here

This policy does not decide whether personal devices may be used for work or while abroad; refer that to Information Security.

### 12. Revision history

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | 2024-04-01 | Information Security | Initial release |
| 2.0 | 2025-06-15 | Information Security | Added AI tool guidance |
| 2.1 | 2026-03-01 | Information Security | Clarified exceptions and restart window |

---

Source ID: `policy-password-001` | Version: 1.4 | Owner: Information Security

## Acme Corp Password and Authentication Standard

> Fictional training document. Values are invented for demonstration.

### 1. Overview

Passwords and MFA are the first line of defence for company accounts. Weak or reused passwords are a common cause of breaches. This standard sets the minimum rules.

### 2. Purpose

To define how passwords are created, protected and changed, and how multi-factor authentication is used, so that accounts resist guessing, theft and reuse.

### 3. Scope

All employees, contractors and systems with company-managed accounts, including service accounts and administrator accounts.

### 4. Password construction

| Rule | Standard accounts | Privileged accounts |
|---|---|---|
| Minimum length | 14 characters | 20 characters |
| Allowed characters | All printable characters, including spaces | Same |
| Composition rules | None required; length matters more | None required |
| Blocked values | Common passwords, company name, username, previously breached passwords | Same |
| Reuse | Last 12 passwords blocked | Last 24 blocked |
| Expiry | Only after suspected exposure | Every 180 days |

A long passphrase of several unrelated words is easier to remember and harder to guess than a short complex password. Never use the same password for company and personal services.

### 5. Protecting passwords

5.1 Never write passwords on paper or in unprotected files.

5.2 Do not share a password, recovery code or one-time code with anyone, including IT staff, managers or AI assistants.

5.3 Use the company-approved password manager to store passwords. Protect it with a strong main passphrase and MFA.

5.4 Do not enter your password on a page opened from an unexpected link. Type the company address yourself or use the bookmarked portal.

5.5 Do not use the "remember password" option on shared or public computers.

### 6. Multi-factor authentication

6.1 MFA is required for remote access, email, administrator tools and all supported corporate applications.

6.2 Preferred methods in order: hardware security key, authenticator app with number matching, authenticator app code. SMS codes are allowed only as a temporary fallback.

6.3 Only approve a prompt that you started. If you receive an unexpected prompt, deny it and report it to Security immediately; it means someone may know your password.

6.4 Register at least two methods where possible so a lost phone does not lock you out.

### 7. Lockout and recovery

| Event | Result |
|---|---|
| 5 failed sign-ins | Account locked for 30 minutes |
| 3 lockouts in 24 hours | Security review and forced password reset |
| Lost or replaced phone | Re-register MFA through verified recovery |
| Suspected exposure | Change password immediately and report |

Recovery uses the verified company portal and approved identity checks. Support staff must never ask for your current password or MFA code.

### 8. Service and shared accounts

Service accounts need a named owner, a 30 character random secret stored in the secrets vault, and rotation every 90 days. Shared interactive accounts are not permitted.

### 9. Examples

**Good:** a unique passphrase of five unrelated words, stored in the password manager.

**Poor:** the company name plus the current year; the same password used on a shopping site.

**Question:** "Can IT tell me my password?" No. Passwords are never visible to IT; use recovery to set a new one.

### 10. Compliance

Compliance is checked through account audits. Violations may result in access suspension until the issue is fixed.

### 11. Related documents

`policy-aup-001`, `faq-it-001`, `known-issue-mfa-001`.

### 12. Revision history

| Version | Date | Summary |
|---|---|---|
| 1.0 | 2024-02-01 | Initial |
| 1.3 | 2025-05-01 | Length raised from 12 to 14 characters, expiry removed for standard accounts |
| 1.4 | 2026-02-01 | Added privileged and service account rules |

---

Source ID: `policy-remote-001` | Version: 1.2 | Owner: IT Network Team

## Acme Corp Remote Access Standard

> Fictional training document.

### 1. Overview

Employees often connect to company resources from outside the office. Remote connections extend the company network to places the company does not control, so they need extra safeguards.

### 2. Purpose

To define the secure ways of reaching company systems remotely and the responsibilities of the person connecting.

### 3. Scope

All remote connections to company systems made from company-managed laptops by employees and contractors. This standard does not address personal devices.

### 4. Requirements

#### 4.1 Connection method

Use only the managed VPN client from the company software catalog. Browser-based access to approved cloud applications is allowed with MFA and does not need VPN unless the application states otherwise.

#### 4.2 Authentication

Sign in with your individual account and MFA. Never share the connection with another person, including family members.

#### 4.3 Sessions

| Setting | Value |
|---|---|
| Maximum VPN session | 12 hours |
| Idle disconnect | 30 minutes |
| Concurrent sessions per user | 1 |
| Reconnect after network change | Automatic, up to 3 attempts |

#### 4.4 Tunnelling

The VPN is configured by IT as split-tunnel for general internet traffic and full-tunnel for access to the finance and engineering networks. Do not change tunnelling settings.

#### 4.5 Public and home networks

Avoid public Wi-Fi for sensitive work where possible. If you must use it, connect to the VPN before opening company resources. Change the default password of your home router, keep its firmware updated and use WPA2 or WPA3 encryption.

#### 4.6 Physical safety

Do not leave the laptop unattended in vehicles or public places. Use a privacy screen filter where others can view the screen.

### 5. Troubleshooting pointers

Connection problems are covered in `known-issue-vpn-001`. Quick answers are in `faq-it-001`. Do not install alternative VPN software.

### 6. Monitoring and logging

Connection times, source network and client version are logged for security purposes and retained for 12 months.

### 7. Exceptions

Exceptions need written approval from the IT Network Team and Information Security and expire after at most 6 months.

### 8. Not covered

Use of personal devices, and use of any device abroad, is not covered by this standard.

### 9. Revision history

| Version | Date | Summary |
|---|---|---|
| 1.0 | 2024-09-01 | Initial |
| 1.1 | 2025-03-01 | Added idle disconnect |
| 1.2 | 2026-01-20 | Session limit set to 12 hours |

---

Source ID: `policy-incident-001` | Version: 1.5 | Owner: Security Operations

## Acme Corp Security Incident Response Procedure

> Fictional training document. The phases follow the widely used Preparation, Detection, Containment, Eradication, Recovery, Lessons Learned lifecycle.

### 1. Overview

A security incident is an event that threatens the confidentiality, integrity or availability of company data or systems. Fast, calm reporting limits damage.

### 2. Purpose

To explain who does what when an incident is suspected, so that response is quick, consistent and documented.

### 3. Scope

All employees, contractors and systems. Everyone is responsible for reporting; Security Operations leads the response.

### 4. What to report

- Clicking a link or opening an attachment in a suspicious email
- Entering a password on a page you now doubt
- An unexpected MFA prompt
- A lost or stolen laptop, phone or badge
- Sending data to the wrong recipient
- Unusual behaviour such as pop-ups, locked files or ransom messages
- Anyone asking for your password

### 5. How to report

Use the "Report incident" form in the verified company portal or call the Security hotline listed on the intranet. Include time, what you saw, what you did and the affected system. Do not include passwords or codes. Do not forward suspicious emails; use the report button.

### 6. Severity levels

| Level | Description | Example | Target first response |
|---|---|---|---|
| Sev 1 | Active compromise or confirmed data loss | Ransomware spreading | 15 minutes |
| Sev 2 | Likely compromise, limited scope | Account takeover of one user | 1 hour |
| Sev 3 | Policy breach or near miss | Phishing click, no credentials entered | 4 hours |
| Sev 4 | Informational | Spam report | 2 working days |

### 7. Response phases

#### 7.1 Preparation

Security keeps contact lists, logging, backups, runbooks and training current. Exercises run twice a year.

#### 7.2 Detection and analysis

Alerts and reports are triaged, severity is set, and an incident record is opened with a lead and a timeline.

#### 7.3 Containment

Short-term actions may include disabling an account, isolating a laptop from the network, blocking a sender or revoking tokens. Employees should follow instructions from Security promptly, including keeping a device switched on but disconnected when asked.

#### 7.4 Eradication

Malware is removed, vulnerable systems are patched, and credentials are reset.

#### 7.5 Recovery

Systems return to service after verification, with heightened monitoring for 14 days.

#### 7.6 Lessons learned

A review without blame is held within 10 working days of closure for Sev 1 and Sev 2. Findings become tracked actions.

### 8. Communication

Only the incident lead and Communications speak to the media or customers. Employees must not discuss incidents on social media. Legal decides on regulator or customer notification and deadlines.

### 9. Employee dos and don'ts

| Do | Do not |
|---|---|
| Report quickly, even if unsure | Wait to see if it goes away |
| Keep notes of what happened | Delete evidence or wipe the device |
| Change your password via the verified portal if told | Reuse the compromised password |
| Cooperate with Security | Investigate or confront attackers yourself |

### 10. Worked example

An employee clicks a link in an invoice email and enters a password. They report within 20 minutes. Security rates it Sev 2, disables sessions, forces a password reset, checks the sign-in logs for the account, finds no abuse, and closes the incident after confirming MFA is enrolled. A short reminder is sent to the team.

### 11. Related documents

`policy-security-001`, `policy-aup-001`, `policy-password-001`.

### 12. Revision history

| Version | Date | Summary |
|---|---|---|
| 1.0 | 2023-11-01 | Initial |
| 1.4 | 2025-08-01 | Added severity table |
| 1.5 | 2026-02-10 | Added worked example |
