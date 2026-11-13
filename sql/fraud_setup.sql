/*
================================================================================
 CARD FRAUD ANALYST CONSOLE - LIVE SNOWFLAKE MODE SETUP
 Creates everything the Streamlit app needs in live mode:
 - FRAUD_DEMO_DB.CARDS with empty tables (the app loads synthetic data into them)
 - TXN_SCORED: an explainable fraud score for every payment, in SQL
   (time-window functions, HAVERSINE distance, LAG for impossible travel)
 - Masking policies on cardholder and card fields
 - Roles for the three audiences in the governance screen

 This script creates its own objects and changes nothing that already exists.
 The cleanup block at the end removes everything.

 ALL DATA IS SYNTHETIC. Card numbers are never stored: cards carry only a
 last-4, and the app displays them on the 400000 test BIN.
================================================================================
*/

-- [step:setup]
-- ============================================================================
-- STEP 1: SETUP
-- ============================================================================

-- Choose the role that runs the guide:
--   'ACCOUNTADMIN'    - simplest, for sandbox accounts
--   'FRAUD_DEMO_ROLE' - least privilege; create it once with the block below
SET demo_role = 'ACCOUNTADMIN';

-- OPTIONAL: least-privilege role. An administrator runs this ONCE, then set
-- demo_role = 'FRAUD_DEMO_ROLE' above.
-- USE ROLE ACCOUNTADMIN;
-- CREATE ROLE IF NOT EXISTS FRAUD_DEMO_ROLE COMMENT = 'Runs the card fraud analyst console';
-- GRANT CREATE DATABASE  ON ACCOUNT TO ROLE FRAUD_DEMO_ROLE;          -- demo database
-- GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE FRAUD_DEMO_ROLE;          -- XSMALL demo warehouse
-- GRANT CREATE ROLE      ON ACCOUNT TO ROLE FRAUD_DEMO_ROLE;          -- the three audience roles
-- GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE FRAUD_DEMO_ROLE;  -- AI_COMPLETE and AI_AGG
-- GRANT USAGE ON COMPUTE POOL <YOUR_COMPUTE_POOL> TO ROLE FRAUD_DEMO_ROLE;          -- Streamlit container runtime
-- GRANT USAGE ON INTEGRATION <YOUR_PYPI_INTEGRATION> TO ROLE FRAUD_DEMO_ROLE;       -- installs pinned packages
-- GRANT ROLE FRAUD_DEMO_ROLE TO ROLE SYSADMIN;                        -- admins keep control of what it creates
-- SET my_user = CURRENT_USER();
-- GRANT ROLE FRAUD_DEMO_ROLE TO USER IDENTIFIER($my_user);

USE ROLE IDENTIFIER($demo_role);

CREATE WAREHOUSE IF NOT EXISTS FRAUD_WH
    WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE FRAUD_WH;

CREATE OR REPLACE DATABASE FRAUD_DEMO_DB;
CREATE SCHEMA IF NOT EXISTS FRAUD_DEMO_DB.CARDS;
USE SCHEMA FRAUD_DEMO_DB.CARDS;

