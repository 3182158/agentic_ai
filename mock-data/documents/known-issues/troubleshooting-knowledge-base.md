---
source_id: kb-troubleshooting-001
title: Acme Corp IT Troubleshooting Knowledge Base
version: "1.0"
owner: IT Service Desk
classification: internal-training-mock
includes: [known-issue-vpn-001, known-issue-wifi-001, known-issue-mfa-001, known-issue-email-001, known-issue-hardware-001, known-issue-printer-001]
---

# Acme Corp IT Troubleshooting Knowledge Base

> Fictional training document. Combines known-issue articles for VPN, Wi-Fi, MFA, email, laptop and printer problems.

Source ID: `known-issue-vpn-001` | Version: 1.0 | Owner: 

## VPN Connectivity Troubleshooting

### Symptoms

The managed VPN client disconnects, stalls during connection, or reports that the gateway cannot be reached.

### Safe first checks

- Verify ordinary internet access without changing firewall or endpoint-security settings.
- Check that the managed VPN client is current in the company software catalog.
- Reconnect once through the normal company sign-in flow.
- Note the time, network type, client version, and exact non-secret error text.

### Summary

Most VPN failures come from the local network, an outdated client, an expired sign-in session, or a gateway under load. Work through the checks below in order; each step rules out one cause and takes about two minutes.

### Common causes

| Cause | Typical sign | Who fixes it |
|---|---|---|
| Home router or hotel captive portal | Client stalls at "Connecting" | Employee |
| Outdated VPN client | Error VPN-301 after an update announcement | Employee via software catalog |
| Expired sign-in session | Prompt loops back to the sign-in page | Employee |
| Time drift on the device | Certificate or token rejected | Employee |
| Gateway maintenance or overload | Many colleagues fail at the same time | IT Network team |
| Account locked after failed attempts | "Account disabled" message | Service Desk |

### Step-by-step resolution

1. Open a public website. If it fails, fix the internet connection first (see the Wi-Fi article, `known-issue-wifi-001`).
2. If you are on a hotel or café network, open a browser and accept the network's terms page; VPN cannot connect until that page is completed.
3. Confirm the device clock is set automatically. A drift of more than five minutes breaks token validation.
4. Open the company software catalog and install any pending update for the managed VPN client. Restart the client afterwards.
5. Disconnect, wait 10 seconds, reconnect once through the normal company sign-in flow. Repeated rapid retries can lock the account.
6. Switch networks (for example, from Wi-Fi to a phone hotspot) to tell a local network fault from a company-side fault.
7. If the hotspot works but the original network does not, the original network blocks VPN traffic; tell the network owner, not the Service Desk.

### Error messages

| Message | Meaning | Action |
|---|---|---|
| VPN-301 Client version not supported | Client is too old | Update via software catalog |
| VPN-402 Gateway unreachable | Network blocks the connection or the gateway is down | Try another network, then check the status page |
| VPN-515 Authentication timed out | Sign-in or MFA was not completed in time | Retry once and finish MFA promptly |
| VPN-610 Account disabled | Too many failed attempts or security hold | Contact the Service Desk through the verified portal |

### What not to do

Do not disable endpoint protection, install an unofficial VPN client, edit firewall rules, or share a screenshot that shows a one-time code.

### Related documents

- `faq-it-001` VPN and Account Help FAQ
- `known-issue-mfa-001` Repeated MFA prompts
- `policy-security-001` IT Security and Acceptable Use Policy

### Escalate when

The issue repeats, blocks a critical task, or affects several employees. Create an IT ticket with the diagnostic facts above. Never include a password, MFA code, or recovery token.

---

Source ID: `known-issue-wifi-001` | Version: 1.0 | Owner: 

## Office Wi-Fi Connectivity Troubleshooting

### Symptoms

A managed laptop sees the Acme-Staff network but cannot authenticate, or connects without reaching internal services.

### Safe first checks

- Confirm the selected network is the company-managed Acme-Staff network.
- Toggle Wi-Fi off and on once, then reconnect using the normal company sign-in flow.
- Check whether other managed services are reachable and note the office location and time.
- Do not bypass certificate warnings or join look-alike networks.

### Summary

Office Wi-Fi problems are usually one of four things: a device-side setting, a stale saved network profile, weak signal in a specific zone, or an access-point outage. Identify which one before raising a ticket.

### Networks available in the office

| Network | Purpose | Who may join |
|---|---|---|
| Acme-Corp | Managed laptops, certificate based | Company devices only |
| Acme-Guest | Visitors, internet only, 24 hour access code | Visitors |
| Acme-Devices | Printers and meeting-room equipment | IT managed, no manual joining |

### Step-by-step resolution

