# Product Requirements Document (PRD)
## Multi-Bank & Multi-User Credit Card Spend Analyzer & Advisor (MVP)

---

## 1. Project Overview & Objective

A local-first, privacy-focused Python application designed to ingest, normalize, and analyze **credit card transactions** across multiple issuers (**HDFC, ICICI, and Axis**) and **specific physical cards** for **multiple family members/cardholders**.

Single shared DuckDB on one machine. No login or multi-tenant auth in MVP.

**Core architectural rule:** Business logic, parsing, caching, database operations, analytics, and advisory calculations must reside strictly in backend Python modules. Streamlit (`app.py`) is a thin presentation layer only.

**MVP scope:** card registry (create / soft-delete / reactivate), statement **import**/parse (HDFC / ICICI / Axis `.csv` / `.xlsx` / `.xls`), file-level ingest guardrails, categorization cache and Unidentified review, full dashboard (metrics, MoM charts, donut, top spends/merchants, category by card/user), recurring merchant audit, advisory (fixed templates), advanced search (in-app results table only), DuckDB backup to a user-chosen path.

**Deferred:** billing-cycle / “this bill” view, cosine similarity matching, **CSV/Excel export of search results**.

---

## 2. Tech Stack & Directory Structure

* **Language:** Python 3.10+
* **UI & Web Server:** Streamlit (thin presentation shell), run locally (`streamlit run app.py`)
* **Data Processing & Ingestion:** Pandas, Regex (`re`); statement files are **CSV and Excel** (`.csv`, `.xlsx`, `.xls`)
* **Database & Analytics Engine:** DuckDB. Production file: `data/spends.duckdb` (override with env `SPENDS_DB_PATH` or `connect(path)`). Tests reuse the same schema on `:memory:` or a temp file — not a second long-lived database.
* **Visualizations:** Plotly (interactive charts with tooltips and zoom)

**Database choice:** DuckDB is the system of record and analytics engine. Do **not** add Elasticsearch or a second long-lived database. Production file is `data/spends.duckdb`. Tests use the same schema in memory or a temp file. Description search uses SQL (`ILIKE` / optional DuckDB FTS later). Backup copies the production DuckDB file.

### Target File Structure

```text
spend_analyzer/
│
├── docs/
│   └── PRD.md
│
├── scripts/
│   └── init_db.py             # Create/migrate production DuckDB
├── data/
│   └── spends.duckdb          # Local persistent database (gitignored)
├── backend/
│   ├── database.py            # DuckDB connection, schema, cache, upload registry
│   ├── parser_cards.py        # Excel/CSV parser & normalizer for HDFC, ICICI, Axis CC
│   ├── categorizer.py         # Master + custom categories, cache lookup, recategorize
│   ├── analytics.py           # SQL aggregations (monthly, quarterly, yearly rollups)
│   └── advisory.py            # Top merchant drains, category breakdowns, fixed-template advice
│
├── app.py                     # Thin Streamlit UI
└── requirements.txt
```

---

## 3. Card Management Workflow (`database.py` & `app.py`)

**Landing dashboard:** Users open the application to the main financial analytics dashboard.

**Card registry:** A dedicated UI lists all registered cards from `credit_cards` (active and soft-deleted).

**Card creation:** Register a physical card with:

* Bank name (HDFC, ICICI, Axis)
* Card name / nickname (e.g. Regalia, Amazon Pay)
* Last 4 digits (e.g. 1234)
* Cardholder name (user owner)

**Uniqueness:** A card is unique on **bank + last 4 digits + cardholder**. Two people may hold the same product nickname; last-4 alone is not unique. `card_id` must encode this uniqueness (not only bank + nickname + last 4).

**Initial state:** `is_active = TRUE`.

**Soft deletion:** `is_active = FALSE`. The card **remains in history, filters, and dashboard analytics**. It is **removed from the statement-upload dropdown**. To load new statements for that card, the user must reactivate it first, then upload.

**Reactivation:** Restore `is_active = TRUE` from the card manager.

---

## 4. Statement Ingestion & File-Level Replace (`parser_cards.py` & `database.py`)

**Target selection:** Upload dropdown lists only cards where `is_active = TRUE`.

**File upload:** User drops a monthly HDFC, ICICI, or Axis statement. **Accepted formats: `.csv`, `.xlsx`, and `.xls`.** PDF is out of MVP.

**ICICI CSV:** Skip card payments (`INFINITY PAYMENT RECEIVED`, any `PAYMENT RECEIVED`) and all `BillingAmountSign=CR` rows — do not ingest. Auto-tag ICICI merchant refunds when the description contains ` REFUND` (no `BillingAmountSign=CR`). **Refund** category (and `spend_type=Refund`) is excluded from dashboard spend.

**HDFC CSV:** Tilde-delimited (`~|~`). One card per file; match registered last 4 to `Card No:` line (Visa and UPI cards share layout). Use `DATE`, `Description`, `AMT`, `Debit /Credit`. Skip `Cr` rows and `CREDIT CARD PAYMENT` lines — do not ingest. UPI spends keep the `UPI-` merchant prefix in description.

