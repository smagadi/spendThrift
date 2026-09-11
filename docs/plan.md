# Implementation plan (MVP)

Source of truth: [`PRD.md`](./prd.md). This file is the build order only.

**Working agreement:** Plan and get approval before application code. Keep chats/token use small. Any behavior change updates `docs/prd.md`; phase/order changes update this file. Tests under `tests/`; run the full suite after code changes (no regressions). Cursor rules: `.cursor/rules/`.

**Architecture:** Streamlit never talks to DuckDB.

| Phase | What |
|---|---|
| 1 | DuckDB file and tables |
| 2 | Python function API (not HTTP): cards, ingest of **normalized/fixture** rows, categorizer, analytics, advisory, search, backup |
| 3 | Bank-specific statement parsers + real ingest (was 2b) |
| 4 | Thin Streamlit UI (calls Phase 2/3 via `backend.api` only) |

**Deferred (do not build):** billing-cycle / “this bill” view, cosine similarity, search CSV/Excel export.

---

## Phase 1 — DuckDB (schema only)

**Goal:** A persistent production file `data/spends.duckdb` with the normalized schema. No parsers, no Streamlit, no analytics, **no tests** (tests start in Phase 2 against `:memory:` / temp using the same `apply_schema`).

### Work

* Project layout: `backend/`, `docs/`, later `app.py` at repo root (repo name may stay `spendThrift`; PRD’s `spend_analyzer/` is the logical app, not a rename).
* `backend/database.py` (or `backend/schema.py` + connection helper):
  * Connect via `backend.database.connect`; default production path `data/spends.duckdb`
  * Create tables if missing:
    * `credit_cards`
    * `statement_uploads`
    * `credit_card_transactions`
    * `category_cache`
    * `custom_categories`
  * Unique constraint on cards: `(bank_name, last_4_digits, cardholder)`
  * `card_id` encodes bank + last 4 + cardholder
  * Foreign keys: transactions → cards and uploads
  * Timezone for timestamps: Asia/Kolkata
* Idempotent startup: running schema setup twice must not wipe data.
* Optional: seed **master category names** as a Python constant list (not required as a DB table). `custom_categories` is for user-added names only.

### Done when

* `python scripts/init_db.py` creates `data/spends.duckdb` (idempotent).
* Same schema via `connect(":memory:")` for Phase 2 tests — no second production DB.
* No tests in this phase. No UI. No bank files.

---

## Phase 2 — Python API (DB + business logic)

**Goal:** Domain logic the UI will need, callable as ordinary Python functions. No HTTP (FastAPI/Flask). No Streamlit. **No bank-specific parsers** (that is Phase 3). Ingest is tested with already-normalized rows or a tiny fixture CSV.

Suggested modules:

| Module | Responsibility |
|---|---|
| `backend/database.py` | Connection, schema (from Phase 1), raw SQL helpers |
| `backend/cards.py` | Create, list, soft-delete, reactivate |
| `backend/ingest.py` | Hash file, upload registry, reject / replace / insert (normalized rows) |
| `backend/categorizer.py` | Cache lookup, Unidentified, batch save, recategorize + apply to existing, custom categories |
| `backend/analytics.py` | Expense-only rollups (year, MoM, by card/user/category, top txns, merchants, recurring) |
| `backend/advisory.py` | Fixed-template strings from analytics |
| `backend/search.py` | Keyword + date range + amount filters → table |
| `backend/backup.py` | Copy `spends.duckdb` to a user path |
| `backend/api.py` | **Single facade** (`list_cards`, `ingest_normalized`, `dashboard_payload`, …) |

“API” = this facade + the modules behind it.

### Work

* Cards: unique on bank + last 4 + cardholder; `is_active` gates who may be passed to ingest.
* Ingest orchestration: reject same file hash; replace same filename + new hash; insert new. Fixture/normalized rows only.
* Categorizer: exact cleaned description; Unidentified vs Unknown vs Miscellaneous; batch save mappings; editable cache + apply to existing rows; custom category unique case-insensitive.
* Analytics: calendar year of **transaction date**; YTD = selected year total; expenses only; EMI as spend.
* Recurring: same merchant, amount may differ.
* Advisory: templates only.
* Search: in-app table data only (no file export).
* Backup: copy DB file to a given path.