1. Toggle Wi-Fi off and on, or enable and disable airplane mode.
2. Confirm you chose the right network. Company laptops use Acme-Corp, not Acme-Guest.
3. Choose "Forget this network", then rejoin and sign in with your normal company account.
4. Check that the device date and time are correct; certificate sign-in fails otherwise.
5. Restart the device. Pending updates sometimes reset the wireless adapter.
6. Move closer to an access point. Known weak areas are stairwells and the far end of the east meeting rooms.
7. Test another device on the same network. If it also fails, the problem is the network, not your laptop.

### Symptom guide

| Symptom | Likely cause | Next step |
|---|---|---|
| Connected, "No internet" | DHCP or upstream issue | Reconnect; report if several people are affected |
| Repeated password prompt | Stale saved profile | Forget and rejoin |
| Very slow in one room | Weak signal or congestion | Move; report the room and time |
| Drops every few minutes | Roaming between access points | Update the wireless driver via the software catalog |

### Guest access

Visitors must request an access code from reception. Employees should not share the Acme-Corp sign-in details with visitors.

### Related documents

- `known-issue-vpn-001` VPN Connectivity Troubleshooting
- `faq-it-001` VPN and Account Help FAQ

### Escalate when

Authentication still fails after a reconnect, or multiple people are affected. Open a Network ticket and include device type, office location, and non-sensitive error text.

---

Source ID: `known-issue-mfa-001` | Version: 1.0 | Owner: 

## Repeated MFA Prompts

### Symptoms

The sign-in flow repeatedly asks for MFA or does not retain a completed sign-in.

### Safe first checks

- Verify the device's date and time are correct.
- Use the registered authenticator and complete the sign-in in one browser session.
- Approve only prompts that you initiated for a sign-in you recognize.
- Never share a one-time code or approve an unexpected prompt.

### Summary

Repeated MFA prompts are most often caused by a wrong device clock, multiple browser sessions competing, or a notification arriving late. Unexpected prompts you did not start are a different case: treat them as a possible attack.

### Two situations, two responses

| Situation | What it means | What to do |
|---|---|---|
| You just tried to sign in and prompts repeat | Usually a technical fault | Follow the steps below |
| A prompt appears when you did not sign in | Someone may have your password | Deny it, change your password via the verified portal, and contact Security |

### Step-by-step resolution

1. Confirm the phone and the computer both have automatic date and time enabled.
2. Close extra browser windows and private sessions. Sign in once in a single window.
3. Open the registered authenticator app and approve the newest prompt only; older prompts expire.
4. If you use number matching, enter the number shown on the sign-in screen, not one from an earlier attempt.
5. Check that the phone has a data connection; push approvals need it.
6. If the app shows no prompts, use the code option inside the registered authenticator.
7. Wait two minutes before retrying. Rapid repeats can trigger a temporary throttle.

### Lost or replaced phone

Do not try to bypass MFA. Request re-registration through the verified company portal. Identity is checked using approved recovery steps, and the Service Desk never asks for your password or a code.

### Common mistakes

- Approving every prompt "to make it stop". Never approve a prompt you did not initiate.
- Using two authenticator entries for one account.
- Reading a code aloud or pasting it into a ticket or chat.

### Related documents

- `policy-security-001` section 1, Identity and authentication
- `faq-it-001` section 3, Repeated MFA prompts

### Escalate when

The loop continues after a fresh sign-in or an unexpected prompt appears. Report the application and time through the verified Service Desk or Security channel.

---

Source ID: `known-issue-email-001` | Version: 1.0 | Owner: 

## Email and Shared Mailbox Access

### Symptoms

A shared mailbox is missing, messages do not sync, or expected attachments are delayed.

### Safe first checks

- Confirm the correct corporate account and mail profile are open.
- Refresh the mail client once and check the approved web client for the same mailbox.
- Ask the mailbox owner to confirm that access was approved and provisioned.
- Do not forward confidential attachments to a personal account to work around the issue.

### Summary

Email problems fall into three groups: sign-in or sync faults, shared mailbox visibility, and send/delivery failures. Shared mailboxes take up to 60 minutes to appear after access is granted.

### Shared mailbox access

1. Confirm access was approved. Access requires documented business justification and approval from the mailbox owner (see `policy-security-001`).
2. Wait up to 60 minutes after approval. Restart the mail client afterwards.
3. In the web client, open the shared mailbox directly; if it works there but not in the desktop app, the desktop profile needs a refresh.
4. Remove and re-add the mailbox only if the owner confirms permissions are correct.
5. Sending "as" or "on behalf of" the mailbox needs separate permission from read access.

### Delivery and sync problems