### Parsing & normalization

* Map raw headers (transaction date, description, amount / debit-credit flags) to the master schema.
* **`date` = transaction date** (not posting date when both exist; posting date is fallback only).
* Standardize dates to `YYYY-MM-DD`. Interpret timestamps in **Asia/Kolkata**.
* Clean merchant descriptions with regex (whitespace/case and obvious statement noise). Cache key for MVP is the **exact cleaned description**.
* **Analytics rollups** (top merchant drains, recurring merchants, advisory merchant line) group by **`normalize_merchant(description)`** at query time — trailing cities/`IN`, short noise tokens; **`UPI-` prefix is kept** (cross-card UPI merge later). Raw `description` on each row is unchanged; category cache stays exact-match.
* Currency is **INR**. No FX conversion in MVP.
* **Expenses/debits** are stored as a unified **positive** amount.
* **EMI** is treated as spend.
* **Rewards / points / cashback-as-points:** ignore (do not ingest as spend).
* **Payments, refunds, and credits:** not ingested for ICICI CR/payment lines; **Refund** category never counts as spend. Dashboard filters expenses only.

### Time bucketing (locked)

Banks typically **send the statement in the following calendar month**. That is delivery lag, not spend month.

* All trends, year filter, and “YTD” use the **calendar month/year of transaction date**.
* **YTD in the UI** means **total spend for the selected calendar year** (not year-to-today vs “now”).
* **Statement / billing cycle** (e.g. 15th–14th, “this bill”, amount due) is **out of MVP**. Do not bucket charts by statement-sent month or upload month.
* If a file header includes a statement period, it may be stored on the **upload** record for audit only.

### Anti-duplication: file-level, not row-hash (locked)

The goal is to stop **re-uploading the same statement**, not to collapse two legitimate same-day same-merchant spends (e.g. two Swiggy orders of ₹349).

Do **not** use `card_id + date + description + amount` as the primary duplicate key. That both misses renamed copies of the same file and falsely drops real repeated spends.

**Approach:**

1. Table `statement_uploads` records each ingest: `upload_id`, `card_id`, `original_filename`, **`file_fingerprint` (hash of file bytes)**, `uploaded_at`, `row_count`, `status`. Optional: statement period from the file header.
2. Each transaction row stores **`upload_id`** and **`source_filename`** (filename is for the user; hash is the identity of the document).
3. On upload for a card:
   * **Same file hash already ingested** → reject: this document was already loaded (show prior upload date).
   * **Same filename, different hash** (corrected re-download) → **delete existing rows for that card + filename / prior upload**, then reload (replace).
   * **New file** → insert all expense rows, including identical merchant/date/amount lines.

Row-level unique hashes are not the MVP guardrail.

---

## 5. Core Functional Modules & Workflows

### Module 1: Categorization & cache (`categorizer.py`)

**Seed master categories:**

* Groceries & Supermarket
* Dining Out & Food Delivery
* Utilities & Bills
* Fuel & Transportation
* Shopping & E-Commerce
* Healthcare & Pharmacy
* Rent & Housing
* Investments & Insurance
* Entertainment & Subscriptions
* Travel & Hotels
* Miscellaneous
* Unknown

Unmatched new rows are tagged **Unidentified** (pending review), not Miscellaneous.

**Cache lookup (MVP):** exact match on **cleaned description** → `category_cache`. No cosine similarity in v1; similarity matching is a later evolution.

**Review UX:** table of Unidentified rows; per-row dropdown (master list + persisted custom categories + Unknown + Miscellaneous); **one “Save mappings” button** (batch), not save-per-row.

**Custom categories:** user-entered names **persist** and must be **unique** (treat as unique ignoring case: `Food` and `food` are the same).

**Recategorize (MVP):** cache is **editable**. Changing a mapping applies to **future** uploads. Offer **apply to existing rows** with the same cleaned description.

### Module 2: Analytics & visualizations (`analytics.py` & `app.py`)

DuckDB SQL rollups for expenses only:

* Time-series: monthly and quarterly totals (calendar periods of `date`)
* Cross-compare: category, card name, cardholder

Plotly: interactive bar/line MoM, donut for category mix, grouped bars for multi-user / multi-card.

### Module 3: Advisory (`advisory.py`)

* Top spending categories and top 5 merchant drains per card/user.
* **Fixed text templates** (e.g. “X is your top drain this year”). No custom threshold engine in MVP.

### Recurring payments audit

Recurring means **same merchant appearing repeatedly**, **not** same amount. Amount may drift (subscriptions, utilities). Table: merchant, **total spent** (selected year, normalized merchant), txn count, month count, amount range, last charged date, category; sorted by **total spent** descending.

---

## 6. UI Layout (`app.py`)

Thin presentation layer.

**Global filters:** Year (calendar year of transaction date) | User (All / cardholder) | Card (All / specific, including soft-deleted cards for viewing history).

**Alert:** count of Unidentified rows pending review.

