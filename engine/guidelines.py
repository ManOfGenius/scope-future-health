"""
BAYT guideline knowledge base.

Every rule is machine-readable, versioned and traceable to its source document.
Rules decide *eligibility and due dates* (the approved guideline layer).
The ML layer only *prioritises* among people the rules already make eligible,
or flags risk-based pathways that guidelines explicitly allow (cascade testing,
earlier CBC, BP <3y in high-risk conditions). It never overrides a guideline.

Sources (retrieved Nov 2026):
  WCV  = DoH/ADPHC Standard for Well-Child Visits, DOH/WCV/SD/10/2025 v10 (Dec 2025)
  IFHAS = DoH Periodic Comprehensive Screening Program (IFHAS), 2025 update,
          as published by ADPHC and participating providers
  LDCT = ADPHC lung cancer screening programme (55-75, cigarette/shisha/medwakh)
  GEN  = Emirati Genome Programme: premarital carrier screening (570+ genes),
          Newborn Genetic Screening Programme (800+ treatable conditions)
"""

GUIDELINE_VERSION = "SCOPE-KB 1.0 (2026-11-05)"

# ---------------------------------------------------------------- children
# WCV visit ages in months (WCV §Appendix 1)
WCV_AGES_MONTHS = [1, 2, 4, 6, 9, 12, 15, 18, 24, 30, 36, 48, 60, 72]

# Window: a visit is "due" from its age until the next scheduled age,
# "overdue" after a grace period (months) beyond its nominal age.
WCV_GRACE_MONTHS = {1: 1, 2: 1, 4: 1, 6: 2, 9: 2, 12: 2, 15: 2, 18: 3,
                    24: 3, 30: 4, 36: 6, 48: 6, 60: 6, 72: 6}

CHILD_RULES = [
    {
        "id": "WCV-MCHAT-18", "pathway": "Well-Child Visit", "item": "M-CHAT-R autism screen (18 m)",
        "age_from_m": 18, "age_to_m": 24, "source": "WCV §3 Development; KPI 8 (target 100%)",
        "followup": "Score 3-7: neurodevelopment + speech referral within 4 weeks; 8-20: within 2 weeks",
    },
    {
        "id": "WCV-MCHAT-24", "pathway": "Well-Child Visit", "item": "M-CHAT-R autism screen (24 m)",
        "age_from_m": 24, "age_to_m": 30, "source": "WCV §3 Development; KPI 12 (target 100%)",
        "followup": "As above; low-risk at 24 m needs no further screen unless indicated",
    },
    {
        "id": "WCV-CBC-12", "pathway": "Well-Child Visit", "item": "CBC / haemoglobin (12 m, else 15-18 m)",
        "age_from_m": 12, "age_to_m": 24, "source": "WCV §3 Anaemia",
        "followup": "Hb < 11 g/dL in under-6s requires etiologic evaluation",
        "risk_earlier": "Earlier CBC allowed with risk factors: inherited blood disorder, chronic illness, rapid growth, unfortified formula",
    },
    {
        "id": "WCV-HEAR", "pathway": "Well-Child Visit", "item": "Pure-tone audiometry (4, 5, 6 y)",
        "age_from_m": 48, "age_to_m": 84, "source": "WCV §3.3 Hearing",
        "followup": "Abnormal: follow-up within 7 days, specialist within 2-4 weeks",
    },
    {
        "id": "WCV-VISION3", "pathway": "Well-Child Visit", "item": "Snellen + auto-refraction + fundus (from 3 y)",
        "age_from_m": 36, "age_to_m": 84, "source": "WCV §3.4 Vision",
        "followup": "Immediate ophthalmology referral for red-flag findings or family history of retinoblastoma/cataract/glaucoma",
    },
    {
        "id": "WCV-BP", "pathway": "Well-Child Visit", "item": "Blood pressure (3-6 y; <3 y only if high-risk)",
        "age_from_m": 36, "age_to_m": 84, "source": "WCV §3 Blood pressure",
        "followup": "High-risk <3 y: CKD, diabetes, obesity, prematurity, OSA, repaired coarctation",
    },
    {
        "id": "WCV-ORAL", "pathway": "Well-Child Visit", "item": "Dentist / hygienist oral screen",
        "age_from_m": 12, "age_to_m": 84, "source": "WCV §3 Oral health",
        "followup": "Caries-risk assessment and preventive referral",
    },
]