| Symptom | Likely cause | Action |
|---|---|---|
| Mail stuck in Outbox | Attachment too large (limit 25 MB) | Share a link instead |
| Bounce: mailbox full | Recipient or your mailbox over quota | Archive old mail |
| Mail missing on phone only | Sync profile stale | Remove and re-add the account |
| Calendar invites not arriving | Rule or junk filter | Check rules and junk folder |
| Message flagged as external | Sender outside the company | Do not click links you did not expect |

### Suspicious messages

If an email asks for a password, a code, or urgent payment, do not reply. Report it through the "Report phishing" button or contact Security.

### Related documents

- `policy-security-001` sections 2 and 3

### Escalate when

The mailbox remains unavailable or an attachment is unexpectedly quarantined. Raise an Email ticket and include the mailbox name, approximate time, and non-sensitive message details. A quarantine concern may need Security review.

---

Source ID: `known-issue-hardware-001` | Version: 1.0 | Owner: 

## Laptop Hardware First Checks

### Symptoms

A managed laptop has a battery, camera, keyboard, or display problem that affects work.

### Safe first checks

- Record the device asset label if visible, the symptom, and when it began.
- For a camera issue, check the operating system's normal privacy-permission settings and the meeting application's selected camera.
- For a power issue, use the supplied company charger and stop using equipment that is unusually hot, swollen, or damaged.
- Do not open the device or install unofficial drivers.

### Summary

Laptop faults are triaged by whether the device powers on, whether the fault is software or hardware, and whether data is at risk. Always protect data first: do not attempt repairs that could lose unsaved or unsynced work.

### Fault guide

| Symptom | First checks | Likely outcome |
|---|---|---|
| Will not power on | Try a different outlet and charger; hold power 15 seconds | Battery or charger swap |
| Battery drains fast | Check battery health report; close heavy apps | Battery replacement if health below 70% |
| Overheating, loud fan | Clear vents; use a hard surface | Cleaning or fan repair |
| Cracked screen | Stop using it if glass is loose | Hardware replacement |
| Keyboard keys unresponsive | Restart; test an external keyboard | Keyboard replacement |
| Very slow | Check pending updates and storage space | Cleanup or reimage |
| Blue or black screen on boot | Note the stop code | Ticket with the code |

### Step-by-step

1. Save work and sync files to the company storage if the device still runs.
2. Restart once. Install pending updates from the software catalog.
3. Free disk space: keep at least 15% free.
4. Disconnect docks, USB devices, and external monitors, then retest.
5. Record the model, asset tag (on the underside label), and exact message.

### Replacement and loan devices

Hardware replacement is decided by IT after diagnosis. A loan laptop can be issued for a business-critical outage; it is returned once the repair is complete. Lost or stolen devices must be reported to Security immediately through the verified portal.

### Related documents

- `policy-security-001` for lost-device reporting

### Escalate when

The issue persists, there are signs of physical damage, or the device may be unsafe. Create a Hardware ticket and arrange support through the approved asset process.

---

Source ID: `known-issue-printer-001` | Version: 1.0 | Owner: 

## Printer Produces Blank Pages

### Symptoms

A shared office printer feeds paper but prints blank pages or very faint output.

### Safe first checks

- Check the device display for a toner or supply warning.
- Confirm the correct printer and document page range are selected.
- Print a single test page from an approved application.
- Do not open equipment panels beyond the normal user-accessible supply compartment.

### Summary

Blank pages usually mean a driver or print-queue problem, a document that did not render, or a consumable that is empty. Hardware faults are less common.

### Step-by-step resolution

1. Print a different document, such as a short text file. If it prints, the original file is the problem; re-export it to PDF and print again.
2. Cancel all jobs in the print queue, then resubmit one job.
3. Confirm the right printer is selected. Floor printers have names like PRN-3F-02; a similarly named printer on another floor may be chosen by mistake.
4. Check the display on the printer for toner, drum, or paper messages.
5. Remove and re-add the printer from the company software catalog so the managed driver is reinstalled.
6. Try printing from another device. If that also gives blank pages, report a printer fault.

### Symptom guide

| Symptom | Likely cause | Action |
|---|---|---|
| Fully blank page | Toner empty or protective tape left on a new cartridge | Check toner; report to facilities |
| Header only, body blank | Document rendering issue | Print to PDF first |
| Blank only from one laptop | Driver problem | Reinstall the managed driver |
| Faint or striped pages | Drum wear | Report with printer name |

### Supplies and ownership

Toner is replaced by facilities. Employees should not open the printer or buy cartridges. Report the printer name, floor, and message shown on the display.

### Related documents

- `known-issue-wifi-001` for printers that appear offline

### Escalate when

A test page is blank or the device shows a hardware error. Raise a Hardware ticket with the printer location and any displayed error code.