**Sidebar:** Dashboard, Card Manager, Statement Upload (ICICI CSV in this build), Category Review, Advanced Search / Settings.

**Section 1 — Portfolio summary:** YTD (selected year total), top spending card, top spending category; yearly spend by card; yearly spend by user.

**Section 2 — MoM trends:** by card/user; household aggregate burn.

**Section 3 — Top spends:** largest individual transactions; aggregated merchant drains.

**Section 4 — Category breakdown:** donut; by card; by user.

**Section 5 — Recurring merchants audit.**

**Section 6 — Search & maintenance:** keyword on description, date range, amount slider, **in-app** results table. No CSV/Excel download of search results in MVP (later). Backup button copies `data/spends.duckdb` to a **user-chosen path**.

---

## 7. Database Schema (DuckDB)

### Table 1: `credit_cards` (dimension)

| Column | Type | Notes |
|---|---|---|
| `card_id` | VARCHAR PK | Encodes **bank + last 4 + cardholder** uniqueness |
| `bank_name` | VARCHAR | HDFC, ICICI, Axis |
| `card_name` | VARCHAR | Nickname, e.g. Regalia |
| `last_4_digits` | VARCHAR | e.g. `1234` |
| `cardholder` | VARCHAR | Owner |
| `is_active` | BOOLEAN DEFAULT TRUE | Soft delete: false = no new uploads; history still visible |

Unique constraint: `(bank_name, last_4_digits, cardholder)`.

### Table 2: `statement_uploads` (ingest registry)

| Column | Type | Notes |
|---|---|---|
| `upload_id` | VARCHAR PK | |
| `card_id` | VARCHAR FK | |
| `original_filename` | VARCHAR | Display / replace key with card |
| `file_fingerprint` | VARCHAR | Hash of file bytes; same hash = same document |
| `uploaded_at` | TIMESTAMP | Asia/Kolkata |
| `row_count` | INTEGER | Expense rows ingested |
| `status` | VARCHAR | e.g. loaded, rejected_duplicate, replaced |
| `statement_period` | VARCHAR | Optional; audit only, not used for chart months |

### Table 3: `credit_card_transactions` (fact)

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR PK | Per ingested row (not a date+description+amount hash) |
| `card_id` | VARCHAR FK | |
| `upload_id` | VARCHAR FK | Links to `statement_uploads` |
| `source_filename` | VARCHAR | Original file name |
| `date` | DATE | Transaction date; calendar bucketing |
| `description` | VARCHAR | Cleaned description (cache key) |
| `amount` | DOUBLE | Positive expense amount |
| `category` | VARCHAR | Default `Unidentified` |
| `spend_type` | VARCHAR | Default `One-Time`; expenses vs non-expense if stored |

### Table 4: `category_cache`

| Column | Type | Notes |
|---|---|---|
| `merchant_pattern` | VARCHAR PK | Exact cleaned description (MVP) |
| `assigned_category` | VARCHAR | Editable; apply-forward and apply-to-existing |

### Table 5: `custom_categories` (optional but required for uniqueness)

| Column | Type | Notes |
|---|---|---|
| `category_name` | VARCHAR PK | Unique ignoring case |
| `created_at` | TIMESTAMP | |

---

## 8. Locked product decisions (summary)

| Topic | Decision |
|---|---|
| Scope | Full list in §1; deferred: cycle/bill view, cosine matching, search CSV/Excel export |
| Auth | None; one local DuckDB |
| Database | DuckDB only; no Elasticsearch |
| Currency | INR |
| EMI | Spend |
| Rewards/points | Ignore |
| Dashboard totals | Expenses only |
| Dedup | File fingerprint + replace-on-same-filename-different-hash |
| Merchant cache | Exact cleaned description; cosine later |
| Merchant analytics | Query-time `normalize_merchant()` grouping; raw description preserved |
| Categories | Unknown + Miscellaneous + Unidentified (pending); custom names unique (case-insensitive) |
| Review | Batch Save mappings |
| Recategorize | Editable cache; future + apply to existing rows |
| Soft-deleted cards | Visible in history; cannot upload until undeleted |
| Card uniqueness | Bank + last 4 + cardholder |
| Time | Transaction date, calendar month/year, Asia/Kolkata |
| YTD | Selected calendar year total |
| Statement cycle | Out of MVP |
| Recurring | Same merchant, amount may differ |
| Advisory | Fixed templates |
| Search export | Out of MVP (later). Statement **import** of CSV/Excel stays |
| Backup | User-chosen path (copy of `data/spends.duckdb`) |
| Statement file types | `.csv`, `.xlsx`, `.xls` (PDF out of MVP) |
| Runtime | Local Streamlit |

---

## 9. Open / follow-ups (do not block MVP build)

* Bank-specific parser mappings depend on **real sample statements** in the repo (not yet present at last review).
* Custom category uniqueness: **case-insensitive** (assumed above).
* If a bank file has only posting date, use posting date as `date`.
* **Later:** download filtered search results as CSV/Excel (not required for analysis inside the app).
