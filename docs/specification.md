# **BARA Core Specification — Simplified System Blueprint (v1.0)**

## **1. Overview**

The **Bank Alert Reconciliation Agent (BARA)** is a backend service that automatically and on-demand:

* fetches bank alert emails,
* fetches transactions,
* matches both,
* tracks metrics,
* exposes results to users via Telex using natural language commands.

This document defines the **core user story**, **command set**, and **lean REST → Telex mapping** for the simplified, purpose-driven version of BARA.

It serves as the **primary guiding document** for development, ensuring the system stays focused, maintainable, and user-centered.

---

# **2. Core User Story**

**As a finance or operations user,**
I want BARA to automatically fetch my bank alert emails and transactions, match them continuously, and keep a running record of status and metrics,
so that reconciliation stays up-to-date without manual work.

When I need more control,
I want to trigger email fetching, transaction polling, or reconciliation on demand,
view all unmatched items, and manually resolve mismatches —
all through natural language commands in Telex.

BARA should allow me to start or stop automation at any time,
view the system’s health, and inspect logs or metrics whenever I return.

---

# **3. Functional Modes**

## **3.1 Automated Mode (Default)**

BARA should periodically and automatically:

* fetch new bank alert emails
* fetch new transactions
* run matching
* store results, metrics, and logs
* update status for user visibility

### **User expectations**

When they return, they should see:

* what matched
* what didn’t
* how the system is performing
* whether automation is running

### **User controls**

* Start automation
* Stop automation
* Check system status
* View logs

---

## **3.2 Manual/On-Demand Mode**

Users can override automation and manually:

* fetch emails
* fetch transactions
* run matching
* view unmatched items
* perform manual match pairing

### **User expectations**

* One command should run a full manual match
* Unmatched items should be easy to inspect
* Manual corrections should be supported

---

# **4. Simplified Command Set (12 Commands Total)**

These are the only commands BARA needs to support in v1.

## **4.1 Automation Commands**

1. **start_automation**
   Begin automatic cycle (fetch → poll → match).

2. **stop_automation**
   Halt automatic background processing.

3. **get_status**
   Show automation state and latest system health.

4. **show_logs**
   Display recent logs and events for debugging or audit.

---

## **4.2 Manual/On-Demand Commands**

5. **fetch_emails_now**
   Immediately pull new bank alert emails.

6. **fetch_transactions_now**
   Immediately pull new transactions.

7. **match_now**
   Match all currently unprocessed emails and transactions.

8. **list_unmatched**
   Show all unmatched emails *and* unmatched transactions.

9. **manual_match**
   Manually match a specific email to a specific transaction.

---

## **4.3 Insights Commands**

10. **show_summary**
    Overview of matched vs unmatched items.

11. **show_metrics**
    Detailed system metrics (accuracy, throughput, counts).

---

## **4.4 Utility**

12. **help**
    Show list of available commands with examples.

---

# **5. Lean REST → Telex Mapping**

The REST API only needs **11 endpoints** to power the 12 commands.

## **5.1 Automation Endpoints**

| REST                     | Purpose                            | Telex Command      |
| ------------------------ | ---------------------------------- | ------------------ |
| POST `/automation/start` | Start automated cycle              | `start_automation` |
| POST `/automation/stop`  | Stop automated cycle               | `stop_automation`  |
| GET `/automation/status` | Automation + overall system health | `get_status`       |
| GET `/logs/recent`       | Retrieve recent logs/events        | `show_logs`        |

---

## **5.2 Manual Operations**

| REST                       | Purpose                             | Telex Command            |
| -------------------------- | ----------------------------------- | ------------------------ |
| POST `/emails/fetch`       | Fetch unread alerts from IMAP       | `fetch_emails_now`       |
| POST `/transactions/fetch` | Fetch new transactions              | `fetch_transactions_now` |
| POST `/match/run`          | Run matching manually               | `match_now`              |
| GET `/items/unmatched`     | Get unmatched emails + transactions | `list_unmatched`         |
| POST `/match/manual`       | Manual email → transaction link     | `manual_match`           |

---

## **5.3 Insights**

| REST           | Purpose                           | Telex Command  |
| -------------- | --------------------------------- | -------------- |
| GET `/summary` | High-level reconciliation summary | `show_summary` |
| GET `/metrics` | Detailed system metrics           | `show_metrics` |

---

## **5.4 Utility**

| REST                   | Purpose         | Telex Command |
| ---------------------- | --------------- | ------------- |
| GET `/help` (optional) | Serve help text | `help`        |

---

# **6. Guiding Principles for Development**

1. **Automation is the default.**
   Users shouldn’t manage low-level services.

2. **Manual control is simple and direct.**
   One command = one clear action.

3. **Every essential operation is exposed through Telex.**
   No hidden features.

4. **Logs and status should always be queryable.**
   Users trust what they can inspect.

5. **The system should remain small, predictable, and maintainable.**

6. **Avoid exposing internal “poller/fetcher” components.**
   These should stay under the hood.

---

# **7. Final Summary**

This document defines the **lean, distilled version of BARA**:

* Clear user story
* Reduced command set
* Minimal REST surface
* Clean automation and manual workflows
* Natural language access through Telex
* No unnecessary complexity
