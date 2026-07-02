import streamlit as st
import pandas as pd
import sqlite3
import io
import os
from datetime import datetime

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NeurologyInsurance Transformation Engine",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .block-container { padding-top: 1rem; }
    h1 { color: #4a9eff; font-size: 1.6rem !important; }
    h2 { color: #66bb6a; font-size: 1.2rem !important; }
    h3 { color: #90a4ae; font-size: 1rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { padding: 6px 14px; border-radius: 6px; }
    .stDownloadButton > button {
        background-color: #1976d2; color: white;
        border-radius: 6px; border: none; padding: 6px 16px;
    }
    .stButton > button {
        background-color: #1976d2; color: white;
        border-radius: 8px; border: none;
        padding: 10px 28px; font-size: 1rem; font-weight: bold;
    }
    .metric-card {
        background: #1e2a45; border-radius: 10px;
        padding: 12px 16px; text-align: center;
        border: 1px solid #2e3f6b;
    }
    .metric-value { font-size: 2rem; font-weight: bold; color: #4a9eff; }
    .metric-label { font-size: 0.75rem; color: #90a4ae; margin-top: 2px; }
    .log-success { background: #1b3a1e; border-left: 3px solid #4caf50;
                   padding: 4px 10px; margin: 2px 0; border-radius: 4px;
                   font-size: 0.8rem; color: #c8e6c9; }
    .log-warn    { background: #3e2c00; border-left: 3px solid #ff9800;
                   padding: 4px 10px; margin: 2px 0; border-radius: 4px;
                   font-size: 0.8rem; color: #ffe082; }
    .log-error   { background: #3e0000; border-left: 3px solid #f44336;
                   padding: 4px 10px; margin: 2px 0; border-radius: 4px;
                   font-size: 0.8rem; color: #ffcdd2; }
    .pipeline-box {
        border-radius: 8px; padding: 10px; text-align: center;
        font-weight: bold; font-size: 0.85rem; margin: 4px 0;
    }
    .session-card {
        background: #1e2a45; border-radius: 8px; padding: 10px 14px;
        border-left: 4px solid #4a9eff; margin: 6px 0; font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Database Setup ───────────────────────────────────────────────────────────
DB_PATH = "neuro_transform.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Sessions table — one row per transformation run
    c.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at TEXT,
        policies_in INTEGER,
        claims_in INTEGER,
        transformed INTEGER,
        warnings INTEGER,
        hard_rejects INTEGER,
        bureau_records INTEGER
    )""")
    # Canonical Policy
    c.execute("""CREATE TABLE IF NOT EXISTS canonical_policy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        PolicyNumber TEXT,
        InsuredName TEXT,
        PolicyEffectiveDate TEXT,
        CoverageType TEXT,
        PolicyLineageKey TEXT,
        TransformedAt TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    # Canonical Claim
    c.execute("""CREATE TABLE IF NOT EXISTS canonical_claim (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ClaimNumber TEXT,
        DestPolicyRef TEXT,
        DateOfLoss TEXT,
        TypeOfLossCode TEXT,
        ClaimPaid REAL,
        BenefitType TEXT,
        DiagnosisCode TEXT,
        TreatmentType TEXT,
        ClaimStatus TEXT,
        TransformedAt TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    # ISO Bureau
    c.execute("""CREATE TABLE IF NOT EXISTS bureau_iso (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ClaimNumber TEXT, PolicyRef TEXT, DateOfLoss TEXT,
        CauseOfLoss TEXT, AmountPaid REAL, ServiceCode TEXT,
        CoverageClass TEXT, ClaimStatusCode TEXT,
        ICD10_BureauRef TEXT, ProcedureClass TEXT,
        BureauReporter TEXT, EffectiveDate TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    # NCCI Bureau
    c.execute("""CREATE TABLE IF NOT EXISTS bureau_ncci (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ClaimNumber TEXT, PolicyRef TEXT, DateOfLoss TEXT,
        InjuryTypeCode TEXT, ClaimPaid REAL, BenefitClass TEXT,
        ClaimStateCode TEXT, BureauReporter TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    # FL State Bureau
    c.execute("""CREATE TABLE IF NOT EXISTS bureau_fl (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ClaimNumber TEXT, PolicyRef TEXT, DateOfLoss TEXT,
        FL_LossType TEXT, ClaimPaid REAL, FL_BenefitCode TEXT,
        FL_CoverageType TEXT, FL_ClaimStatus TEXT, BureauReporter TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    # Transform Log
    c.execute("""CREATE TABLE IF NOT EXISTS transform_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        RecordType TEXT, RecordID TEXT, Rule TEXT,
        Status TEXT, InputValue TEXT, OutputValue TEXT, Message TEXT,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )""")
    conn.commit()
    conn.close()

def save_to_db(session_meta, canonical_policies, canonical_claims,
               iso_rows, ncci_rows, fl_rows, log):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Insert session
    c.execute("""INSERT INTO sessions
        (run_at, policies_in, claims_in, transformed, warnings, hard_rejects, bureau_records)
        VALUES (?,?,?,?,?,?,?)""",
        (session_meta["run_at"], session_meta["policies_in"],
         session_meta["claims_in"], session_meta["transformed"],
         session_meta["warnings"], session_meta["hard_rejects"],
         session_meta["bureau_records"]))
    session_id = c.lastrowid

    for p in canonical_policies:
        c.execute("""INSERT INTO canonical_policy
            (session_id,PolicyNumber,InsuredName,PolicyEffectiveDate,CoverageType,PolicyLineageKey,TransformedAt)
            VALUES (?,?,?,?,?,?,?)""",
            (session_id, p["PolicyNumber"], p["InsuredName"],
             p["PolicyEffectiveDate"], p["CoverageType"],
             p["PolicyLineageKey"], p["TransformedAt"]))

    for cl in canonical_claims:
        c.execute("""INSERT INTO canonical_claim
            (session_id,ClaimNumber,DestPolicyRef,DateOfLoss,TypeOfLossCode,
             ClaimPaid,BenefitType,DiagnosisCode,TreatmentType,ClaimStatus,TransformedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, cl["ClaimNumber"], cl["DestPolicyRef"],
             cl["DateOfLoss"], cl["TypeOfLossCode"], cl["ClaimPaid"],
             cl["BenefitType"], cl["DiagnosisCode"], cl["TreatmentType"],
             cl["ClaimStatus"], cl["TransformedAt"]))

    for r in iso_rows:
        c.execute("""INSERT INTO bureau_iso
            (session_id,ClaimNumber,PolicyRef,DateOfLoss,CauseOfLoss,AmountPaid,
             ServiceCode,CoverageClass,ClaimStatusCode,ICD10_BureauRef,ProcedureClass,BureauReporter,EffectiveDate)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, r["ClaimNumber"], r["PolicyRef"], r["DateOfLoss"],
             r["CauseOfLoss"], r["AmountPaid"], r["ServiceCode"],
             r["CoverageClass"], r["ClaimStatusCode"], r["ICD10_BureauRef"],
             r["ProcedureClass"], r["BureauReporter"], r["EffectiveDate"]))

    for r in ncci_rows:
        c.execute("""INSERT INTO bureau_ncci
            (session_id,ClaimNumber,PolicyRef,DateOfLoss,InjuryTypeCode,
             ClaimPaid,BenefitClass,ClaimStateCode,BureauReporter)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (session_id, r["ClaimNumber"], r["PolicyRef"], r["DateOfLoss"],
             r["InjuryTypeCode"], r["ClaimPaid"], r["BenefitClass"],
             r["ClaimStateCode"], r["BureauReporter"]))

    for r in fl_rows:
        c.execute("""INSERT INTO bureau_fl
            (session_id,ClaimNumber,PolicyRef,DateOfLoss,FL_LossType,ClaimPaid,
             FL_BenefitCode,FL_CoverageType,FL_ClaimStatus,BureauReporter)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session_id, r["ClaimNumber"], r["PolicyRef"], r["DateOfLoss"],
             r["FL_LossType"], r["ClaimPaid"], r["FL_BenefitCode"],
             r["FL_CoverageType"], r["FL_ClaimStatus"], r["BureauReporter"]))

    for l in log:
        c.execute("""INSERT INTO transform_log
            (session_id,RecordType,RecordID,Rule,Status,InputValue,OutputValue,Message)
            VALUES (?,?,?,?,?,?,?,?)""",
            (session_id, l[0], l[1], l[2], l[3], l[4], l[5], l[6]))

    conn.commit()
    conn.close()
    return session_id

def get_sessions():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM sessions ORDER BY id DESC", conn)
    conn.close()
    return df

def get_session_data(session_id, table):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {table} WHERE session_id=?", conn, params=(session_id,))
    conn.close()
    df = df.drop(columns=["id","session_id"], errors="ignore")
    return df

def get_db_summary():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    totals = {}
    for tbl in ["sessions","canonical_policy","canonical_claim","bureau_iso","bureau_ncci","bureau_fl"]:
        c.execute(f"SELECT COUNT(*) FROM {tbl}")
        totals[tbl] = c.fetchone()[0]
    conn.close()
    return totals

def clear_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for tbl in ["transform_log","bureau_iso","bureau_ncci","bureau_fl",
                "canonical_policy","canonical_claim","sessions"]:
        c.execute(f"DELETE FROM {tbl}")
    conn.commit()
    conn.close()

def export_db_csv(table):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()

# ─── Lookup Tables ────────────────────────────────────────────────────────────
COVERAGE_LUT  = {"CC-01":"COMPREHENSIVE","CC-02":"SPECIALTY","CC-03":"WRAPAROUND","CC-04":"STANDARD","CC-99":"STANDARD"}
PLAN_TYPE_LUT = {"PT-COMP":"COMPREHENSIVE","PT-SPEC":"SPECIALTY","PT-WRAP":"WRAPAROUND","PT-STD":"STANDARD"}
LOSS_TYPE_LUT = {"001":"NEURO-001","NSD":"NEURO-001","002":"NEURO-002","TBI":"NEURO-002","003":"NEURO-003","SCI":"NEURO-003","004":"NEURO-004","PN":"NEURO-004"}
BENEFIT_LUT   = {"PT":"PHYSICAL_THERAPY","PHYSICAL THERAPY":"PHYSICAL_THERAPY","OT":"OCCUPATIONAL_THERAPY","OCCUPATIONAL THERAPY":"OCCUPATIONAL_THERAPY","RX":"PRESCRIPTION_DRUG","SX":"SURGERY","SURGERY":"SURGERY","DME":"DURABLE_MEDICAL"}
STATUS_LUT    = {"01":"OPEN","02":"CLOSED","03":"PENDING","04":"DENIED","OPEN":"OPEN","CLOSED":"CLOSED","PENDING":"PENDING","DENIED":"DENIED"}
ICD10_VALID   = {"G20","G21","G35","G36","G40","G43","G45","G47","G50","G54","G60","G61","G70","G71","G80","G89","G91","G93","G95","G99"}

ISO_CAUSE = {"NEURO-001":"0610","NEURO-002":"0612","NEURO-003":"0615","NEURO-004":"0618"}
ISO_SVC   = {"PHYSICAL_THERAPY":"PT-100","OCCUPATIONAL_THERAPY":"OT-100","PRESCRIPTION_DRUG":"RX-100","SURGERY":"SX-100","DURABLE_MEDICAL":"DME-100","UNCLASSIFIED":"UC-000","MEDICATION":"RX-100","UNSPECIFIED":"UC-000"}
ISO_COV   = {"COMPREHENSIVE":"ISO-CV-01","SPECIALTY":"ISO-CV-02","WRAPAROUND":"ISO-CV-03","STANDARD":"ISO-CV-01"}
ISO_STAT  = {"OPEN":"ISO-CS-01","CLOSED":"ISO-CS-02","PENDING":"ISO-CS-03","DENIED":"ISO-CS-04"}
ISO_ICD   = {"G20":"NEURO-PD-001","G35":"NEURO-MS-001","G40":"NEURO-EP-001","G43":"NEURO-MG-001","G45":"NEURO-TIA-001","G60":"NEURO-HPN-001","G70":"NEURO-MYG-001","G80":"NEURO-CP-001"}
ISO_PROC  = {"SURGERY":"ISO-PROC-SX","PHYSICAL_THERAPY":"ISO-PROC-PT","MEDICATION":"ISO-PROC-MED","PRESCRIPTION_DRUG":"ISO-PROC-MED","DURABLE_MEDICAL":"ISO-PROC-DME","OCCUPATIONAL_THERAPY":"ISO-PROC-PT"}
NCCI_INJ  = {"NEURO-001":"N-610","NEURO-002":"N-611","NEURO-003":"N-612","NEURO-004":"N-613"}
NCCI_BEN  = {"PHYSICAL_THERAPY":"NC-PT","OCCUPATIONAL_THERAPY":"NC-OT","PRESCRIPTION_DRUG":"NC-RX","MEDICATION":"NC-RX","SURGERY":"NC-SX","DURABLE_MEDICAL":"NC-DM","UNCLASSIFIED":"NC-UNK","UNSPECIFIED":"NC-UNK"}
NCCI_STAT = {"OPEN":"NCCI-ST-01","CLOSED":"NCCI-ST-02","PENDING":"NCCI-ST-03","DENIED":"NCCI-ST-04"}
FL_LOSS   = {"NEURO-001":"FL-9001","NEURO-002":"FL-9002","NEURO-003":"FL-9003","NEURO-004":"FL-9004"}
FL_BEN    = {"PHYSICAL_THERAPY":"FL-B01","OCCUPATIONAL_THERAPY":"FL-B02","PRESCRIPTION_DRUG":"FL-B03","MEDICATION":"FL-B03","SURGERY":"FL-B04","DURABLE_MEDICAL":"FL-B05","UNCLASSIFIED":"FL-B99","UNSPECIFIED":"FL-B99"}
FL_COV    = {"COMPREHENSIVE":"FL-CV-01","SPECIALTY":"FL-CV-02","WRAPAROUND":"FL-CV-03","STANDARD":"FL-CV-01"}
FL_STAT   = {"OPEN":"FL-CS-01","CLOSED":"FL-CS-02","PENDING":"FL-CS-03","DENIED":"FL-CS-04"}

SAMPLE_POLICY = """PolicyNo,NamedInsured,PolicyStartDate,CoverageCode,PlanType
P-2024-001,john smith,2024-01-01,CC-01,
P-2024-002,MARIA GARCIA,2024-02-15,CC-02,PT-SPEC
P-2024-003,robert chen,2024-03-01,,PT-COMP
P-2024-004,sarah johnson,2024-04-01,CC-03,
P-2024-005,james wilson,2024-05-15,CC-99,PT-STD"""

SAMPLE_CLAIM = """ClaimNo,PolicyNo,LossDate,LossTypeCode,AmountPaid,BenefitCategory,DiagCode,TreatmentDesc,ClaimStatusCode
C-2024-001,P-2024-001,2024-03-15,002,15000,PT,G35,Physical therapy and balance training,01
C-2024-002,P-2024-002,2024-04-10,SCI,45000,SX,G20,Surgical intervention for spinal decompression,02
C-2024-003,P-2024-003,2024-05-01,NSD,8500,RX,G40,Prescription medication management for seizures,01
C-2024-004,P-2024-001,2024-06-20,004,22000,DME,G60,Home medical equipment for neuropathy patient,03
C-2024-005,P-2024-002,2024-07-01,TBI,125000,OT,G43,Occupational therapy for migraine rehabilitation,04
C-2024-006,P-2024-004,2024-06-15,001,35000,PT,G70,Physical therapy for myasthenia gravis,01
C-2024-007,P-2024-005,2024-07-01,,5000,UNKNOWN,INVALID,Unknown treatment description,01"""

# ─── Helpers ─────────────────────────────────────────────────────────────────
def to_title_case(s):
    if not s or str(s).strip() == "" or str(s).strip().lower() == "nan":
        return None
    return " ".join(w.capitalize() for w in str(s).strip().split())

def classify_treatment(desc):
    if not desc or str(desc).strip() == "" or str(desc).strip().lower() == "nan":
        return "UNSPECIFIED", "LOW"
    d = str(desc).lower()
    if "surg" in d:                                                              return "SURGERY","HIGH"
    if "occupational" in d:                                                      return "OCCUPATIONAL_THERAPY","HIGH"
    if "physical therapy" in d or "balance" in d or "rehabilitation" in d:      return "PHYSICAL_THERAPY","HIGH"
    if "medication" in d or "prescription" in d or "seizure" in d or "drug" in d: return "MEDICATION","HIGH"
    if "equipment" in d or "dme" in d or "home medical" in d:                   return "DURABLE_MEDICAL","HIGH"
    return "UNSPECIFIED","LOW"

def csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()

def safe_str(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()

# ─── Transformation Engine ────────────────────────────────────────────────────
def run_transformation(policy_csv_text, claim_csv_text):
    log = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        policy_df = pd.read_csv(io.StringIO(policy_csv_text))
    except Exception as e:
        st.error(f"Policy CSV parse error: {e}"); return None
    try:
        claim_df = pd.read_csv(io.StringIO(claim_csv_text))
    except Exception as e:
        st.error(f"Claim CSV parse error: {e}"); return None

    canonical_policies = []
    for _, row in policy_df.iterrows():
        rec_id = safe_str(row.get("PolicyNo",""))
        pol_num = safe_str(row.get("PolicyNo",""))
        if not pol_num:
            log.append(("POLICY",rec_id or "?","TR-NI-001","ERROR","","","❌ ERR-001: PolicyNumber is required — HARD REJECT")); continue
        log.append(("POLICY",rec_id,"TR-NI-001","SUCCESS",row.get("PolicyNo",""),pol_num,"✅ PolicyNumber standardized"))
        insured = to_title_case(row.get("NamedInsured",""))
        log.append(("POLICY",rec_id,"TR-NI-002","SUCCESS",row.get("NamedInsured",""),insured or "","✅ InsuredName title-cased"))
        pol_date = safe_str(row.get("PolicyStartDate",""))
        try:
            pd.to_datetime(pol_date)
            log.append(("POLICY",rec_id,"TR-NI-003","SUCCESS",pol_date,pol_date,"✅ PolicyEffectiveDate valid"))
        except:
            log.append(("POLICY",rec_id,"TR-NI-003","ERROR",pol_date,"","❌ ERR-003: Invalid date — HARD REJECT")); continue
        cov_code  = safe_str(row.get("CoverageCode",""))
        plan_type = safe_str(row.get("PlanType",""))
        if cov_code:
            cov_type = COVERAGE_LUT.get(cov_code,"STANDARD")
            tag = "SUCCESS" if cov_code in COVERAGE_LUT else "WARN"
            msg = f"✅ CoverageType resolved via CoverageLUT" if tag=="SUCCESS" else "⚠️ WARN-004: CoverageCode unrecognized — defaulted to STANDARD"
            log.append(("POLICY",rec_id,"TR-NI-004",tag,cov_code,cov_type,msg))
        else:
            cov_type = PLAN_TYPE_LUT.get(plan_type,"STANDARD")
            tag = "SUCCESS" if plan_type and plan_type in PLAN_TYPE_LUT else "WARN"
            msg = f"✅ CoverageType via PlanTypeLUT fallback" if tag=="SUCCESS" else "⚠️ WARN-005: PlanType fallback — defaulted to STANDARD"
            log.append(("POLICY",rec_id,"TR-NI-005",tag,plan_type,cov_type,msg))
        lineage_key = f"LNK-{pol_num}"
        log.append(("POLICY",rec_id,"TR-NI-014","SUCCESS",pol_num,lineage_key,"✅ PolicyLineageKey generated"))
        canonical_policies.append({"PolicyNumber":pol_num,"InsuredName":insured or "","PolicyEffectiveDate":pol_date,"CoverageType":cov_type,"PolicyLineageKey":lineage_key,"TransformedAt":now})

    policy_map = {p["PolicyNumber"]: p for p in canonical_policies}
    pol_cov_map = {p["PolicyNumber"]: p["CoverageType"] for p in canonical_policies}
    canonical_claims = []
    hard_rejects = 0

    for _, row in claim_df.iterrows():
        rec_id = safe_str(row.get("ClaimNo",""))
        cl_num = safe_str(row.get("ClaimNo",""))
        if not cl_num:
            log.append(("CLAIM",rec_id or "?","TR-NI-006","ERROR","","","❌ ERR-006: ClaimNumber required — HARD REJECT")); hard_rejects+=1; continue
        log.append(("CLAIM",rec_id,"TR-NI-006","SUCCESS",row.get("ClaimNo",""),cl_num,"✅ ClaimNumber standardized"))
        loss_date = safe_str(row.get("LossDate",""))
        try:
            pd.to_datetime(loss_date)
            log.append(("CLAIM",rec_id,"TR-NI-007","SUCCESS",loss_date,loss_date,"✅ DateOfLoss valid"))
        except:
            log.append(("CLAIM",rec_id,"TR-NI-007","ERROR",loss_date,"","❌ ERR-007: Invalid LossDate — HARD REJECT")); hard_rejects+=1; continue
        loss_code = safe_str(row.get("LossTypeCode","")).upper()
        type_of_loss = LOSS_TYPE_LUT.get(loss_code)
        if not type_of_loss:
            log.append(("CLAIM",rec_id,"TR-NI-008","ERROR",loss_code,"","❌ ERR-008: LossTypeCode no canonical mapping — HARD REJECT")); hard_rejects+=1; continue
        log.append(("CLAIM",rec_id,"TR-NI-008","SUCCESS",loss_code,type_of_loss,f"✅ TypeOfLossCode → {type_of_loss}"))
        try:
            claim_paid = float(row.get("AmountPaid",0) or 0)
            if claim_paid < 0:
                log.append(("CLAIM",rec_id,"TR-NI-009","ERROR",str(claim_paid),"","❌ ERR-009B: Negative AmountPaid — HARD REJECT")); hard_rejects+=1; continue
            log.append(("CLAIM",rec_id,"TR-NI-009","SUCCESS",str(row.get("AmountPaid","")),f"{claim_paid:.2f}","✅ ClaimPaid cast to numeric"))
        except:
            claim_paid=0.00
            log.append(("CLAIM",rec_id,"TR-NI-009","WARN",str(row.get("AmountPaid","")), "0.00","⚠️ WARN-009: AmountPaid invalid — defaulted to 0.00"))
        ben_cat = safe_str(row.get("BenefitCategory","")).upper()
        benefit_type = BENEFIT_LUT.get(ben_cat)
        if benefit_type:
            log.append(("CLAIM",rec_id,"TR-NI-010","SUCCESS",ben_cat,benefit_type,"✅ BenefitType resolved"))
        else:
            benefit_type="UNCLASSIFIED"
            log.append(("CLAIM",rec_id,"TR-NI-010","WARN",ben_cat,"UNCLASSIFIED","⚠️ WARN-010: BenefitCategory unrecognized — UNCLASSIFIED"))
        diag_code = safe_str(row.get("DiagCode","")).upper()
        if diag_code in ICD10_VALID:
            log.append(("CLAIM",rec_id,"TR-NI-011","SUCCESS",diag_code,diag_code,"✅ DiagnosisCode valid ICD-10-CM"))
        else:
            log.append(("CLAIM",rec_id,"TR-NI-011","WARN",diag_code,"NULL",f"⚠️ WARN-011: DiagCode not in ICD-10-CM — set to NULL")); diag_code=""
        treat_desc = safe_str(row.get("TreatmentDesc",""))
        treat_type, confidence = classify_treatment(treat_desc)
        if treat_type=="UNSPECIFIED":
            log.append(("CLAIM",rec_id,"TR-NI-012","WARN",treat_desc,"UNSPECIFIED","⚠️ WARN-012: TreatmentType NLP LOW confidence"))
        else:
            log.append(("CLAIM",rec_id,"TR-NI-012","SUCCESS",treat_desc,treat_type,f"✅ TreatmentType NLP — {confidence} confidence"))
        status_code = safe_str(row.get("ClaimStatusCode","")).upper()
        claim_status = STATUS_LUT.get(status_code)
        if claim_status:
            log.append(("CLAIM",rec_id,"TR-NI-013","SUCCESS",status_code,claim_status,f"✅ ClaimStatus → {claim_status}"))
        else:
            claim_status="OPEN"
            log.append(("CLAIM",rec_id,"TR-NI-013","WARN",status_code,"OPEN","⚠️ WARN-013: ClaimStatus unrecognized — defaulted to OPEN"))
        pol_ref = safe_str(row.get("PolicyNo",""))
        log.append(("CLAIM",rec_id,"TR-NI-014","SUCCESS",pol_ref,pol_ref,"✅ DestPolicyRef FK joined"))
        canonical_claims.append({"ClaimNumber":cl_num,"DestPolicyRef":pol_ref,"DateOfLoss":loss_date,"TypeOfLossCode":type_of_loss,"ClaimPaid":round(claim_paid,2),"BenefitType":benefit_type,"DiagnosisCode":diag_code,"TreatmentType":treat_type,"ClaimStatus":claim_status,"TransformedAt":now})

    iso_rows, ncci_rows, fl_rows = [], [], []
    for c in canonical_claims:
        cov = pol_cov_map.get(c["DestPolicyRef"],"STANDARD")
        iso_rows.append({"ClaimNumber":c["ClaimNumber"],"PolicyRef":c["DestPolicyRef"],"DateOfLoss":c["DateOfLoss"],"CauseOfLoss":ISO_CAUSE.get(c["TypeOfLossCode"],""),"AmountPaid":c["ClaimPaid"],"ServiceCode":ISO_SVC.get(c["BenefitType"],"UC-000"),"CoverageClass":ISO_COV.get(cov,"ISO-CV-01"),"ClaimStatusCode":ISO_STAT.get(c["ClaimStatus"],"ISO-CS-01"),"ICD10_BureauRef":ISO_ICD.get(c["DiagnosisCode"],"NEURO-GEN-001") if c["DiagnosisCode"] else "NEURO-GEN-001","ProcedureClass":ISO_PROC.get(c["TreatmentType"],"ISO-PROC-UNK"),"BureauReporter":"ISO","EffectiveDate":"2024-01-01"})
        ncci_rows.append({"ClaimNumber":c["ClaimNumber"],"PolicyRef":c["DestPolicyRef"],"DateOfLoss":c["DateOfLoss"],"InjuryTypeCode":NCCI_INJ.get(c["TypeOfLossCode"],""),"ClaimPaid":c["ClaimPaid"],"BenefitClass":NCCI_BEN.get(c["BenefitType"],"NC-UNK"),"ClaimStateCode":NCCI_STAT.get(c["ClaimStatus"],"NCCI-ST-01"),"BureauReporter":"NCCI"})
        fl_rows.append({"ClaimNumber":c["ClaimNumber"],"PolicyRef":c["DestPolicyRef"],"DateOfLoss":c["DateOfLoss"],"FL_LossType":FL_LOSS.get(c["TypeOfLossCode"],""),"ClaimPaid":c["ClaimPaid"],"FL_BenefitCode":FL_BEN.get(c["BenefitType"],"FL-B99"),"FL_CoverageType":FL_COV.get(cov,"FL-CV-01"),"FL_ClaimStatus":FL_STAT.get(c["ClaimStatus"],"FL-CS-01"),"BureauReporter":"Florida State OIR"})

    warns  = sum(1 for r in log if r[3]=="WARN")
    bureau = len(iso_rows)+len(ncci_rows)+len(fl_rows)
    session_meta = {"run_at":now,"policies_in":len(canonical_policies),"claims_in":len(canonical_claims),"transformed":len(canonical_policies)+len(canonical_claims),"warnings":warns,"hard_rejects":hard_rejects,"bureau_records":bureau}

    session_id = save_to_db(session_meta, canonical_policies, canonical_claims, iso_rows, ncci_rows, fl_rows, log)

    return {"session_id":session_id,"canonical_policy":pd.DataFrame(canonical_policies),"canonical_claim":pd.DataFrame(canonical_claims),"iso":pd.DataFrame(iso_rows),"ncci":pd.DataFrame(ncci_rows),"fl_state":pd.DataFrame(fl_rows),"dest_policy":pd.DataFrame([{"DestPolicyNumber":p["PolicyNumber"],"DestInsuredName":p["InsuredName"],"EffectiveDate":p["PolicyEffectiveDate"],"CoverageCategory":p["CoverageType"],"PolicyLineageKey":p["PolicyLineageKey"],"TransformedAt":p["TransformedAt"]} for p in canonical_policies]),"dest_claim":pd.DataFrame([{"DestClaimNumber":c["ClaimNumber"],"DestPolicyRef":c["DestPolicyRef"],"LossDate":c["DateOfLoss"],"LossTypeCode":c["TypeOfLossCode"],"TotalAmountPaid":c["ClaimPaid"],"BenefitCategory":c["BenefitType"],"ICD10Code":c["DiagnosisCode"],"TreatmentCategory":c["TreatmentType"],"ClaimStatusDesc":c["ClaimStatus"],"TransformedAt":c["TransformedAt"]} for c in canonical_claims]),"log":log,"hard_rejects":hard_rejects,"session_meta":session_meta}

# ─── Initialize DB ────────────────────────────────────────────────────────────
init_db()

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 NeurologyInsurance")
    st.markdown("**Canonical Transformation Engine v3.0**")
    st.markdown("---")
    st.markdown("### Pipeline Layers")
    for label, bg, border in [("📥 SOURCE CSV","#1e3a5f","#4a9eff"),("⚙️ CANONICAL","#1a4731","#66bb6a"),("🏛️ BUREAU","#4a2c00","#ffa726"),("📤 DESTINATION","#3d1a4f","#ce93d8")]:
        st.markdown(f'<div class="pipeline-box" style="background:{bg};color:{border};border:1px solid {border};">{label}</div>', unsafe_allow_html=True)
        if label != "📤 DESTINATION": st.markdown(f'<div style="text-align:center;color:{border};font-size:1.2rem;">↓</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Transform Rules:** TR-NI-001 – TR-NI-014")
    st.markdown("**Lookup Tables:** CoverageLUT · PlanTypeLUT · LossTypeLUT · BenefitTypeLUT · ICD10_REF")
    st.markdown("**Bureau Reporters:** ISO · NCCI · FL State OIR")
    st.markdown("---")
    if os.path.exists(DB_PATH):
        totals = get_db_summary()
        st.markdown("### 🗄️ Database Status")
        st.markdown(f"**Sessions stored:** {totals.get('sessions',0)}")
        st.markdown(f"**Canonical policies:** {totals.get('canonical_policy',0)}")
        st.markdown(f"**Canonical claims:** {totals.get('canonical_claim',0)}")
        st.markdown(f"**Bureau records:** {totals.get('bureau_iso',0)+totals.get('bureau_ncci',0)+totals.get('bureau_fl',0)}")
    st.markdown("---")
    st.caption("POC Demo v3.0 · July 2026 · SQLite Persistence")

# ─── Main Header ─────────────────────────────────────────────────────────────
st.markdown("# 🏥 NeurologyInsurance — Canonical Transformation Engine")
st.markdown("**Source-Agnostic POC Demo** · CSV In → Canonical Rules → Bureau Flat Files → **SQLite Database** 🗄️")
st.markdown("---")

# ─── MAIN TABS ───────────────────────────────────────────────────────────────
main_tabs = st.tabs(["⚙️ Transform", "🗄️ Query History", "📊 Database Explorer"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TRANSFORM
# ══════════════════════════════════════════════════════════════════════════════
with main_tabs[0]:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        st.markdown("### 📄 Policy CSV Input")
        pol_upload = st.file_uploader("Upload Policy CSV", type=["csv"], key="pol_upload")
        if pol_upload:
            policy_text = pol_upload.read().decode("utf-8")
        else:
            policy_text = st.text_area("Or paste Policy CSV:", value=SAMPLE_POLICY, height=180, key="pol_area")
        if st.button("↺ Reset Policy Sample", key="reset_pol"):
            st.session_state["pol_area"] = SAMPLE_POLICY; st.rerun()

    with col_in2:
        st.markdown("### 📋 Claim CSV Input")
        cl_upload = st.file_uploader("Upload Claim CSV", type=["csv"], key="cl_upload")
        if cl_upload:
            claim_text = cl_upload.read().decode("utf-8")
        else:
            claim_text = st.text_area("Or paste Claim CSV:", value=SAMPLE_CLAIM, height=180, key="cl_area")
        if st.button("↺ Reset Claim Sample", key="reset_cl"):
            st.session_state["cl_area"] = SAMPLE_CLAIM; st.rerun()

    st.markdown("---")
    run_col, info_col = st.columns([1, 3])
    with run_col:
        run_btn = st.button("▶ RUN TRANSFORMATION", use_container_width=True)
    with info_col:
        st.info("💾 Results are automatically saved to the local SQLite database after every run.")

    if run_btn:
        with st.spinner("⚙️ Applying transformation rules & saving to database…"):
            results = run_transformation(policy_text, claim_text)
        if results:
            st.success(f"✅ Transformation complete & saved — Session #{results['session_id']} · {datetime.now().strftime('%H:%M:%S')}")
            st.session_state["results"] = results

    if "results" in st.session_state:
        results = st.session_state["results"]
        log = results["log"]
        warns  = sum(1 for r in log if r[3]=="WARN")
        errors = sum(1 for r in log if r[3]=="ERROR")
        bureau_outs = len(results["iso"])+len(results["ncci"])+len(results["fl_state"])
        st.markdown("---")
        c1,c2,c3,c4,c5,c6 = st.columns(6)
        for col,label,val,color in [(c1,"Policies In",len(results["canonical_policy"]),"#4a9eff"),(c2,"Claims In",len(results["canonical_claim"]),"#4a9eff"),(c3,"Transformed",len(results["canonical_policy"])+len(results["canonical_claim"]),"#66bb6a"),(c4,"Warnings",warns,"#ff9800"),(c5,"Hard Rejects",results["hard_rejects"],"#f44336"),(c6,"Bureau Records",bureau_outs,"#ce93d8")]:
            col.markdown(f'<div class="metric-card"><div class="metric-value" style="color:{color}">{val}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 📤 Output Files")
        tabs = st.tabs(["⚙️ Canonical Policy","⚙️ Canonical Claim","🏛️ ISO Bureau","🏛️ NCCI Bureau","🏛️ FL State OIR","📦 DestPolicy","📦 DestClaim"])
        for tab, df, fname in zip(tabs,[results["canonical_policy"],results["canonical_claim"],results["iso"],results["ncci"],results["fl_state"],results["dest_policy"],results["dest_claim"]],["canonical_policy.csv","canonical_claim.csv","bureau_ISO.csv","bureau_NCCI.csv","bureau_FL_State.csv","dest_policy.csv","dest_claim.csv"]):
            with tab:
                if df.empty: st.warning("No records."); continue
                st.markdown(f"**{len(df)} record(s)** — also saved to database ✅")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(f"⬇ Download {fname}", data=csv_bytes(df), file_name=fname, mime="text/csv", key=fname)

        st.markdown("---")
        with st.expander("📋 Transformation Log", expanded=True):
            c1, c2 = st.columns(2)
            with c1: fs = st.selectbox("Status:", ["ALL","SUCCESS","WARN","ERROR"], key="lf1")
            with c2: ft = st.selectbox("Type:", ["ALL","POLICY","CLAIM"], key="lf2")
            log_df = pd.DataFrame(log, columns=["Type","RecordID","Rule","Status","InputValue","OutputValue","Message"])
            if fs!="ALL": log_df=log_df[log_df["Status"]==fs]
            if ft!="ALL": log_df=log_df[log_df["Type"]==ft]
            for _, r in log_df.iterrows():
                css = "log-success" if r.Status=="SUCCESS" else ("log-warn" if r.Status=="WARN" else "log-error")
                st.markdown(f'<div class="{css}"><b>[{r.Type}]</b> {r.RecordID} · <b>{r.Rule}</b> · <span style="opacity:0.7">{r.InputValue} → {r.OutputValue}</span> · {r.Message}</div>', unsafe_allow_html=True)
            st.caption(f"Showing {len(log_df)} of {len(log)} entries")
    else:
        st.info("💡 Sample data is pre-loaded. Click **▶ RUN TRANSFORMATION** to begin.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — QUERY HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with main_tabs[1]:
    st.markdown("### 🗄️ Transformation Session History")
    st.markdown("Every time you click Run, a session is automatically saved here.")
    if st.button("🔄 Refresh History"):
        st.rerun()

    sessions_df = get_sessions()
    if sessions_df.empty:
        st.info("No sessions yet — run a transformation first!")
    else:
        st.markdown(f"**{len(sessions_df)} session(s) recorded**")
        st.dataframe(sessions_df.rename(columns={"id":"Session","run_at":"Run At","policies_in":"Policies","claims_in":"Claims","transformed":"Transformed","warnings":"Warnings","hard_rejects":"Hard Rejects","bureau_records":"Bureau Records"}), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 🔍 Drill Into a Session")
        session_ids = sessions_df["id"].tolist()
        sel_id = st.selectbox("Select Session ID:", session_ids, format_func=lambda x: f"Session #{x} — {sessions_df[sessions_df['id']==x]['run_at'].values[0]}")
        drill_tab = st.selectbox("View table:", ["canonical_policy","canonical_claim","bureau_iso","bureau_ncci","bureau_fl","transform_log"])
        drill_df = get_session_data(sel_id, drill_tab)
        st.markdown(f"**{len(drill_df)} record(s)** in `{drill_tab}` for Session #{sel_id}")
        st.dataframe(drill_df, use_container_width=True, hide_index=True)
        st.download_button(f"⬇ Download Session #{sel_id} · {drill_tab}.csv", data=csv_bytes(drill_df), file_name=f"session_{sel_id}_{drill_tab}.csv", mime="text/csv", key=f"dl_{sel_id}_{drill_tab}")

        st.markdown("---")
        with st.expander("⚠️ Danger Zone"):
            st.warning("This will permanently delete ALL sessions and records from the database.")
            if st.button("🗑️ Clear Entire Database", type="primary"):
                clear_database()
                st.success("Database cleared!"); st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DATABASE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with main_tabs[2]:
    st.markdown("### 📊 Full Database Explorer")
    st.markdown("Browse and download the complete contents of every database table.")

    if not os.path.exists(DB_PATH):
        st.info("No database yet — run a transformation first!")
    else:
        totals = get_db_summary()
        c1,c2,c3,c4,c5,c6 = st.columns(6)
        for col,label,val in [(c1,"Sessions",totals.get("sessions",0)),(c2,"Canon Policies",totals.get("canonical_policy",0)),(c3,"Canon Claims",totals.get("canonical_claim",0)),(c4,"ISO Records",totals.get("bureau_iso",0)),(c5,"NCCI Records",totals.get("bureau_ncci",0)),(c6,"FL Records",totals.get("bureau_fl",0))]:
            col.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#4a9eff">{val}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        tbl_tabs = st.tabs(["Sessions","Canonical Policy","Canonical Claim","ISO Bureau","NCCI Bureau","FL State","Transform Log"])
        for ttab, tbl in zip(tbl_tabs,["sessions","canonical_policy","canonical_claim","bureau_iso","bureau_ncci","bureau_fl","transform_log"]):
            with ttab:
                conn = sqlite3.connect(DB_PATH)
                df = pd.read_sql_query(f"SELECT * FROM {tbl} ORDER BY id DESC", conn)
                conn.close()
                df = df.drop(columns=["id"], errors="ignore")
                st.markdown(f"**{len(df)} total record(s)** in `{tbl}`")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(f"⬇ Download full {tbl}.csv", data=export_db_csv(tbl), file_name=f"db_{tbl}_full.csv", mime="text/csv", key=f"full_{tbl}")
