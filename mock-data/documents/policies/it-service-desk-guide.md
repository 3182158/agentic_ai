---
source_id: handbook-servicedesk-001
title: Acme Corp IT Service Desk Guide
version: "1.0"
owner: IT Service Desk
classification: internal-training-mock
includes: [faq-it-001, policy-software-001, policy-onboarding-001]
---

# Acme Corp IT Service Desk Guide

> Fictional training document. Combines the VPN and account FAQ, software and access requests, and new joiner onboarding.

Source ID: `faq-it-001` | Version: 1.0 | Owner: IT Service Desk

## Acme Corp VPN and Account Help FAQ

> Fictional troubleshooting content for the workshop. Follow approved IT procedures in a real environment.

### 1. VPN disconnects or will not connect

1. Confirm the device has a working internet connection before starting the VPN.
2. Check that the managed VPN client is up to date using the company software catalog.
3. Disconnect once, wait 10 seconds, and reconnect using the normal company sign-in flow.
4. If the problem continues, record the approximate time, operating system, network type, and any non-sensitive error text, then raise a Service Desk ticket.

Do not disable endpoint protection, install an unapproved VPN client, or send passwords or one-time codes to support staff.

### 2. Password reset

Use the verified company account-recovery portal. The support team may verify identity using approved recovery checks, but it must never request your current password or MFA code. Do not put a password in a ticket description or chat.

### 3. Repeated MFA prompts

Confirm that the device date and time are correct, use the registered authenticator, and complete the company sign-in flow in one browser session. If prompts continue, report the time and application to the Service Desk; do not approve prompts you did not initiate.

### 4. What to include in a ticket

Include the affected service, a concise description, the time the issue began, steps already tried, and business impact. Exclude passwords, access tokens, recovery codes, and unrelated personal information.

### 6. Account lockout

Accounts lock after five failed sign-in attempts and unlock automatically after 30 minutes, or sooner through the verified recovery portal. Do not keep retrying; each attempt resets the timer.

### 7. Password rules (mock)

| Rule | Value |
|---|---|
| Minimum length | 14 characters |
| Reuse | Last 12 passwords blocked |
| Expiry | Only after a suspected exposure |
| Sharing | Never |
| Password manager | Company-approved manager recommended |

### 8. VPN quick answers

- *Which client do I use?* The managed client from the company software catalog.
- *Can I use a different VPN?* No; unapproved clients are not allowed.
- *How long does a VPN session last?* Sessions end after 12 hours; sign in again.
- *VPN works but a site does not.* The site may be restricted by role; raise an access request.

### 9. Software and access requests

Request software through the catalog. If it is not listed, raise a ticket with the business reason and the manager name. Approval takes up to 3 working days.

### 10. Service Desk hours and priorities (mock)

| Priority | Example | First response |
|---|---|---|
| P1 | Many users cannot work | 30 minutes |
| P2 | One team blocked | 2 hours |
| P3 | Single user, workaround exists | 1 working day |
| P4 | Question or request | 3 working days |

Hours are 07:00 to 19:00 on working days; P1 has out-of-hours cover.

### 11. Questions not covered here

This FAQ does not decide whether personal devices may be used for work, nor covers HR, travel, or leave matters; ask the owning team.

### 12. Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-04-15 | First release |

### 13. Related documents

`known-issue-vpn-001`, `known-issue-mfa-001`, `policy-security-001`.

### 14. Escalation

If a suspected security incident or account compromise is involved, contact Security through the verified company portal instead of repeatedly retrying sign-in.

---

Source ID: `policy-software-001` | Version: 1.3 | Owner: IT Service Desk

## Acme Corp Software and Access Request Procedure

> Fictional training document.

### Summary

Software comes from the company catalog. Access to restricted systems needs a documented business reason and approval before provisioning.

### 1. Catalog software

Pre-approved applications install without a ticket. Examples: the managed VPN client, office suite, authenticator, and approved browsers.

### 2. Non-catalog software

| Step | Owner |
|---|---|
| Submit ticket with product, version, business reason | Employee |
| Manager approval | Manager |
| Security and licence review (up to 5 working days) | Security |
| Install or rejection with reason | IT |

Unlicensed or unreviewed software must not be installed.

### 3. Access to systems

| Access type | Approver | Target turnaround |
|---|---|---|
| Standard team folders | Manager | 1 working day |
| Shared mailbox | Mailbox owner | 1 working day plus up to 60 minutes sync |
| Finance systems | Finance Operations | 3 working days |
| Production or restricted data | Resource owner and Security | 5 working days |

### 4. Temporary access

Temporary access expires automatically, by default after 30 days, and can be extended once with new approval.

### 5. Removing access

Managers request removal when roles change. Quarterly reviews remove unused access.

### 6. Not covered

Personal devices and device use abroad are not addressed here.

---

Source ID: `policy-onboarding-001` | Version: 1.0 | Owner: IT Service Desk

## Acme Corp New Joiner IT Onboarding Guide

> Fictional training document.

### Summary

This guide lists what a new employee receives on day one, what to set up in the first week, and where to get help.

### 1. Before day one

IT prepares a laptop, a corporate account, and a mailbox once People Operations confirms the start date at least 5 working days ahead. Late confirmations delay equipment.

### 2. Day one checklist

| Step | Detail |
|---|---|
| Collect laptop | From the Service Desk or delivered to home for remote joiners |
| First sign-in | Use the temporary credentials in the sealed welcome pack; change on first use |
| Register MFA | Install the registered authenticator and enrol |
| Install VPN | From the company software catalog |
| Join Wi-Fi | Acme-Corp in the office |

### 3. First week

Complete the mandatory security awareness course within 10 working days. Request role-specific access through the access request process, with manager approval. Shared mailboxes need owner approval and take up to 60 minutes to appear.

### 4. Equipment

Standard kit is a laptop, charger, and headset. Monitors and docks are issued on request. Report faults through the Service Desk.

### 5. Getting help

Use the Service Desk portal. Typical first response times: P3 within 1 working day. Never share your password, even with IT.

### 6. Not covered

This guide does not state leave balances, expense limits, or whether personal devices may be used abroad.
