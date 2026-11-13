# Card Fraud Analyst Console

**Owner:** Janet Cho · **Last reviewed:** November 2026 · **License:** [Apache 2.0](LICENSE)

An interactive Streamlit console for card-fraud operations on Snowflake:

1. **Live transaction feed:** replay a day of payments, each scored as it arrives
2. **Alert queue:** payments at or above the threshold, highest risk first, filterable by pattern
3. **Case review:** the exact signals behind the score, the card's recent locations and payments, a Cortex `AI_COMPLETE` briefing, and block / confirm / clear actions
4. **Threshold tuning:** fraud dollars caught vs. good payments declined vs. alerts per day, at every threshold
5. **Patterns and merchants:** a common-point-of-purchase check and a Cortex `AI_AGG` summary of analyst notes

There are also **governance** (role-based masking and an audit trail) and **about** pages.

- **Landing page:** https://sfc-gh-jacho.github.io/sfguide-card-fraud-console/
- **Try it in your browser (no account):** https://sfc-gh-jacho.github.io/sfguide-card-fraud-console/try/

## Two modes, one codebase

| | Sample data mode | Live Snowflake mode |
|---|---|---|
| Where | Your browser (stlite), or `streamlit run` on a laptop | Streamlit in Snowflake, in your account |
| Data | Generated in the app, deterministic | Same data, loaded into `FRAUD_DEMO_DB.CARDS` |
| Scoring | Python (`fraud/logic.py`) | The `TXN_SCORED` SQL view, identical scores |
| AI | **Captured** output from a real Cortex run, labeled; template text elsewhere, labeled | Live `AI_COMPLETE` and `AI_AGG` |
| Governance | The view-as switcher simulates each role | Masking policies on the tables |
| Case actions | Kept in the browser session | Written to `CASE_ACTIONS` |

The app uses live mode automatically when it can reach the `FRAUD_DEMO_DB.CARDS` tables. A sidebar switch goes back to sample data.

## Try it locally (no account)

```bash
git clone https://github.com/sfc-gh-jacho/sfguide-card-fraud-console.git
cd sfguide-card-fraud-console
python3 -m venv .venv && source .venv/bin/activate
pip install "streamlit==1.65.0"
FRAUD_SAMPLE_ONLY=1 streamlit run streamlit_app.py
```

`FRAUD_SAMPLE_ONLY=1` stops the app from trying to connect to Snowflake.

## The scoring signals

Each payment's score (0–100) is the sum of these named signals, so every alert can be explained exactly.

| Signal | Points |
|---|---|
| Amount 10x or more above the card's typical spend | 25 |
| Amount 5x to 10x above typical | 15 |
| Amount 3x to 5x above typical | 8 |
| Resellable goods (electronics or gift cards) | 10 |
| Online payment from a device the customer hasn't used | 20 |
| Between midnight and 5 a.m. | 8 |
| In person, more than 500 km from home | 12 |
| Impossible travel: in person, faster than 900 km/h from the previous in-person payment | 35 |
| Card testing: 3+ charges under $2 on the card in the last 30 minutes | 30 |
| Velocity: 4+ payments on the card in the last hour | 10 |

The default alert threshold is 40. The SQL view uses `RANGE BETWEEN INTERVAL ... PRECEDING` windows, `HAVERSINE` and `LAG`. On all 54,064 synthetic payments it produces exactly the same score and signals as the Python version.

## Run it live in your Snowflake account

### Prerequisites

- **Enterprise Edition or higher**, for masking policies
- **Cortex AI functions** in your region: `AI_COMPLETE` with `llama3.3-70b`, and `AI_AGG`. If the model isn't available, enable cross-region inference or change `MODEL` in `fraud/ai.py`.
- **A compute pool** for Streamlit's container runtime (`SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT`)
- **An external access integration for PyPI**, because `pyproject.toml` pins Streamlit 1.65.0 to match the browser version
- **Snowflake CLI 3.14 or later**
- **Tested with:** Snowflake CLI 3.31, Streamlit 1.65.0, stlite 1.12.2, and the `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11` runtime on an AWS Enterprise Edition account

### Steps

1. **Run the setup script.** Run Steps 1–4 of [`sql/fraud_setup.sql`](sql/fraud_setup.sql) in a Snowsight worksheet. This creates:
   - `FRAUD_DEMO_DB.CARDS`
   - The `FRAUD_WH` warehouse (XSMALL, 60-second auto-suspend)
   - Empty tables
   - The `TXN_SCORED` view
   - Masking policies
   - Three audience roles
2. **Set your account names.** In `snowflake.yml`, set `compute_pool` and `external_access_integrations` for your account.
3. **Deploy the app** with `snow streamlit deploy fraud_console --replace`.
4. **Load the data.** Open the app, go to **About this example**, and select **Load synthetic data**.
5. **Check the results (optional).** Run Step 5 to see today's alert queue in SQL and each role's masked view.
6. **Clean up** when you're done: uncomment and run Step 6. Dropping `FRAUD_DEMO_DB` also removes the Streamlit app.

### Least-privilege option (no ACCOUNTADMIN)

The script starts with `SET demo_role = 'ACCOUNTADMIN';`. To avoid ACCOUNTADMIN, an administrator runs the commented block at the top of Step 1 once. That block creates `FRAUD_DEMO_ROLE` with:
- `CREATE DATABASE`, `CREATE WAREHOUSE` and `CREATE ROLE`
- `SNOWFLAKE.CORTEX_USER`
- Usage on your compute pool and PyPI integration
- A grant to SYSADMIN

