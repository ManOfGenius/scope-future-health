"""
Synthetic Abu Dhabi population for BAYT.

No real data is used. Structure and rates are plausible orders of magnitude for
demonstration only (see ASSUMPTIONS in docs). Ground-truth outcomes are drawn
from a hidden data-generating process so the engine can be evaluated honestly
(sensitivity, false positives/negatives, calibration, uptake).
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

import json, math
import numpy as np
from datetime import date, timedelta

TODAY = date(2026, 11, 5)
rng = np.random.default_rng(2026)

def sig(x): return 1 / (1 + math.exp(-x))

REGIONS = {
    "Abu Dhabi City": {"w": 0.55, "districts": ["Khalifa City", "Mohammed Bin Zayed City", "Al Reem", "Musaffah", "Al Shamkha", "Al Bateen"], "dist": (3, 12)},
    "Al Ain": {"w": 0.33, "districts": ["Al Jimi", "Al Muwaiji", "Al Hili", "Zakher", "Al Towayya"], "dist": (3, 15)},
    "Al Dhafra": {"w": 0.12, "districts": ["Madinat Zayed", "Ruwais", "Ghayathi", "Liwa", "Delma"], "dist": (8, 60)},
}

# nationality group -> household mix, language distribution, insurance
GROUPS = {
    "Emirati":      {"w": 0.36, "lang": {"Arabic": 0.92, "English": 0.08}, "ins": "Thiqa"},
    "Arab expat":   {"w": 0.14, "lang": {"Arabic": 0.95, "English": 0.05}, "ins": "Enhanced"},
    "South Asian":  {"w": 0.30, "lang": {"Urdu": 0.30, "Hindi": 0.18, "Malayalam": 0.27, "Bengali": 0.12, "English": 0.13}, "ins": "Basic"},
    "Filipino":     {"w": 0.10, "lang": {"Tagalog": 0.55, "English": 0.45}, "ins": "Basic"},
    "Western/other":{"w": 0.10, "lang": {"English": 1.0}, "ins": "Enhanced"},
}

ARAB_M = ["Ahmed", "Mohammed", "Khalid", "Saeed", "Rashid", "Hamdan", "Sultan", "Obaid", "Saif", "Hamad", "Zayed", "Majid", "Faisal", "Omar", "Yousef"]
ARAB_F = ["Fatima", "Maryam", "Aisha", "Shamma", "Hessa", "Moza", "Noura", "Latifa", "Alia", "Salama", "Meera", "Reem", "Amna", "Hind", "Sara"]
ARAB_FAM = ["Al Mansouri", "Al Dhaheri", "Al Ketbi", "Al Shamsi", "Al Nuaimi", "Al Hammadi", "Al Kaabi", "Al Mazrouei", "Al Ameri", "Al Falasi", "Al Qubaisi", "Al Hosani", "Al Marzooqi", "Al Romaithi"]
EXPAT_ARAB_FAM = ["Haddad", "Khoury", "Mansour", "Saleh", "Nasser", "Hamdi", "Barakat", "Aziz"]
SA_M = ["Imran", "Rahul", "Arjun", "Faisal", "Anil", "Bilal", "Suresh", "Rafiq", "Vijay", "Hassan", "Rajesh", "Tariq"]
SA_F = ["Ayesha", "Priya", "Anjali", "Sana", "Lakshmi", "Nadia", "Divya", "Farah", "Meena", "Zainab"]
SA_FAM = ["Khan", "Sharma", "Nair", "Menon", "Hussain", "Patel", "Rahman", "Pillai", "Qureshi", "Iyer", "Chowdhury", "Ahmed"]
FIL_M = ["Jose", "Mark", "John Paul", "Carlo", "Miguel", "Ramon"]
FIL_F = ["Maria", "Grace", "Joy", "Angelica", "Kristine", "Rowena"]
FIL_FAM = ["Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Dela Cruz"]
W_M = ["James", "Daniel", "Thomas", "Lucas", "Oliver", "Pierre"]
W_F = ["Emma", "Sophie", "Claire", "Olivia", "Anna", "Laura"]
W_FAM = ["Smith", "Martin", "Dubois", "Müller", "Brown", "Rossi", "Wilson"]

def pick(d):
    keys = list(d.keys()); w = np.array([d[k] if not isinstance(d[k], dict) else d[k]["w"] for k in keys], float)
    return keys[rng.choice(len(keys), p=w / w.sum())]

LANG_NAMES = {
    "Urdu":      (["Imran", "Bilal", "Faisal", "Tariq", "Hassan", "Usman", "Zain", "Ahsan", "Rizwan", "Kamran"],
                  ["Ayesha", "Sana", "Farah", "Zainab", "Hira", "Mahnoor", "Amna", "Iqra", "Saima", "Nida"],
                  ["Khan", "Qureshi", "Hussain", "Malik", "Butt", "Siddiqui", "Sheikh"]),
    "Bengali":   (["Rafiq", "Karim", "Habib", "Tanvir", "Sohel", "Arif"], ["Nasrin", "Shirin", "Taslima", "Rumana", "Farzana", "Sumaiya"],
                  ["Rahman", "Chowdhury", "Islam", "Hossain", "Ahmed"]),
    "Hindi":     (["Rahul", "Arjun", "Rajesh", "Vijay", "Amit", "Rohan", "Karan", "Sanjay", "Vikram", "Aarav"],
                  ["Priya", "Anjali", "Divya", "Meena", "Pooja", "Neha", "Kavya", "Ananya", "Riya", "Sunita"],
                  ["Sharma", "Patel", "Gupta", "Verma", "Singh", "Joshi"]),
    "Malayalam": (["Anil", "Suresh", "Joseph", "Thomas", "Vishnu", "Arun", "Biju", "Shaji", "Abin", "Jithin"],
                  ["Lakshmi", "Divya", "Mary", "Sneha", "Anjana", "Reshma", "Aleena", "Gopika", "Sreya", "Neethu"],
                  ["Nair", "Menon", "Pillai", "Kurian", "Varghese", "Iyer", "Thomas"]),
}

def names_for(group, sex, lang=None):
    if group == "South Asian" and lang in LANG_NAMES:
        return rng.choice(LANG_NAMES[lang][0 if sex == "M" else 1])
    if group == "Emirati": return rng.choice(ARAB_M if sex == "M" else ARAB_F)
    if group == "Arab expat": return rng.choice(ARAB_M if sex == "M" else ARAB_F)
    if group == "South Asian": return rng.choice(SA_M if sex == "M" else SA_F)
    if group == "Filipino": return rng.choice(FIL_M if sex == "M" else FIL_F)
    return rng.choice(W_M if sex == "M" else W_F)

def family_name(group, lang=None):
    if group == "South Asian" and lang in LANG_NAMES: return LANG_NAMES[lang][2]
    return {"Emirati": ARAB_FAM, "Arab expat": EXPAT_ARAB_FAM, "South Asian": SA_FAM,
            "Filipino": FIL_FAM, "Western/other": W_FAM}[group]

def dob_from_age_years(age):
    days = int(age * 365.25 + rng.integers(0, 365))
    return TODAY - timedelta(days=days)

def age_years(dob): return (TODAY - dob).days / 365.25

VARIANT_BASE = {  # founder carrier probability per group
    "HBB":   {"Emirati": 0.10, "Arab expat": 0.05, "South Asian": 0.045, "Filipino": 0.02, "Western/other": 0.01},
    "FH":    {"Emirati": 0.012, "Arab expat": 0.005, "South Asian": 0.005, "Filipino": 0.004, "Western/other": 0.004},
    "BRCA":  {"Emirati": 0.008, "Arab expat": 0.004, "South Asian": 0.004, "Filipino": 0.003, "Western/other": 0.004},
    "LYNCH": {"Emirati": 0.007, "Arab expat": 0.003, "South Asian": 0.003, "Filipino": 0.003, "Western/other": 0.003},
}

people, households, families = [], [], []
pindex_tmp = {}
pid = 0

def new_person(hh, fam, group, sex, age, role, mother=None, father=None, inherit=None):
    global pid
    pid += 1
    p = {"id": f"P{pid:05d}", "hh": hh["id"], "fam": fam, "group": group, "sex": sex,
         "dob": dob_from_age_years(age), "role": role, "mother": mother, "father": father,
         "first": None, "last": hh["surname"], "variants": {}}
    used = {pindex_tmp[m]["first"] for m in hh["members"]}
    nl = hh.get("name_lang")
    for _ in range(30):
        nm = str(names_for(group, sex, nl))
        if nm not in used: break
    p["first"] = nm
    pindex_tmp[p["id"]] = p
    for v, base in VARIANT_BASE.items():
        if inherit is None:
            p["variants"][v] = bool(rng.random() < base[group])
        else:
            m, f = inherit
            pm = 0.5 if (m and m["variants"].get(v)) else 0.0
            pf = 0.5 if (f and f["variants"].get(v)) else 0.0
            p["variants"][v] = bool(rng.random() < 1 - (1 - pm) * (1 - pf) + 0.0005)
    people.append(p)
    hh["members"].append(p["id"])
    return p

N_HH = 1350
for h in range(N_HH):
    group = pick(GROUPS)
    region = pick(REGIONS)
    rconf = REGIONS[region]
    # labour accommodation single workers (mostly South Asian men), 13% of households
    single_worker = group in ("South Asian", "Filipino") and rng.random() < 0.28
    if group == "South Asian" and region == "Al Dhafra": single_worker = rng.random() < 0.6
    lang = pick(GROUPS[group]["lang"])
    hh = {"id": f"H{h+1:04d}", "group": group, "region": region,
          "district": str(rng.choice(rconf["districts"])),
          "dist_km": round(float(rng.uniform(*rconf["dist"]) * (1.6 if single_worker else 1.0)), 1),
          "lang": lang, "insurance": GROUPS[group]["ins"],
          "housing": "labour accommodation" if single_worker else ("villa" if group == "Emirati" and rng.random() < 0.75 else "apartment"),
          "surname": str(rng.choice(family_name(group, lang if lang != "English" else str(rng.choice(["Urdu", "Hindi", "Malayalam"]))))), "members": [],
          "engagement": float(rng.normal(0.25 if group == "Emirati" else 0.0, 0.9)),
          "digital": float(np.clip(rng.normal(0.75 if group in ("Emirati", "Western/other") else 0.55, 0.2), 0.05, 1)),
          "shift_work": bool(single_worker or rng.random() < 0.15),
          "consang": bool(group == "Emirati" and rng.random() < 0.40) or bool(group in ("Arab expat", "South Asian") and rng.random() < 0.15),
          }
    if single_worker:
        hh["insurance"] = "Basic"
    hh["name_lang"] = lang if lang in LANG_NAMES else ({"Khan": "Urdu", "Qureshi": "Urdu", "Hussain": "Urdu", "Malik": "Urdu", "Butt": "Urdu", "Siddiqui": "Urdu", "Sheikh": "Urdu",
        "Sharma": "Hindi", "Patel": "Hindi", "Gupta": "Hindi", "Verma": "Hindi", "Singh": "Hindi", "Joshi": "Hindi"}.get(hh["surname"], "Malayalam") if group == "South Asian" else None)
    fam = f"F{h+1:04d}"
    households.append(hh)

    if single_worker:
        new_person(hh, fam, group, "M", float(rng.uniform(24, 56)), "self")
        continue

    father_age = float(rng.uniform(26, 62)); mother_age = max(20.0, father_age - float(rng.uniform(0, 8)))
    father = new_person(hh, fam, group, "M", father_age, "father")
    mother = new_person(hh, fam, group, "F", mother_age, "mother")
    # Emirati multigenerational: grandparent co-resident
    if group == "Emirati" and rng.random() < 0.38:
        gsex = "F" if rng.random() < 0.6 else "M"
        g = new_person(hh, fam, group, gsex, float(min(88, father_age + rng.uniform(22, 30))), "grandmother" if gsex == "F" else "grandfather")
        father["father" if gsex == "M" else "mother"] = g["id"]
        # father inherits some variants from co-resident grandparent
        for v in g["variants"]:
            if g["variants"][v] and rng.random() < 0.5: father["variants"][v] = True
    # children
    lam = {"Emirati": 3.0, "Arab expat": 2.2, "South Asian": 1.8, "Filipino": 1.3, "Western/other": 1.5}[group]
    n_kids = int(min(7, rng.poisson(lam)))
    for k in range(n_kids):
        max_age = min(mother_age - 19, 17.5)
        if max_age < 0.05: break
        # oversample young children (WCV population) for demo depth
        kid_age = float(rng.uniform(0.05, min(7.5, max_age))) if rng.random() < 0.55 else float(rng.uniform(0.05, max_age))
        sex = "M" if rng.random() < 0.51 else "F"
        c = new_person(hh, fam, group, sex, kid_age, "child", mother["id"], father["id"], inherit=(mother, father))
        c["preterm"] = bool(rng.random() < (0.09 + (0.02 if hh["consang"] else 0)))

pindex = {p["id"]: p for p in people}
import sys
T2D_INTERCEPT = float(sys.argv[1]) if len(sys.argv) > 1 else -3.95

# ------------------------------------------------------------ clinical state
def rand_date_within(years_back_max, years_back_min=0.0):
    d = rng.uniform(years_back_min, years_back_max) * 365.25
    return TODAY - timedelta(days=int(d))

for p in people:
    hh = next(h for h in households if h["id"] == p["hh"]) if False else None
hh_index = {h["id"]: h for h in households}

for p in people:
    hh = hh_index[p["hh"]]
    a = age_years(p["dob"])
    p["age"] = round(a, 2)
    g = p["group"]
    eng = hh["engagement"]
    # language barrier when only Arabic/English outreach exists
    lang_barrier = 0.0 if hh["lang"] in ("Arabic", "English") else 0.7
    dist_pen = 0.015 * hh["dist_km"]
    p["genomic_available"] = bool(
        (g == "Emirati" and rng.random() < (0.85 if a < 1.3 else 0.55)) or (g != "Emirati" and rng.random() < 0.03))
    p["consent"] = {
        "genomic": bool(p["genomic_available"] and rng.random() < 0.86),
        "family_link": bool(rng.random() < 0.9),
        "social": bool(rng.random() < 0.82),
        "outreach": bool(rng.random() < 0.96),
    }
    if a >= 18:
        # adult latent cardiometabolic state
        bmi = float(np.clip(rng.normal({"Emirati": 29, "Arab expat": 28, "South Asian": 26.5, "Filipino": 25.5, "Western/other": 26}[g] + 0.06 * (a - 40), 4.8), 17, 50))
        sa = 1 if g == "South Asian" else 0
        em = 1 if g == "Emirati" else 0
        p["bmi"] = round(bmi, 1)
        p["smoke"] = str(rng.choice(["none", "cigarette", "shisha", "medwakh"],
                                     p=[0.66, 0.2, 0.09, 0.05] if p["sex"] == "M" else [0.9, 0.03, 0.07, 0.0]))
        p["active"] = bool(rng.random() < 0.38)
        p["waist"] = round(float(np.clip((0.9 if p["sex"] == "M" else 0.82) * (bmi * 3.1) + rng.normal(0, 6), 60, 150)), 0)
        p["veg_daily"] = bool(rng.random() < 0.45)
        lt = T2D_INTERCEPT + 0.065 * (a - 18) + 0.11 * (bmi - 25) + 0.6 * sa + 0.45 * em
        p["t2d"] = bool(rng.random() < sig(lt))
        p["htn"] = bool(rng.random() < sig(-5.0 + 0.07 * (a - 18) + 0.08 * (bmi - 25)))
        p["prediab_latent"] = bool((not p["t2d"]) and rng.random() < sig(lt + 1.6))
        # IFHAS attendance history (Thiqa only)
        p_attend = sig(0.3 + eng - lang_barrier - dist_pen - (0.6 if hh["shift_work"] else 0))
        if hh["insurance"] == "Thiqa" and 18 <= a <= 76:
            p["last_ifhas"] = rand_date_within(3.0).isoformat() if rng.random() < p_attend else (
                rand_date_within(7, 3.05).isoformat() if rng.random() < 0.5 else None)
        else:
            p["last_ifhas"] = None
            # some expats get employer health checks
            p["last_employer_check"] = rand_date_within(3).isoformat() if rng.random() < sig(-0.6 + eng) else None
        recent = p["last_ifhas"] and (TODAY - date.fromisoformat(p["last_ifhas"])).days < 3 * 365
        if recent or (p.get("last_employer_check") and rng.random() < 0.4):
            p["hba1c"] = round(float(np.clip(rng.normal(7.8, 1.1) if p["t2d"] else (rng.normal(6.0, 0.2) if p["prediab_latent"] else rng.normal(5.3, 0.25)), 4.5, 12)), 1)
        else:
            p["hba1c"] = None
        # diagnosis status: a recent HbA1c reveals diabetes; otherwise most cases stay undiagnosed
        p["t2d_known"] = bool(p["t2d"] and (p["hba1c"] is not None or rng.random() < 0.08))
        # cancer screening history
        p["last_fit"] = rand_date_within(1.0).isoformat() if (a >= 40 and rng.random() < p_attend * 0.55) else None
        p["last_mammo"] = rand_date_within(2.0).isoformat() if (p["sex"] == "F" and a >= 40 and rng.random() < p_attend * 0.65) else None
        p["last_cerv"] = rand_date_within(3.0).isoformat() if (p["sex"] == "F" and a >= 25 and rng.random() < p_attend * 0.5) else None
        p["last_dexa"] = rand_date_within(2.0).isoformat() if (a >= 40 and rng.random() < p_attend * 0.35) else None
        p["last_fundus"] = rand_date_within(1.0).isoformat() if (a >= 40 and rng.random() < p_attend * 0.4) else None
        p["last_moca"] = rand_date_within(3.0).isoformat() if (a >= 50 and rng.random() < p_attend * 0.4) else None
        p["last_ldct"] = rand_date_within(1.0).isoformat() if (a >= 55 and p["smoke"] != "none" and rng.random() < p_attend * 0.25) else None
        p["noshow_hist"] = int(rng.poisson(max(0.05, 1.2 - eng)))
    else:
        # child developmental and anaemia latent state
        prem = p.get("preterm", False)
        p["formula_unfortified"] = bool(rng.random() < 0.12)
        p["screen_time_high"] = bool(a > 1.5 and rng.random() < 0.35)
        hbb_parents = sum(1 for par in (p["mother"], p["father"]) if par and pindex[par]["variants"]["HBB"])
        p["hbb_parents"] = hbb_parents
        famhx_dev = bool(hh["consang"] and rng.random() < 0.18) or bool(rng.random() < 0.04)
        p["famhx_dev"] = famhx_dev
        p["dev_delay_true"] = bool(rng.random() < sig(-3.1 + 1.0 * prem + 0.7 * hh["consang"] + 1.0 * famhx_dev + 0.35 * (p["sex"] == "M") + 0.3 * p["screen_time_high"]))
        p["anaemia_true"] = bool(rng.random() < sig(-1.9 + 0.7 * p["formula_unfortified"] + 0.5 * prem + 0.4 * (hh["housing"] != "villa") + 0.3 * (hbb_parents > 0)))
        # WCV attendance history
        months = a * 12
        attended = []
        from guidelines import WCV_AGES_MONTHS, WCV_GRACE_MONTHS
        for vm in WCV_AGES_MONTHS:
            if vm + WCV_GRACE_MONTHS[vm] <= months:
                pv = sig(1.6 + eng - lang_barrier - dist_pen - 0.035 * vm - (0.4 if hh["shift_work"] else 0))
                if rng.random() < pv: attended.append(vm)
        p["wcv_attended"] = attended
        p["mchat18"] = None; p["mchat24"] = None
        for vm, key in ((18, "mchat18"), (24, "mchat24")):
            if vm in attended and rng.random() < 0.82:
                p[key] = int(np.clip(rng.normal(7 if p["dev_delay_true"] else 1.2, 2.5 if p["dev_delay_true"] else 1.2), 0, 20))
        p["cbc_done"] = bool(any(v in attended for v in (12, 15, 18)) and rng.random() < 0.7)
        p["hb"] = round(float(rng.normal(10.3, 0.6) if p["anaemia_true"] else rng.normal(12.0, 0.6)), 1) if p["cbc_done"] else None
        p["noshow_hist"] = int(rng.poisson(max(0.05, 1.0 - eng)))
        # immunisation record (national programme: high coverage, lower for HPV and for late school doses)
        from guidelines import VAX_SCHEDULE, VAX_GRACE_M
        missing = []
        for v in VAX_SCHEDULE:
            if v["due_m"] <= months:
                base = 3.2 if v["due_m"] <= 18 else (1.1 if v["id"] == "VAX-G8" else 2.2)
                pv = sig(base + 0.8 * eng - 0.6 * lang_barrier - (0.4 if hh["shift_work"] else 0) - 0.4 * (months - v["due_m"] < 3))
                if rng.random() >= pv: missing.append(v["id"])
        p["vax_missing"] = missing
        # annual school health examination, 7-17 y
        if 7 <= a < 18:
            p["last_school_exam"] = rand_date_within(1.0).isoformat() if rng.random() < sig(1.6 + 0.5 * eng - 0.4 * lang_barrier) else rand_date_within(3, 1.1).isoformat()

# adult incident outcomes (3-year hidden ground truth) -- needs family history
def first_degree(p):
    rel = []
    for k in ("mother", "father"):
        if p.get(k): rel.append(pindex[p[k]])
    for q in people:
        if q.get("mother") == p["id"] or q.get("father") == p["id"]: rel.append(q)
        if p.get("mother") and q["id"] != p["id"] and q.get("mother") == p["mother"]: rel.append(q)
    return rel

children_of = {}
for q in people:
    for k in ("mother", "father"):
        if q.get(k): children_of.setdefault(q[k], []).append(q["id"])
siblings_of = {}
for q in people:
    if q.get("mother"):
        siblings_of.setdefault(q["mother"], []).append(q["id"])

def fdr(p):
    ids = set()
    for k in ("mother", "father"):
        if p.get(k): ids.add(p[k])
    ids.update(children_of.get(p["id"], []))
    if p.get("mother"):
        ids.update(siblings_of.get(p["mother"], []))
    ids.discard(p["id"])
    return [pindex[i] for i in ids]

# family history of T2D: from linked relatives plus self-reported (unlinked) history
for p in people:
    rel = fdr(p)
    linked_t2d = any(r.get("t2d") for r in rel)
    p["famhx_t2d_reported"] = bool(linked_t2d or rng.random() < (0.35 if p["group"] in ("Emirati", "South Asian") else 0.2))
    p["famhx_crc_reported"] = bool(any(r["variants"]["LYNCH"] for r in rel) and rng.random() < 0.6) or bool(rng.random() < 0.03)
    p["famhx_breast_reported"] = bool(any(r["variants"]["BRCA"] for r in rel) and rng.random() < 0.6) or bool(rng.random() < 0.05)

for p in people:
    if p["age"] >= 18:
        a = p["age"]; g = p["group"]
        lt = (-4.3 + 0.045 * (a - 40) + 0.12 * (p["bmi"] - 27) + 0.9 * p["famhx_t2d_reported"] + 1.5 * p["prediab_latent"]
              + 0.45 * p["htn"] + 0.45 * (g == "South Asian") + 0.3 * (g == "Emirati") - 0.35 * p["active"]
              + 0.35 * (p["smoke"] != "none") + 1.2 * p["variants"]["FH"] + 0.6 * p["t2d_known"] + 1.2 * (p["t2d"] and not p["t2d_known"]))
        p["y_cardiomet_3y"] = bool(rng.random() < sig(lt))

# attendance propensity if invited with a *standard* generic SMS (ground truth for uptake simulation)
for p in people:
    hh = hh_index[p["hh"]]
    lang_barrier = 0.0 if hh["lang"] in ("Arabic", "English") else 0.8
    p["_base_logit_attend"] = round(-0.4 + 0.9 * hh["engagement"] - lang_barrier - 0.02 * hh["dist_km"]
                                    - (0.6 if hh["shift_work"] else 0) - 0.15 * p["noshow_hist"]
                                    + (0.3 if p["age"] < 7 else 0) + float(rng.normal(0, 0.3)), 3)

out = {"today": TODAY.isoformat(), "households": households, "people": people}
for p in people:
    p["dob"] = p["dob"].isoformat()
with open(str(ROOT / "data" / "population.json"), "w") as f:
    json.dump(out, f, default=lambda o: bool(o) if isinstance(o, np.bool_) else str(o))

import collections
print("households", len(households), "people", len(people))
print("children <7:", sum(1 for p in people if p["age"] < 7), " adults:", sum(1 for p in people if p["age"] >= 18))
print(collections.Counter(h["group"] for h in households))
print("variant carriers:", {v: sum(p["variants"][v] for p in people) for v in VARIANT_BASE})
ad = [p for p in people if 20 <= p["age"] < 80]
t2 = [p for p in ad if p["t2d"]]
print("T2D prevalence 20-79: %.3f  undiagnosed share: %.3f" % (len(t2) / len(ad), sum(not p["t2d_known"] for p in t2) / max(1, len(t2))))
kids = [p for p in people if p["age"] < 18]
print("children with a missing vaccine: %.3f" % (sum(bool(p["vax_missing"]) for p in kids) / len(kids)))
print("dev delay true:", sum(p.get("dev_delay_true", False) for p in people), " cardiomet 3y:", sum(p.get("y_cardiomet_3y", False) for p in people))
