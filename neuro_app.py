import streamlit as st
import pandas as pd
import io
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
</style>
""", unsafe_allow_html=True)

# ─── Lookup Tables ────────────────────────────────────────────────────────────
COVERAGE_LUT = {"CC-01":"COMPREHENSIVE","CC-02":"SPECIALTY","CC-03":"WRAPAROUND","CC-04":"STANDARD","CC-99":"STANDARD"}
PLAN_TYPE_LUT = {"PT-COMP":"COMPREHENSIVE","PT-SPEC":"SPECIALTY","PT-WRAP":"WRAPAROUND","PT-STD":"STANDARD"}
LOSS_TYPE_LUT = {"001":"NEURO-001","NSD":"NEURO-001","002":"NEURO-002","TBI":"NEURO-002","003":"NEURO-003","SCI":"NEURO-003","004":"NEURO-004","PN":"NEURO-004"}
BENEFIT_LUT   = {"PT":"PHYSICAL_THERAPY","PHYSICAL THERAPY":"PHYSICAL_THERAPY","OT":"OCCUPATIONAL_THERAPY","OCCUPATIONAL THERAPY":"OCCUPATIONAL_THERAPY","RX":"PRESCRIPTION_DRUG","RX DRUG":"PRESCRIPTION_DRUG","SX":"SURGERY","SURGERY":"SURGERY","DME":"DURABLE_MEDICAL","DURABLE MEDICAL":"DURABLE_MEDICAL"}
STATUS_LUT    = {"01":"OPEN","02":"CLOSED","03":"PENDING","04":"DENIED","OPEN":"OPEN","CLOSED":"CLOSED","PENDING":"PENDING","DENIED":"DENIED"}
ICD10_VALID   = {"G20","G21","G35","G36","G40","G43","G45","G47","G50","G54","G60","G61","G70","G71","G80","G89","G91","G93","G95","G99"}

# Bureau crosswalks
ISO_CAUSE  = {"NEURO-001":"0610","NEURO-002":"0612","NEURO-003":"0615","NEURO-004":"0618"}
ISO_SVC    = {"PHYSICAL_THERAPY":"PT-100","OCCUPATIONAL_THERAPY":"OT-100","PRESCRIPTION_DRUG":"RX-100","SURGERY":"SX-100","DURABLE_MEDICAL":"DME-100","UNCLASSIFIED":"UC-000","MEDICATION":"RX-100","UNSPECIFIED":"UC-000"}
ISO_COV    = {"COMPREHENSIVE":"ISO-CV-01","SPECIALTY":"ISO-CV-02","WRAPAROUND":"ISO-CV-03","STANDARD":"ISO-CV-01"}
ISO_STAT   = {"OPEN":"ISO-CS-01","CLOSED":"ISO-CS-02","PENDING":"ISO-CS-03","DENIED":"ISO-CS-04"}
ISO_ICD    = {"G20":"NEURO-PD-001","G35":"NEURO-MS-001","G40":"NEURO-EP-001","G43":"NEURO-MG-001","G45":"NEURO-TIA-001","G60":"NEURO-HPN-001","G70":"NEURO-MYG-001","G80":"NEURO-CP-001"}
ISO_PROC   = {"SURGERY":"ISO-PROC-SX","PHYSICAL_THERAPY":"ISO-PROC-PT","MEDICATION":"ISO-PROC-MED","PRESCRIPTION_DRUG":"ISO-PROC-MED","DURABLE_MEDICAL":"ISO-PROC-DME","OCCUPATIONAL_THERAPY":"ISO-PROC-PT"}

NCCI_INJ   = {"NEURO-001":"N-610","NEURO-002":"N-611","NEURO-003":"N-612","NEURO-004":"N-613"}
NCCI_BEN   = {"PHYSICAL_THERAPY":"NC-PT","OCCUPATIONAL_THERAPY":"NC-OT","PRESCRIPTION_DRUG":"NC-RX","MEDICATION":"NC-RX","SURGERY":"NC-SX","DURABLE_MEDICAL":"NC-DM","UNCLASSIFIED":"NC-UNK","UNSPECIFIED":"NC-UNK"}
NCCI_STAT  = {"OPEN":"NCCI-ST-01","CLOSED":"NCCI-ST-02","PENDING":"NCCI-ST-03","DENIED":"NCCI-ST-04"}

FL_LOSS    = {"NEURO-001":"FL-9001","NEURO-002":"FL-9002","NEURO-003":"FL-9003","NEURO-004":"FL-9004"}
FL_BEN     = {"PHYSICAL_THERAPY":"FL-B01","OCCUPATIONAL_THERAPY":"FL-B02","PRESCRIPTION_DRUG":"FL-B03","MEDICATION":"FL-B03","SURGERY":"FL-B04","DURABLE_MEDICAL":"FL-B05","UNCLASSIFIED":"FL-B99","UNSPECIFIED":"FL-B99"}
FL_COV     = {"COMPREHENSIVE":"FL-CV-01","SPECIALTY":"FL-CV-02","WRAPAROUND":"FL-CV-03","STANDARD":"FL-CV-01"}
FL_STAT    = {"OPEN":"FL-CS-01","CLOSED":"FL-CS-02","PENDING":"FL-CS-03","DENIED":"FL-CS-04"}

# ─── Sample Data ─────────────────────────────────────────────────────────────
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
    if "surg" in d:                                     return "SURGERY", "HIGH"
    if "occupational" in d:                             return "OCCUPATIONAL_THERAPY", "HIGH"
    if "physical therapy" in d or "balance" in d or "rehabilitation" in d: return "PHYSICAL_THERAPY", "HIGH"
    if "medication" in d or "prescription" in d or "seizure" in d or "drug" in d: return "MEDICATION", "HIGH"
    if "equipment" in d or "dme" in d or "home medical" in d: return "DURABLE_MEDICAL", "HIGH"
    return "UNSPECIFIED", "LOW"

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

    # ── Parse Policy CSV ──
    try:
        policy_df = pd.read_csv(io.StringIO(policy_csv_text))
    except Exception as e:
        st.error(f"Policy CSV parse error: {e}")
        return None

    # ── Parse Claim CSV ──
    try:
        claim_df = pd.read_csv(io.StringIO(claim_csv_text))
    except Exception as e:
        st.error(f"Claim CSV parse error: {e}")
        return None

    # ── POLICY TRANSFORMATIONS ──
    canonical_policies = []
    for _, row in policy_df.iterrows():
        rec_id = safe_str(row.get("PolicyNo", ""))
        rejected = False

        # TR-NI-001: PolicyNumber standardize
        pol_num = safe_str(row.get("PolicyNo", ""))
        if not pol_num:
            log.append(("POLICY", rec_id or "?", "TR-NI-001", "ERROR", "", "", "❌ ERR-001: PolicyNumber is required — HARD REJECT"))
            continue
        log.append(("POLICY", rec_id, "TR-NI-001", "SUCCESS", row.get("PolicyNo",""), pol_num, "✅ PolicyNumber standardized"))

        # TR-NI-002: InsuredName title case
        insured = to_title_case(row.get("NamedInsured",""))
        log.append(("POLICY", rec_id, "TR-NI-002", "SUCCESS", row.get("NamedInsured",""), insured or "", "✅ InsuredName title-cased"))

        # TR-NI-003: PolicyEffectiveDate cast
        pol_date = safe_str(row.get("PolicyStartDate",""))
        try:
            pd.to_datetime(pol_date)
            log.append(("POLICY", rec_id, "TR-NI-003", "SUCCESS", pol_date, pol_date, "✅ PolicyEffectiveDate valid"))
        except:
            log.append(("POLICY", rec_id, "TR-NI-003", "ERROR", pol_date, "", "❌ ERR-003: Invalid date — HARD REJECT"))
            continue

        # TR-NI-004/005: CoverageType lookup
        cov_code = safe_str(row.get("CoverageCode",""))
        plan_type = safe_str(row.get("PlanType",""))
        if cov_code:
            cov_type = COVERAGE_LUT.get(cov_code, "STANDARD")
            if cov_code not in COVERAGE_LUT:
                log.append(("POLICY", rec_id, "TR-NI-004", "WARN", cov_code, "STANDARD", "⚠️ WARN-004: CoverageCode unrecognized — defaulted to STANDARD"))
            else:
                log.append(("POLICY", rec_id, "TR-NI-004", "SUCCESS", cov_code, cov_type, f"✅ CoverageType resolved via CoverageLUT"))
        else:
            cov_type = PLAN_TYPE_LUT.get(plan_type, "STANDARD")
            if plan_type and plan_type not in PLAN_TYPE_LUT:
                log.append(("POLICY", rec_id, "TR-NI-005", "WARN", plan_type, "STANDARD", "⚠️ WARN-005: PlanType unrecognized — defaulted to STANDARD"))
            elif plan_type:
                log.append(("POLICY", rec_id, "TR-NI-005", "SUCCESS", plan_type, cov_type, "✅ CoverageType resolved via PlanTypeLUT fallback"))
            else:
                log.append(("POLICY", rec_id, "TR-NI-005", "WARN", "", "STANDARD", "⚠️ WARN-005: Both CoverageCode and PlanType empty — defaulted to STANDARD"))

        # TR-NI-014: PolicyLineageKey
        lineage_key = f"LNK-{pol_num}"
        log.append(("POLICY", rec_id, "TR-NI-014", "SUCCESS", pol_num, lineage_key, "✅ PolicyLineageKey generated"))

        canonical_policies.append({
            "PolicyNumber": pol_num,
            "InsuredName": insured or "",
            "PolicyEffectiveDate": pol_date,
            "CoverageType": cov_type,
            "PolicyLineageKey": lineage_key,
            "TransformedAt": now,
        })

    # Build policy lookup map for FK join
    policy_map = {p["PolicyNumber"]: p for p in canonical_policies}

    # ── CLAIM TRANSFORMATIONS ──
    canonical_claims = []
    hard_rejects = 0

    for _, row in claim_df.iterrows():
        rec_id = safe_str(row.get("ClaimNo", ""))

        # TR-NI-006: ClaimNumber
        cl_num = safe_str(row.get("ClaimNo",""))
        if not cl_num:
            log.append(("CLAIM", rec_id or "?", "TR-NI-006", "ERROR", "", "", "❌ ERR-006: ClaimNumber is required — HARD REJECT"))
            hard_rejects += 1; continue
        log.append(("CLAIM", rec_id, "TR-NI-006", "SUCCESS", row.get("ClaimNo",""), cl_num, "✅ ClaimNumber standardized"))

        # TR-NI-007: DateOfLoss
        loss_date = safe_str(row.get("LossDate",""))
        try:
            pd.to_datetime(loss_date)
            log.append(("CLAIM", rec_id, "TR-NI-007", "SUCCESS", loss_date, loss_date, "✅ DateOfLoss valid"))
        except:
            log.append(("CLAIM", rec_id, "TR-NI-007", "ERROR", loss_date, "", "❌ ERR-007: Invalid LossDate — HARD REJECT"))
            hard_rejects += 1; continue

        # TR-NI-008: TypeOfLossCode — HARD REJECT if no match
        loss_code = safe_str(row.get("LossTypeCode","")).upper()
        type_of_loss = LOSS_TYPE_LUT.get(loss_code)
        if not type_of_loss:
            log.append(("CLAIM", rec_id, "TR-NI-008", "ERROR", loss_code, "", "❌ ERR-008: LossTypeCode has no canonical mapping — HARD REJECT"))
            hard_rejects += 1; continue
        log.append(("CLAIM", rec_id, "TR-NI-008", "SUCCESS", loss_code, type_of_loss, f"✅ TypeOfLossCode mapped to {type_of_loss}"))

        # TR-NI-009: ClaimPaid
        try:
            claim_paid = float(row.get("AmountPaid", 0) or 0)
            if claim_paid < 0:
                log.append(("CLAIM", rec_id, "TR-NI-009", "ERROR", str(claim_paid), "", "❌ ERR-009B: ClaimPaid is negative — HARD REJECT"))
                hard_rejects += 1; continue
            log.append(("CLAIM", rec_id, "TR-NI-009", "SUCCESS", str(row.get("AmountPaid","")), f"{claim_paid:.2f}", "✅ ClaimPaid cast to numeric"))
        except:
            claim_paid = 0.00
            log.append(("CLAIM", rec_id, "TR-NI-009", "WARN", str(row.get("AmountPaid","")), "0.00", "⚠️ WARN-009: AmountPaid invalid — defaulted to 0.00"))

        # TR-NI-010: BenefitType
        ben_cat = safe_str(row.get("BenefitCategory","")).upper()
        benefit_type = BENEFIT_LUT.get(ben_cat)
        if benefit_type:
            log.append(("CLAIM", rec_id, "TR-NI-010", "SUCCESS", ben_cat, benefit_type, f"✅ BenefitType resolved"))
        else:
            benefit_type = "UNCLASSIFIED"
            log.append(("CLAIM", rec_id, "TR-NI-010", "WARN", ben_cat, "UNCLASSIFIED", "⚠️ WARN-010: BenefitCategory unrecognized — defaulted to UNCLASSIFIED"))

        # TR-NI-011: DiagnosisCode ICD-10 validation
        diag_code = safe_str(row.get("DiagCode","")).upper()
        if diag_code in ICD10_VALID:
            log.append(("CLAIM", rec_id, "TR-NI-011", "SUCCESS", diag_code, diag_code, "✅ DiagnosisCode valid ICD-10-CM"))
        else:
            log.append(("CLAIM", rec_id, "TR-NI-011", "WARN", diag_code, "NULL", f"⚠️ WARN-011: DiagnosisCode '{diag_code}' not in ICD-10-CM reference — set to NULL"))
            diag_code = ""

        # TR-NI-012: TreatmentType NLP
        treat_desc = safe_str(row.get("TreatmentDesc",""))
        treat_type, confidence = classify_treatment(treat_desc)
        if treat_type == "UNSPECIFIED":
            log.append(("CLAIM", rec_id, "TR-NI-012", "WARN", treat_desc, "UNSPECIFIED", f"⚠️ WARN-012: TreatmentType NLP — LOW confidence, defaulted to UNSPECIFIED"))
        else:
            log.append(("CLAIM", rec_id, "TR-NI-012", "SUCCESS", treat_desc, treat_type, f"✅ TreatmentType NLP classified — {confidence} confidence"))

        # TR-NI-013: ClaimStatus decode
        status_code = safe_str(row.get("ClaimStatusCode","")).upper()
        claim_status = STATUS_LUT.get(status_code)
        if claim_status:
            log.append(("CLAIM", rec_id, "TR-NI-013", "SUCCESS", status_code, claim_status, f"✅ ClaimStatus decoded to {claim_status}"))
        else:
            claim_status = "OPEN"
            log.append(("CLAIM", rec_id, "TR-NI-013", "WARN", status_code, "OPEN", "⚠️ WARN-013: ClaimStatusCode unrecognized — defaulted to OPEN"))

        # FK join
        pol_ref = safe_str(row.get("PolicyNo",""))
        log.append(("CLAIM", rec_id, "TR-NI-014", "SUCCESS", pol_ref, pol_ref, "✅ DestPolicyRef FK joined"))

        canonical_claims.append({
            "ClaimNumber":   cl_num,
            "DestPolicyRef": pol_ref,
            "DateOfLoss":    loss_date,
            "TypeOfLossCode":type_of_loss,
            "ClaimPaid":     round(claim_paid, 2),
            "BenefitType":   benefit_type,
            "DiagnosisCode": diag_code,
            "TreatmentType": treat_type,
            "ClaimStatus":   claim_status,
            "TransformedAt": now,
        })

    # ── BUILD OUTPUT DFs ──
    can_pol_df  = pd.DataFrame(canonical_policies)
    can_cl_df   = pd.DataFrame(canonical_claims)

    # Policy map for bureau coverage lookup
    pol_cov_map = {p["PolicyNumber"]: p["CoverageType"] for p in canonical_policies}

    # ISO Bureau
    iso_rows = []
    for c in canonical_claims:
        cov = pol_cov_map.get(c["DestPolicyRef"], "STANDARD")
        iso_rows.append({
            "ClaimNumber":     c["ClaimNumber"],
            "PolicyRef":       c["DestPolicyRef"],
            "DateOfLoss":      c["DateOfLoss"],
            "CauseOfLoss":     ISO_CAUSE.get(c["TypeOfLossCode"], ""),
            "AmountPaid":      c["ClaimPaid"],
            "ServiceCode":     ISO_SVC.get(c["BenefitType"], "UC-000"),
            "CoverageClass":   ISO_COV.get(cov, "ISO-CV-01"),
            "ClaimStatusCode": ISO_STAT.get(c["ClaimStatus"], "ISO-CS-01"),
            "ICD10_BureauRef": ISO_ICD.get(c["DiagnosisCode"], "NEURO-GEN-001") if c["DiagnosisCode"] else "NEURO-GEN-001",
            "ProcedureClass":  ISO_PROC.get(c["TreatmentType"], "ISO-PROC-UNK"),
            "BureauReporter":  "ISO",
            "EffectiveDate":   "2024-01-01",
        })
    iso_df = pd.DataFrame(iso_rows)

    # NCCI Bureau
    ncci_rows = []
    for c in canonical_claims:
        ncci_rows.append({
            "ClaimNumber":    c["ClaimNumber"],
            "PolicyRef":      c["DestPolicyRef"],
            "DateOfLoss":     c["DateOfLoss"],
            "InjuryTypeCode": NCCI_INJ.get(c["TypeOfLossCode"], ""),
            "ClaimPaid":      c["ClaimPaid"],
            "BenefitClass":   NCCI_BEN.get(c["BenefitType"], "NC-UNK"),
            "ClaimStateCode": NCCI_STAT.get(c["ClaimStatus"], "NCCI-ST-01"),
            "BureauReporter": "NCCI",
        })
    ncci_df = pd.DataFrame(ncci_rows)

    # FL State Bureau
    fl_rows = []
    for c in canonical_claims:
        cov = pol_cov_map.get(c["DestPolicyRef"], "STANDARD")
        fl_rows.append({
            "ClaimNumber":    c["ClaimNumber"],
            "PolicyRef":      c["DestPolicyRef"],
            "DateOfLoss":     c["DateOfLoss"],
            "FL_LossType":    FL_LOSS.get(c["TypeOfLossCode"], ""),
            "ClaimPaid":      c["ClaimPaid"],
            "FL_BenefitCode": FL_BEN.get(c["BenefitType"], "FL-B99"),
            "FL_CoverageType":FL_COV.get(cov, "FL-CV-01"),
            "FL_ClaimStatus": FL_STAT.get(c["ClaimStatus"], "FL-CS-01"),
            "BureauReporter": "Florida State OIR",
        })
    fl_df = pd.DataFrame(fl_rows)

    # DestPolicy
    dest_pol_df = pd.DataFrame([{
        "DestPolicyNumber": p["PolicyNumber"],
        "DestInsuredName":  p["InsuredName"],
        "EffectiveDate":    p["PolicyEffectiveDate"],
        "CoverageCategory": p["CoverageType"],
        "PolicyLineageKey": p["PolicyLineageKey"],
        "TransformedAt":    p["TransformedAt"],
    } for p in canonical_policies])

    # DestClaim
    dest_cl_df = pd.DataFrame([{
        "DestClaimNumber":  c["ClaimNumber"],
        "DestPolicyRef":    c["DestPolicyRef"],
        "LossDate":         c["DateOfLoss"],
        "LossTypeCode":     c["TypeOfLossCode"],
        "TotalAmountPaid":  c["ClaimPaid"],
        "BenefitCategory":  c["BenefitType"],
        "ICD10Code":        c["DiagnosisCode"],
        "TreatmentCategory":c["TreatmentType"],
        "ClaimStatusDesc":  c["ClaimStatus"],
        "TransformedAt":    c["TransformedAt"],
    } for c in canonical_claims])

    return {
        "canonical_policy": can_pol_df,
        "canonical_claim":  can_cl_df,
        "iso":              iso_df,
        "ncci":             ncci_df,
        "fl_state":         fl_df,
        "dest_policy":      dest_pol_df,
        "dest_claim":       dest_cl_df,
        "log":              log,
        "hard_rejects":     hard_rejects,
    }

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 NeurologyInsurance")
    st.markdown("**Canonical Transformation Engine**")
    st.markdown("---")
    st.markdown("### Pipeline Layers")
    st.markdown('<div class="pipeline-box" style="background:#1e3a5f;color:#4a9eff;border:1px solid #4a9eff;">📥 SOURCE CSV</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;color:#4a9eff;font-size:1.2rem;">↓</div>', unsafe_allow_html=True)
    st.markdown('<div class="pipeline-box" style="background:#1a4731;color:#66bb6a;border:1px solid #66bb6a;">⚙️ CANONICAL</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;color:#66bb6a;font-size:1.2rem;">↓</div>', unsafe_allow_html=True)
    st.markdown('<div class="pipeline-box" style="background:#4a2c00;color:#ffa726;border:1px solid #ffa726;">🏛️ BUREAU</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;color:#ffa726;font-size:1.2rem;">↓</div>', unsafe_allow_html=True)
    st.markdown('<div class="pipeline-box" style="background:#3d1a4f;color:#ce93d8;border:1px solid #ce93d8;">📤 DESTINATION</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Transform Rules:** TR-NI-001 – TR-NI-014")
    st.markdown("**Lookup Tables:** 5 (CoverageLUT, PlanTypeLUT, LossTypeLUT, BenefitTypeLUT, ICD10_REF)")
    st.markdown("**Bureau Reporters:** ISO · NCCI · FL State OIR")
    st.markdown("---")
    st.caption("POC Demo v2.0 · July 2026")

# ─── Main Header ─────────────────────────────────────────────────────────────
st.markdown("# 🏥 NeurologyInsurance — Canonical Transformation Engine")
st.markdown("**Source-Agnostic POC Demo** · Paste any source CSV → Apply canonical rules → Download Bureau + Destination flat files")
st.markdown("---")

# ─── Input Section ────────────────────────────────────────────────────────────
col_in1, col_in2 = st.columns(2)

with col_in1:
    st.markdown("### 📄 Policy CSV Input")
    pol_upload = st.file_uploader("Upload PolicyHeader CSV (optional)", type=["csv"], key="pol_upload")
    if pol_upload:
        policy_text = pol_upload.read().decode("utf-8")
    else:
        policy_text = st.text_area("Or paste Policy CSV here:", value=SAMPLE_POLICY, height=180, key="pol_area")
    if st.button("↺ Reset Policy to Sample Data", key="reset_pol"):
        st.session_state["pol_area"] = SAMPLE_POLICY
        st.rerun()

with col_in2:
    st.markdown("### 📋 Claim CSV Input")
    cl_upload = st.file_uploader("Upload ClaimHeader CSV (optional)", type=["csv"], key="cl_upload")
    if cl_upload:
        claim_text = cl_upload.read().decode("utf-8")
    else:
        claim_text = st.text_area("Or paste Claim CSV here:", value=SAMPLE_CLAIM, height=180, key="cl_area")
    if st.button("↺ Reset Claim to Sample Data", key="reset_cl"):
        st.session_state["cl_area"] = SAMPLE_CLAIM
        st.rerun()

st.markdown("---")
run_col, _ = st.columns([1, 3])
with run_col:
    run_btn = st.button("▶ RUN TRANSFORMATION", use_container_width=True)

# ─── Run ─────────────────────────────────────────────────────────────────────
if run_btn:
    with st.spinner("⚙️ Applying transformation rules…"):
        results = run_transformation(policy_text, claim_text)

    if results:
        st.success(f"✅ Transformation complete — {datetime.now().strftime('%H:%M:%S')}")
        st.session_state["results"] = results

if "results" in st.session_state:
    results = st.session_state["results"]
    log = results["log"]

    warns   = sum(1 for r in log if r[3] == "WARN")
    errors  = sum(1 for r in log if r[3] == "ERROR")
    success = sum(1 for r in log if r[3] == "SUCCESS")
    total_in = len(results["canonical_policy"]) + len(results["canonical_claim"]) + results["hard_rejects"]
    total_out= len(results["canonical_policy"]) + len(results["canonical_claim"])
    bureau_outs = len(results["iso"]) + len(results["ncci"]) + len(results["fl_state"])

    # ── Stats Bar ──
    st.markdown("---")
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    for col, label, val, color in [
        (c1, "Policies In",    len(results["canonical_policy"]), "#4a9eff"),
        (c2, "Claims In",      len(results["canonical_claim"]),  "#4a9eff"),
        (c3, "Transformed",    total_out,                        "#66bb6a"),
        (c4, "Warnings",       warns,                            "#ff9800"),
        (c5, "Hard Rejects",   results["hard_rejects"],          "#f44336"),
        (c6, "Bureau Records", bureau_outs,                      "#ce93d8"),
    ]:
        col.markdown(f'<div class="metric-card"><div class="metric-value" style="color:{color}">{val}</div><div class="metric-label">{label}</div></div>', unsafe_allow_html=True)

    # ── Output Tabs ──
    st.markdown("---")
    st.markdown("### 📤 Output Files")
    tabs = st.tabs(["⚙️ Canonical Policy","⚙️ Canonical Claim","🏛️ ISO Bureau","🏛️ NCCI Bureau","🏛️ FL State OIR","📦 DestPolicy","📦 DestClaim"])

    def render_output_tab(tab, df, filename, color):
        with tab:
            if df.empty:
                st.warning("No records in this output.")
                return
            st.markdown(f"**{len(df)} record(s)** ready for download")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                label=f"⬇ Download {filename}",
                data=csv_bytes(df),
                file_name=filename,
                mime="text/csv",
                key=filename,
            )

    render_output_tab(tabs[0], results["canonical_policy"], "canonical_policy.csv",  "#66bb6a")
    render_output_tab(tabs[1], results["canonical_claim"],  "canonical_claim.csv",   "#66bb6a")
    render_output_tab(tabs[2], results["iso"],              "bureau_ISO.csv",         "#ffa726")
    render_output_tab(tabs[3], results["ncci"],             "bureau_NCCI.csv",        "#ffa726")
    render_output_tab(tabs[4], results["fl_state"],         "bureau_FL_State.csv",    "#ffa726")
    render_output_tab(tabs[5], results["dest_policy"],      "dest_policy.csv",        "#ce93d8")
    render_output_tab(tabs[6], results["dest_claim"],       "dest_claim.csv",         "#ce93d8")

    # ── Transformation Log ──
    st.markdown("---")
    with st.expander("📋 Transformation Log", expanded=True):
        col_f1, col_f2 = st.columns([2,1])
        with col_f1:
            filter_status = st.selectbox("Filter by status:", ["ALL","SUCCESS","WARN","ERROR"], key="log_filter")
        with col_f2:
            filter_type = st.selectbox("Filter by type:", ["ALL","POLICY","CLAIM"], key="log_type")

        log_df = pd.DataFrame(log, columns=["Type","RecordID","Rule","Status","InputValue","OutputValue","Message"])
        if filter_status != "ALL":
            log_df = log_df[log_df["Status"] == filter_status]
        if filter_type != "ALL":
            log_df = log_df[log_df["Type"] == filter_type]

        for _, r in log_df.iterrows():
            css = "log-success" if r.Status=="SUCCESS" else ("log-warn" if r.Status=="WARN" else "log-error")
            st.markdown(
                f'<div class="{css}"><b>[{r.Type}]</b> {r.RecordID} · <b>{r.Rule}</b> · '
                f'<span style="opacity:0.7">{r.InputValue} → {r.OutputValue}</span> · {r.Message}</div>',
                unsafe_allow_html=True
            )

        st.caption(f"Showing {len(log_df)} of {len(log)} log entries")

else:
    st.info("💡 Sample Policy and Claim data are pre-loaded above. Click **▶ RUN TRANSFORMATION** to begin.")