# ---------------------------------------------------------------- adults
# IFHAS: Thiqa holders 18-75, package every 3 years unless stated.
IFHAS_ELIGIBLE_AGE = (18, 75)
IFHAS_CYCLE_YEARS = 3

ADULT_RULES = [
    {"id": "IF-CORE", "item": "IFHAS core package (BP, BMI, HbA1c, lipids, kidney, CBC, PHQ-9/GAD-7)",
     "sex": "any", "age": (18, 75), "interval_y": 3, "source": "IFHAS all ages"},
    {"id": "IF-CRC", "item": "Colorectal screen (FIT yearly or colonoscopy 10-yearly)",
     "sex": "any", "age": (40, 75), "interval_y": 1, "source": "IFHAS 40-75",
     "risk_note": "First-degree relative with colorectal cancer or Lynch variant: refer for colonoscopy pathway"},
    {"id": "IF-MAMMO", "item": "Mammogram", "sex": "F", "age": (40, 75), "interval_y": 2,
     "source": "IFHAS women 40-75",
     "risk_note": "BRCA1/2 or strong family history: genetic counselling + high-risk breast pathway"},
    {"id": "IF-CERV", "item": "Cervical screen (Pap 25-39 / HPV 5-yearly)", "sex": "F", "age": (25, 75),
     "interval_y": 3, "source": "IFHAS women 25-75; DoH Cervical Standard v2 2025"},
    {"id": "IF-FUNDUS", "item": "Dilated fundus exam", "sex": "any", "age": (40, 75), "interval_y": 1,
     "source": "IFHAS 40-75"},
    {"id": "IF-DEXA", "item": "Osteoporosis screen (DEXA)", "sex": "any", "age": (40, 75), "interval_y": 2,
     "source": "IFHAS 40-75"},
    {"id": "IF-MOCA", "item": "Memory screen (MoCA)", "sex": "any", "age": (50, 75), "interval_y": 3,
     "source": "IFHAS 2025 update (from 50)"},
    {"id": "LDCT", "item": "Low-dose CT lung screen", "sex": "any", "age": (55, 75), "interval_y": 1,
     "requires": "tobacco", "source": "ADPHC lung screening (cigarette, shisha, medwakh exposure)"},
]

# Risk-based preventive pathways the KB allows to be triggered by data, not age
RISK_PATHWAYS = [
    {"id": "CASCADE-FH", "item": "Cascade testing: lipid profile + genetic counselling (familial hypercholesterolaemia)",
     "trigger": "first-degree relative carries a consented pathogenic LDLR/APOB/PCSK9 variant",
     "source": "International FH cascade-screening consensus; GEN data"},
    {"id": "CASCADE-HBOC", "item": "Genetic counselling referral (hereditary breast/ovarian cancer)",
     "trigger": "first-degree relative carries a consented BRCA1/2 variant",
     "source": "GEN data; IFHAS Gail risk assessment"},
    {"id": "CASCADE-LYNCH", "item": "Genetic counselling + early colonoscopy pathway (Lynch syndrome)",
     "trigger": "first-degree relative carries a consented MMR-gene variant",
     "source": "GEN data"},
    {"id": "EARLY-CBC", "item": "Earlier CBC (from 9 m)",
     "trigger": "child of two carriers of a haemoglobin disorder, or carrier child with anaemia risk",
     "source": "WCV §3 Anaemia risk factors"},
    {"id": "DPP", "item": "Diabetes prevention programme referral",
     "trigger": "ML cardiometabolic risk in top decile among adults without diabetes, confirmed by HbA1c",
     "source": "IFHAS core HbA1c; population prioritisation only"},
    {"id": "DEV-PRIORITY", "item": "Priority developmental surveillance at next WCV",
     "trigger": "prematurity, consanguinity with family history of developmental disorder, or missed M-CHAT",
     "source": "WCV §3 Development"},
]