-- [step:tables]
-- ============================================================================
-- STEP 2: TABLES (empty; the app's About page loads the synthetic data)
-- ============================================================================

CREATE OR REPLACE TABLE METROS (METRO VARCHAR, LAT FLOAT, LON FLOAT);
CREATE OR REPLACE TABLE CARDHOLDERS (
    CARDHOLDER_ID VARCHAR, FIRST_NAME VARCHAR, LAST_NAME VARCHAR, HOME_METRO VARCHAR, SEGMENT VARCHAR, EMAIL VARCHAR);
CREATE OR REPLACE TABLE CARDS (CARD_ID VARCHAR, CARDHOLDER_ID VARCHAR, LAST4 VARCHAR, PRODUCT VARCHAR, STATUS VARCHAR);
CREATE OR REPLACE TABLE MERCHANTS (MERCHANT_ID VARCHAR, CATEGORY VARCHAR, METRO VARCHAR, MERCHANT_NAME VARCHAR, CHANNEL VARCHAR);
CREATE OR REPLACE TABLE CARD_PROFILES (
    CARD_ID VARCHAR, HOME_METRO VARCHAR, HOME_LAT FLOAT, HOME_LON FLOAT, USUAL_DEVICE VARCHAR, TYPICAL_AMOUNT NUMBER(12, 2));
CREATE OR REPLACE TABLE TRANSACTIONS (
    TXN_ID VARCHAR, TS TIMESTAMP_NTZ, CARD_ID VARCHAR, MERCHANT_ID VARCHAR, CATEGORY VARCHAR, AMOUNT NUMBER(12, 2),
    CHANNEL VARCHAR, DEVICE_ID VARCHAR, MERCHANT_METRO VARCHAR, LAT FLOAT, LON FLOAT);
-- Synthetic ground truth, used only by the threshold-tuning screen
CREATE OR REPLACE TABLE FRAUD_LABELS (TXN_ID VARCHAR, IS_FRAUD BOOLEAN);
CREATE OR REPLACE TABLE ANALYST_NOTES (TXN_ID VARCHAR, NOTE_TS TIMESTAMP_NTZ, OUTCOME VARCHAR, NOTE VARCHAR);
CREATE OR REPLACE TABLE CASE_ACTIONS (EVENT_TS TIMESTAMP_NTZ, TXN_ID VARCHAR, CARD_ID VARCHAR, ACTOR VARCHAR, ACTION VARCHAR, NOTE VARCHAR);

-- [step:scoring]
-- ============================================================================
-- STEP 3: EXPLAINABLE FRAUD SCORE IN SQL
-- ============================================================================
-- Every point comes from a named signal. The app's Python scoring (fraud/logic.py)
-- implements exactly the same rules for sample-data mode.

CREATE OR REPLACE VIEW TXN_SCORED AS
WITH base AS (
    SELECT t.*, p.HOME_METRO, p.HOME_LAT, p.HOME_LON, p.USUAL_DEVICE, p.TYPICAL_AMOUNT,
           t.AMOUNT / p.TYPICAL_AMOUNT AS RATIO
    FROM TRANSACTIONS t
    LEFT JOIN CARD_PROFILES p USING (CARD_ID)
),
windows AS (
    SELECT b.*,
        -- card testing: small probes on this card in the last 30 minutes
        COUNT_IF(AMOUNT < 2) OVER (PARTITION BY CARD_ID ORDER BY TS
                                   RANGE BETWEEN INTERVAL '30 MINUTES' PRECEDING AND CURRENT ROW) AS SMALL_30M,
        -- velocity: payments on this card in the last hour
        COUNT(*) OVER (PARTITION BY CARD_ID ORDER BY TS
                       RANGE BETWEEN INTERVAL '60 MINUTES' PRECEDING AND CURRENT ROW) AS TXNS_60M
    FROM base b
),
travel AS (
    -- impossible travel: compare each in-person payment with the previous one on the card
    SELECT TXN_ID,
           HAVERSINE(LAG(LAT) OVER (PARTITION BY CARD_ID ORDER BY TS, TXN_ID),
                     LAG(LON) OVER (PARTITION BY CARD_ID ORDER BY TS, TXN_ID), LAT, LON) AS KM_FROM_PREV,
           DATEDIFF('second', LAG(TS) OVER (PARTITION BY CARD_ID ORDER BY TS, TXN_ID), TS) / 3600 AS HOURS_FROM_PREV
    FROM base
    WHERE CHANNEL = 'CARD_PRESENT'
),
signals AS (
    SELECT w.*,
        ROUND(RATIO, 1)                                                     AS AMOUNT_RATIO,
        IFF(CHANNEL = 'CARD_PRESENT', HAVERSINE(HOME_LAT, HOME_LON, LAT, LON), NULL) AS KM_FROM_HOME,
        IFF(tr.HOURS_FROM_PREV > 0, tr.KM_FROM_PREV / GREATEST(tr.HOURS_FROM_PREV, 1 / 60), NULL) AS IMPLIED_KMH,
        RATIO >= 10                                                         AS SIG_AMOUNT_10X,
        RATIO >= 5 AND RATIO < 10                                           AS SIG_AMOUNT_5X,
        RATIO >= 3 AND RATIO < 5                                            AS SIG_AMOUNT_3X,
        CATEGORY IN ('ELECTRONICS', 'GIFT_CARDS')                           AS SIG_RISKY_MCC,
        CHANNEL = 'ONLINE' AND COALESCE(DEVICE_ID, '') <> COALESCE(USUAL_DEVICE, '') AS SIG_NEW_DEVICE,
        HOUR(TS) < 5                                                        AS SIG_NIGHT,
        CHANNEL = 'CARD_PRESENT' AND HAVERSINE(HOME_LAT, HOME_LON, LAT, LON) > 500 AS SIG_FAR_FROM_HOME,
        COALESCE(IFF(tr.HOURS_FROM_PREV > 0, tr.KM_FROM_PREV / GREATEST(tr.HOURS_FROM_PREV, 1 / 60), NULL) > 900
                 AND tr.KM_FROM_PREV > 500, FALSE)                          AS SIG_IMPOSSIBLE_TRAVEL,
        SMALL_30M >= 3                                                      AS SIG_CARD_TESTING,
        TXNS_60M >= 4                                                       AS SIG_VELOCITY
    FROM windows w
    LEFT JOIN travel tr USING (TXN_ID)
)
SELECT * EXCLUDE (RATIO),
    LEAST(100,
          IFF(SIG_AMOUNT_10X, 25, 0) + IFF(SIG_AMOUNT_5X, 15, 0) + IFF(SIG_AMOUNT_3X, 8, 0)
        + IFF(SIG_RISKY_MCC, 10, 0) + IFF(SIG_NEW_DEVICE, 20, 0) + IFF(SIG_NIGHT, 8, 0)
        + IFF(SIG_FAR_FROM_HOME, 12, 0) + IFF(SIG_IMPOSSIBLE_TRAVEL, 35, 0)
        + IFF(SIG_CARD_TESTING, 30, 0) + IFF(SIG_VELOCITY, 10, 0))      AS RISK_SCORE
FROM signals;

-- [step:roles]
-- ============================================================================
-- STEP 4: ROLES AND MASKING POLICIES
-- ============================================================================

CREATE ROLE IF NOT EXISTS FRAUD_ANALYST;
CREATE ROLE IF NOT EXISTS FRAUD_CS_AGENT;      -- customer service
CREATE ROLE IF NOT EXISTS FRAUD_AUDITOR;
GRANT ROLE FRAUD_ANALYST  TO ROLE IDENTIFIER($demo_role);
GRANT ROLE FRAUD_CS_AGENT TO ROLE IDENTIFIER($demo_role);
GRANT ROLE FRAUD_AUDITOR  TO ROLE IDENTIFIER($demo_role);

-- The owning role (and the app, which runs with the owner's rights) sees full values
CREATE OR REPLACE MASKING POLICY fraud_mask_name AS (val STRING) RETURNS STRING ->
    CASE WHEN CURRENT_ROLE() = 'FRAUD_AUDITOR' THEN LEFT(val, 1) || '.' ELSE val END;

CREATE OR REPLACE MASKING POLICY fraud_mask_email AS (val STRING) RETURNS STRING ->
    CASE WHEN CURRENT_ROLE() = 'FRAUD_AUDITOR' THEN '****@' || SPLIT_PART(val, '@', 2) ELSE val END;

CREATE OR REPLACE MASKING POLICY fraud_mask_last4 AS (val STRING) RETURNS STRING ->
    CASE WHEN CURRENT_ROLE() = 'FRAUD_AUDITOR' THEN '****' ELSE val END;

ALTER TABLE CARDHOLDERS MODIFY COLUMN FIRST_NAME SET MASKING POLICY fraud_mask_name;
ALTER TABLE CARDHOLDERS MODIFY COLUMN LAST_NAME  SET MASKING POLICY fraud_mask_name;
ALTER TABLE CARDHOLDERS MODIFY COLUMN EMAIL      SET MASKING POLICY fraud_mask_email;
ALTER TABLE CARDS       MODIFY COLUMN LAST4      SET MASKING POLICY fraud_mask_last4;

GRANT USAGE ON WAREHOUSE FRAUD_WH TO ROLE FRAUD_ANALYST;
GRANT USAGE ON WAREHOUSE FRAUD_WH TO ROLE FRAUD_CS_AGENT;
GRANT USAGE ON WAREHOUSE FRAUD_WH TO ROLE FRAUD_AUDITOR;
GRANT USAGE ON DATABASE FRAUD_DEMO_DB TO ROLE FRAUD_ANALYST;
GRANT USAGE ON DATABASE FRAUD_DEMO_DB TO ROLE FRAUD_CS_AGENT;
GRANT USAGE ON DATABASE FRAUD_DEMO_DB TO ROLE FRAUD_AUDITOR;
GRANT USAGE ON SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_ANALYST;
GRANT USAGE ON SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_CS_AGENT;
GRANT USAGE ON SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_AUDITOR;
GRANT SELECT ON ALL TABLES IN SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_ANALYST;
GRANT SELECT ON ALL VIEWS  IN SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_ANALYST;
GRANT SELECT ON TABLE CARDHOLDERS TO ROLE FRAUD_CS_AGENT;
GRANT SELECT ON TABLE CARDS       TO ROLE FRAUD_CS_AGENT;
GRANT SELECT ON ALL TABLES IN SCHEMA FRAUD_DEMO_DB.CARDS TO ROLE FRAUD_AUDITOR;

-- [step:verify]
-- ============================================================================
-- STEP 5: VERIFY (run after loading data from the app)
-- ============================================================================
USE SECONDARY ROLES NONE;   -- each test role relies only on its own grants

-- Today's alert queue at the default threshold of 40
SELECT TXN_ID, TS, CARD_ID, AMOUNT, RISK_SCORE
FROM TXN_SCORED WHERE TS::DATE = '2026-11-10' AND RISK_SCORE >= 40
ORDER BY RISK_SCORE DESC, TS;

USE ROLE FRAUD_ANALYST;
SELECT 'FRAUD_ANALYST' AS role, h.FIRST_NAME, h.LAST_NAME, h.EMAIL, c.LAST4
FROM FRAUD_DEMO_DB.CARDS.CARDS c JOIN FRAUD_DEMO_DB.CARDS.CARDHOLDERS h USING (CARDHOLDER_ID) WHERE c.CARD_ID = 'K000303';
USE ROLE FRAUD_AUDITOR;
SELECT 'FRAUD_AUDITOR' AS role, h.FIRST_NAME, h.LAST_NAME, h.EMAIL, c.LAST4
FROM FRAUD_DEMO_DB.CARDS.CARDS c JOIN FRAUD_DEMO_DB.CARDS.CARDHOLDERS h USING (CARDHOLDER_ID) WHERE c.CARD_ID = 'K000303';
USE ROLE IDENTIFIER($demo_role);

-- [step:cleanup]
-- ============================================================================
-- STEP 6: CLEANUP (Optional - uncomment to remove everything)
-- ============================================================================

-- USE ROLE IDENTIFIER($demo_role);
-- USE SECONDARY ROLES ALL;                -- restore your usual setting if you use it
-- DROP DATABASE IF EXISTS FRAUD_DEMO_DB;   -- tables, view, policies and the Streamlit app
-- DROP WAREHOUSE IF EXISTS FRAUD_WH;
-- DROP ROLE IF EXISTS FRAUD_ANALYST;
-- DROP ROLE IF EXISTS FRAUD_CS_AGENT;
-- DROP ROLE IF EXISTS FRAUD_AUDITOR;
-- UNSET demo_role;
-- If you created the least-privilege role, an administrator removes it:
-- USE ROLE ACCOUNTADMIN;
-- DROP ROLE IF EXISTS FRAUD_DEMO_ROLE;