Then set `demo_role = 'FRAUD_DEMO_ROLE'`. The live path was tested as ACCOUNTADMIN. The least-privilege grants follow the documented requirements but weren't run end to end for this app.

## What gets created

| Object | Name |
|---|---|
| Database and schema | `FRAUD_DEMO_DB.CARDS` |
| Warehouse | `FRAUD_WH` (XSMALL, 60-second auto-suspend) |
| Tables | `TRANSACTIONS` (54,064), `CARDS` (2,688), `CARDHOLDERS` (2,400), `MERCHANTS` (256), `CARD_PROFILES`, `METROS`, `FRAUD_LABELS`, `ANALYST_NOTES`, `CASE_ACTIONS` |
| View | `TXN_SCORED` |
| Policies | `fraud_mask_name`, `fraud_mask_email`, `fraud_mask_last4` |
| Roles | `FRAUD_ANALYST`, `FRAUD_CS_AGENT`, `FRAUD_AUDITOR` |
| Streamlit app | `CARD_FRAUD_CONSOLE` |

## Cost and time

- **Time:** about 10 minutes to click through in your browser, and about 20 minutes to set up live mode.
- **Compute:** on an XSMALL warehouse, setup and the data load take well under a minute, and scoring all 54,064 payments in the view takes under a second. Each Cortex call takes a few seconds and a few thousand tokens; capturing the sample-mode AI output took 10 explanations and 1 summary. The Streamlit container uses its compute pool while the app is open.
- **Validation:** tested November 13, 2026 on an Enterprise Edition account (AWS):
  - The setup script ran, and the data loaded from the app.
  - SQL and Python scores matched on all 54,064 payments.
  - Masking was verified for the analyst and auditor roles.
  - Live `AI_COMPLETE` and `AI_AGG` calls succeeded.
  - The app deployed to Streamlit in Snowflake, and `SHOW STREAMLITS` confirmed it.
  - All 8 pages ran headlessly with no exceptions.
  - The browser build loaded in about 20 seconds, and the replay advanced as expected.

## Known limitations

- **The fraud labels are synthetic.** Background fraud and the planted stories are generated with ground-truth labels so the tuning page can show trade-offs. Catch rates and decline counts describe this data set only and aren't performance claims.
- **This is a rule-based score, not a trained model.** It's chosen because it's transparent and runs in the browser. To use Snowflake ML, train a model on your labeled history, register it, and call it from the scoring view.
- **The replay is a replay.** The feed advances through one stored day. A production pipeline would use Snowpipe Streaming or a Dynamic Table.
- **Role switching is simulated in the app.** Streamlit in Snowflake runs with the owner's rights. The masking policies themselves were verified in SQL with each role (Step 5).
- **AI output varies.** The captured explanations come from one run at temperature 0, and live runs may word things differently.
- **The browser version uses a CDN, and its first load is slow.** stlite and Pyodide load from jsDelivr, and the first load takes about 20 seconds while Python starts and the data is generated.
- **The map uses coded metros** at approximate positions, not real merchant locations.

## Customize with Cortex Code

[Cortex Code](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code) can adapt this console to your environment. Open the repo folder in Cortex Code and try prompts like:

- "Explain this console's data model and scoring view, then map it to my authorization, card and merchant tables without changing any objects."
- "Train a gradient-boosted fraud model with Snowflake ML on my labeled history, register it, and add its score next to the rule score in TXN_SCORED. Show me precision and recall at thresholds 30, 40 and 50 before I switch."
- "Turn TXN_SCORED into a Dynamic Table fed by Snowpipe Streaming, and propose least-privilege grants for the fraud analyst role first."

Ask it to review the plan with you before it creates or changes any objects in your account.

## Repository layout

```
LICENSE                       Apache License 2.0
index.html, styles.css,       GitHub Pages landing page (no third-party requests)
  script.js
try/index.html                In-browser version (stlite)
docs/images/                  Screenshots of the running app
streamlit_app.py              App entry point and navigation
app_pages/                    One file per screen
fraud/data.py                 Deterministic synthetic data generator
fraud/logic.py                Explainable scoring, patterns and threshold trade-offs
fraud/source.py               Sample vs live data, Snowflake reads and writes
fraud/ai.py                   Cortex AI_COMPLETE and AI_AGG, captured fallbacks
fraud/ui.py                   Shared UI and view-as masking rules
data/captured_ai.json         AI output captured from a real live run
sql/fraud_setup.sql           Live-mode setup, scoring view, checks and cleanup
snowflake.yml                 Streamlit in Snowflake manifest
pyproject.toml                Pinned dependencies for live mode
.streamlit/config.toml        Snowflake theme
static/                       Inter and JetBrains Mono fonts (SIL Open Font License)
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE). The bundled Inter and JetBrains Mono fonts are under the SIL Open Font License.

## Disclaimer

This is an illustrative example provided as-is. It is not an official Snowflake product, it is not supported by Snowflake Support, and it is not a production fraud system or regulatory advice.

Everything in it is synthetic:

- **Data:** cardholders, cards, merchants, payments and fraud labels are all generated.
- **Locations:** cities are coded metros.
- **Contact details:** emails use the reserved `@example.com` domain.
- **Card numbers:** they are never stored. Cards carry only a last-4, and the app displays them on the 400000 test BIN.

Signals and weights are simplified for demonstration. The repository contains no credentials, account identifiers or connection details. Review and test before any production use.