# Cultural calendar used by the timing engine (approximate; confirm with official announcement)
CALENDAR_2026_27 = [
    {"name": "UAE National Day holiday", "start": "2026-12-01", "end": "2026-12-03", "rule": "avoid"},
    {"name": "School winter break", "start": "2026-12-14", "end": "2027-01-03", "rule": "family-friendly"},
    {"name": "Ramadan (est.)", "start": "2027-02-08", "end": "2027-03-09", "rule": "evening-only (after iftar)"},
    {"name": "Eid al-Fitr (est.)", "start": "2027-03-10", "end": "2027-03-12", "rule": "avoid"},
    {"name": "Post-Eid relaunch", "start": "2027-03-14", "end": "2027-03-31", "rule": "boost"},
]

SMALL_CELL_THRESHOLD = 11  # suppress any reported cell with n < 11

# ---------------------------------------------------------------- immunisation
# DoH Circular 2026/77 (14 May 2026), Appendix 1 Immunization Schedule (updated April 2026).
# School grades mapped to typical ages: Grade 1 ~6 y, Grade 5 ~10 y, Grade 8 ~13 y, Grade 11 ~16 y.
VAX_SOURCE = "DoH Circular 2026/77, Immunization Schedule (Apr 2026)"
VAX_SCHEDULE = [
    {"id": "VAX-2M",  "due_m": 2,   "label": "2-month vaccines",  "vaccines": "Hexavalent, PCV20, rotavirus"},
    {"id": "VAX-4M",  "due_m": 4,   "label": "4-month vaccines",  "vaccines": "Hexavalent, PCV20, rotavirus"},
    {"id": "VAX-6M",  "due_m": 6,   "label": "6-month vaccines",  "vaccines": "Hexavalent, bOPV"},
    {"id": "VAX-12M", "due_m": 12,  "label": "12-month vaccines", "vaccines": "MMR, varicella, MCV4 dose 1"},
    {"id": "VAX-18M", "due_m": 18,  "label": "18-month vaccines", "vaccines": "DTaP-Hib-IPV, bOPV, PCV20 booster, MMR"},
    {"id": "VAX-G1",  "due_m": 72,  "label": "School entry vaccines (Grade 1)", "vaccines": "DTaP-IPV, bOPV, varicella"},
    {"id": "VAX-G5",  "due_m": 120, "label": "Grade 5 vaccine", "vaccines": "MCV4 dose 2"},
    {"id": "VAX-G8",  "due_m": 156, "label": "HPV vaccine (Grade 8)", "vaccines": "HPV9, 2 doses under 15 y"},
    {"id": "VAX-G11", "due_m": 192, "label": "Grade 11 vaccines", "vaccines": "Tdap, MCV4 dose 3"},
]
VAX_GRACE_M = {2: 1, 4: 1, 6: 1, 12: 2, 18: 2, 72: 6, 120: 6, 156: 6, 192: 6}

# ---------------------------------------------------------------- school age 7-17
# UAE National School Health Screening Guideline 2024: annual examination KG-Grade 12
# (growth/BMI, vision, hearing, scoliosis, dental, mental and behavioural health, vaccination review;
# smoking enquiry over 10 years).
SCHOOL_SOURCE = "UAE National School Health Screening Guideline 2024 (annual, KG to Grade 12)"

# ---------------------------------------------------------------- published anchors
ANCHORS = {
    "diabetes_prevalence_20_79": {"value": 0.207, "source": "IDF Diabetes Atlas 2024, UAE, age-adjusted 20-79"},
    "diabetes_undiagnosed_share": {"value": 0.64, "source": "IDF Diabetes Atlas 2024, UAE"},
    "diabetes_cost_per_person_usd": {"value": 1583.5, "source": "IDF Diabetes Atlas 2024, UAE, per person with diabetes"},
}