### Done when

* `python -m pytest` covers cards, ingest reject/replace, categorizer, analytics (expenses + calendar year), search, backup.
* Re-uploading the same file bytes is rejected; same filename + new bytes replaces rows.
* Facade: `backend.api.SpendAPI`. No Streamlit. No HDFC/ICICI/Axis parsers yet.

---

## Phase 3 — Statement import (bank parsers)

**Goal:** Custom parsers for real bank files, wired into Phase 2 ingest. Gated on sample statements.

### Work

* User samples live under `bankstatements /` (gitignored). Phase 3: **ICICI CSV** (`backend/parsers/icici.py`) and **HDFC CSV** (`backend/parsers/hdfc.py`). Axis is a separate module later.
* ICICI CSV: use Date, Transaction Details, Amount(in Rs), BillingAmountSign. Do **not** read Customer Name, Address, Account number, Reward Point Header, Intl.Amount, There, Sr.No.
* HDFC CSV: `~|~` delimiter; one card per file via `Card No:` last 4; use DATE, Description, AMT, Debit /Credit. Skip Cr and card payment lines. Visa and UPI statements share the same layout.
* `BillingAmountSign` **CR** = credit (payments, fuel surcharge give-back, refunds) → `spend_type=Credit`, excluded from dashboard totals. Blank/DR = expense.
* ICICI: one card per statement file; consistent CSV layout. Discover masked-line last-4 from the file; match registered card. No hardcoded card numbers.
* `SpendAPI.ingest_icici_csv` / `SpendAPI.ingest_hdfc_csv` → parse → existing ingest (hash / reject / replace).

### Done when

* Real sample files for each bank ingest through the API into DuckDB.
* Same file-level reject/replace rules still hold.
* Still no Streamlit.

---

## Phase 4 — UI (Streamlit)

**Goal:** Thin `app.py` (plus optional `ui/` helpers that only call `backend.api`). Plotly for charts.

### Screens (sidebar)

1. **Dashboard** — global filters: year, user (All / cardholder), card (All / any card including soft-deleted). Unidentified count badge. Sections from PRD §6: metrics, MoM, top spends/merchants, category donut + by card/user, recurring table, advisory text.
2. **Card manager** — create; list; soft-delete; reactivate.
**Upload (current):** ICICI and HDFC CSV via `SpendAPI.ingest_icici_csv` / `ingest_hdfc_csv`. Axis parser is after this UI.
4. **Category review** — Unidentified table, dropdowns, one **Save mappings**; recategorize + apply to existing (can live here or under settings).
5. **Search / settings** — filters + results table; backup path.

### Done when

* A user can register cards, import statements, categorize, and use the dashboard and search without writing SQL.
* `app.py` contains no DuckDB SQL and no bank-specific parse logic.

---

## Suggested sequence (checklist)

| # | Phase | Item |
|---|---|---|
| 1 | 1 | Connection + create five tables + card unique constraint |
| 2 | 2 | Facade: cards CRUD / soft-delete / reactivate |
| 3 | 2 | Upload registry + ingest of normalized/fixture rows |
| 4 | 2 | Categorizer + custom categories |
| 5 | 2 | Analytics, recurring, advisory, search, backup |
| 6 | 3 | ICICI CSV parser + ingest |
| 7 | 3 | HDFC CSV parser + ingest (Visa + UPI) |
| 8 | 4 | Streamlit UI (this phase; Axis after UI) |

Phases 1–2 do not wait on bank samples. Phase 3 does.

---

## PRD recheck (notes while planning)

Aligned: local DuckDB only, thin Streamlit, file-level dedup, calendar transaction date, expenses-only dashboard, import CSV/Excel, no search export, no Elasticsearch.

Watch-outs (already in PRD; implement as specified):

* **Unidentified** = pending review on a row. Dropdown choices include **Unknown** and **Miscellaneous**. Do not mix these three.
* Soft-deleted cards: visible on dashboard/search; **not** in upload dropdown until reactivated.
* Parser work is Phase 3 and blocked until samples exist; schema and Phase 2 are not.