# ---------------------------------------------------------------- visit purposes (predictive goal of the visit)
# Each open item maps to one purpose. The purpose decides which clinician role sees the person,
# how long the slot is, and which structured protocol the clinician fills in.
PURPOSES = {
    "DEV": {"label": "Developmental surveillance", "role": "Paediatrician", "minutes": 30, "weight": 6,
            "why": "Early identification of developmental and autism-spectrum concerns (WCV §3, M-CHAT-R at 18 and 24 m)"},
    "ANA": {"label": "Anaemia and haemoglobin risk", "role": "Paediatrician", "minutes": 15, "weight": 5,
            "why": "Hb below 11 g/dL needs etiologic evaluation; inherited haemoglobin disorders in the family"},
    "GEN": {"label": "Familial genetic risk", "role": "Family physician", "minutes": 20, "weight": 5,
            "why": "First-degree relative carries a consented pathogenic variant; index-mediated cascade"},
    "CMR": {"label": "Cardiometabolic prevention", "role": "Family physician", "minutes": 30, "weight": 4,
            "why": "IFHAS core package; calibrated 3-year cardiometabolic risk; undiagnosed diabetes"},
    "CAN": {"label": "Cancer screening", "role": "Family physician", "minutes": 15, "weight": 3,
            "why": "IFHAS colorectal, breast and cervical screening; ADPHC lung screening"},
    "WCV": {"label": "Routine Well-Child Visit", "role": "Paediatrician", "minutes": 20, "weight": 3,
            "why": "WCV schedule: growth, vision, hearing, blood pressure, oral health, anticipatory guidance"},
    "IMM": {"label": "Immunisation catch-up", "role": "Nurse", "minutes": 10, "weight": 3,
            "why": "DoH immunisation schedule (Circular 2026/77)"},
    "SCH": {"label": "School-age health check", "role": "Nurse", "minutes": 15, "weight": 1,
            "why": "National School Health Screening Guideline 2024"},
    "COM": {"label": "Community health check", "role": "Nurse", "minutes": 15, "weight": 1,
            "why": "No funded comprehensive screening pathway; blood pressure and glucose check"},
}
RULE_PURPOSE = {
    "WCV-MCHAT-18": "DEV", "WCV-MCHAT-24": "DEV", "WCV-MCHAT-REF": "DEV", "DEV-PRIORITY": "DEV",
    "WCV-CBC-12": "ANA", "EARLY-CBC": "ANA",
    "CASCADE-FH": "GEN", "CASCADE-HBOC": "GEN", "CASCADE-LYNCH": "GEN",
    "IF-CORE": "CMR", "DPP": "CMR", "IF-FUNDUS": "CMR", "IF-DEXA": "CMR", "IF-MOCA": "CMR",
    "IF-CRC": "CAN", "IF-MAMMO": "CAN", "IF-CERV": "CAN", "LDCT": "CAN",
    "WCV-VISIT": "WCV", "WCV-HEAR": "WCV", "WCV-VISION3": "WCV", "WCV-BP": "WCV", "WCV-ORAL": "WCV",
    "VAX": "IMM", "SCH-ANNUAL": "SCH", "PATHWAY-GAP": "COM",
}
ROLE_RANK = {"Nurse": 0, "Family physician": 1, "Paediatrician": 1}

# Family Health Day sessions (local time). A share of each session is reserved for S.C.O.P.E bookings.
SESSIONS = {
    "weekday_morning": {"days": [0, 2], "start": "09:00", "end": "12:00"},     # Mon, Wed
    "weekday_evening": {"days": [1, 3], "start": "16:00", "end": "20:00"},     # Tue, Thu
    "friday_afternoon": {"days": [4], "start": "14:30", "end": "18:00"},
    "saturday_morning": {"days": [5], "start": "09:00", "end": "13:00"},        # Saturday clinics only
    "ramadan_evening": {"days": [0, 1, 2, 3, 4], "start": "20:30", "end": "23:00"},
}
FHD_SHARE = 0.5   # share of each session's minutes that S.C.O.P.E may book
