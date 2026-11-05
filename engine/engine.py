"""
BAYT engine: guideline care-gaps + calibrated, explainable risk prioritisation,
family cascade, uncertainty, equity audit and outcome simulation.
Outputs out/bayt.json consumed by the web app.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

import json, math, collections
from datetime import date, timedelta
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from guidelines import *

rng = np.random.default_rng(7)
D = json.load(open(str(ROOT / "data" / "population.json")))
TODAY = date.fromisoformat(D["today"])
H = {h["id"]: h for h in D["households"]}
P = {p["id"]: p for p in D["people"]}
people = D["people"]
sig = lambda x: 1 / (1 + np.exp(-x))

def days_since(s): return None if not s else (TODAY - date.fromisoformat(s)).days

children_of = collections.defaultdict(list)
for q in people:
    for k in ("mother", "father"):
        if q.get(k): children_of[q[k]].append(q["id"])
def fdr(p):
    ids = set(x for x in (p.get("mother"), p.get("father")) if x)
    ids.update(children_of[p["id"]])
    for par in (p.get("mother"), p.get("father")):
        if par: ids.update(children_of[par])
    ids.discard(p["id"]); return [P[i] for i in ids]

# =========================================================== 1. CARE GAPS (rules)
GAP_WEIGHT = {"VAX": 2.5, "SCH-ANNUAL": 1.0, "WCV-MCHAT-REF": 5.0, "WCV-VISIT": 2.0, "WCV-MCHAT-18": 3.0, "WCV-MCHAT-24": 3.0, "WCV-CBC-12": 2.0, "WCV-HEAR": 1.2,
              "WCV-VISION3": 1.2, "WCV-BP": 0.8, "WCV-ORAL": 0.8, "IF-CORE": 2.0, "IF-CRC": 2.0, "IF-MAMMO": 2.0,
              "IF-CERV": 1.5, "IF-FUNDUS": 0.6, "IF-DEXA": 0.7, "IF-MOCA": 0.7, "LDCT": 2.2,
              "CASCADE-FH": 4.0, "CASCADE-HBOC": 4.0, "CASCADE-LYNCH": 4.0, "EARLY-CBC": 2.0, "DPP": 2.5,
              "DEV-PRIORITY": 2.5, "PATHWAY-GAP": 1.0}

VAXI = {v["id"]: v for v in VAX_SCHEDULE}

def child_gaps(p):
    gaps = []; m = p["age"] * 12
    infant_missing = []
    for vid in p.get("vax_missing", []):
        v = VAXI[vid]; late = m - v["due_m"] - VAX_GRACE_M[v["due_m"]]
        if v["due_m"] <= 18 and m >= 24:
            infant_missing.append(v["label"].replace(" vaccines", "")); continue   # handled as one catch-up review
        vacc = v["vaccines"]
        if m > 8:   # rotavirus is not given after 8 months of age
            vacc = vacc.replace(", rotavirus", "")
        gaps.append({"rule": "VAX", "item": f'{v["label"]}: {vacc}', "status": "overdue" if late > 0 else "due",
                     "days": int(max(0, late) * 30.4), "source": VAX_SOURCE, "vax": vid,
                     "followup": "Catch-up dose at the next visit; record in the immunisation registry"})
    if infant_missing:
        gaps.append({"rule": "VAX", "item": "Catch-up review: infant doses missing (" + ", ".join(infant_missing) + "); give only what the catch-up schedule allows at this age",
                     "status": "overdue", "days": 0, "source": VAX_SOURCE, "vax": "VAX-CATCHUP",
                     "followup": "Catch-up dose at the next visit; record in the immunisation registry"})
    if 84 <= m < 216:
        ds = days_since(p.get("last_school_exam"))
        if ds is None or ds > 365:
            gaps.append({"rule": "SCH-ANNUAL", "item": "Annual school health check: growth, vision, hearing, scoliosis, dental, wellbeing",
                         "status": "overdue", "days": int((ds or 730) - 365), "source": SCHOOL_SOURCE,
                         "followup": "Coordinate with the school nurse; refer abnormal findings to primary care"})
    if m >= 84: return gaps
    att = set(p["wcv_attended"])
    missed = [v for v in WCV_AGES_MONTHS if v + WCV_GRACE_MONTHS[v] <= m and v not in att]
    nxt = next((v for v in WCV_AGES_MONTHS if v > m - 0.01 and v not in att and v + WCV_GRACE_MONTHS[v] > m), None)
    last_missed = missed[-1] if missed else None
    if last_missed is not None and m - last_missed < 14:
        gaps.append({"rule": "WCV-VISIT", "item": f"Well-Child Visit ({fmt_m(last_missed)}) overdue",
                     "status": "overdue", "days": int((m - last_missed - WCV_GRACE_MONTHS[last_missed]) * 30.4),
                     "source": "WCV Appendix 1 schedule"})
    elif nxt is not None and nxt - m <= 2.0:
        gaps.append({"rule": "WCV-VISIT", "item": f"Well-Child Visit ({fmt_m(nxt)}) due",
                     "status": "due", "days": int((nxt - m) * 30.4), "source": "WCV Appendix 1 schedule"})
    for r in CHILD_RULES:
        if not (r["age_from_m"] <= m < r["age_to_m"] + 6): continue
        done = False
        if r["id"] == "WCV-MCHAT-18": done = p["mchat18"] is not None or p["mchat24"] is not None
        elif r["id"] == "WCV-MCHAT-24": done = p["mchat24"] is not None or (m < 24)
        elif r["id"] == "WCV-CBC-12": done = p["cbc_done"]
        elif r["id"] == "WCV-HEAR": done = any(v in att for v in (48, 60, 72) if v <= m) or m < 49
        elif r["id"] == "WCV-VISION3": done = any(v in att for v in (36, 48, 60, 72) if v <= m) or m < 37
        elif r["id"] == "WCV-BP": done = any(v in att for v in (36, 48, 60, 72) if v <= m) or m < 37
        elif r["id"] == "WCV-ORAL": done = any(v in att for v in WCV_AGES_MONTHS if 12 <= v <= m and m - v < 12) or m < 13
        if not done:
            if r["id"] == "WCV-MCHAT-24" and p["mchat18"] is not None and p["mchat18"] <= 2 and m >= 24:
                pass  # rescreen still recommended at 24m after low-risk 18m
            gaps.append({"rule": r["id"], "item": r["item"], "status": "overdue" if m > r["age_from_m"] + 3 else "due",
                         "days": int(((m - r["age_from_m"]) % 12 if r["id"] == "WCV-ORAL" else max(0, m - r["age_from_m"])) * 30.4),
                         "source": r["source"], "followup": r.get("followup")})
    # positive M-CHAT never followed up (simulated: 40% of positives lack referral record)
    score = p["mchat24"] if p["mchat24"] is not None else p["mchat18"]
    if score is not None and score >= 3:
        if (int(p["id"][1:]) * 7 % 10) < 4:
            gaps.append({"rule": "WCV-MCHAT-REF", "item": f"Positive M-CHAT-R (score {score}) — referral not completed",
                         "status": "overdue", "days": 45, "source": "WCV §3 referral timelines",
                         "followup": "Neurodevelopment + speech therapy " + ("within 2 weeks" if score >= 8 else "within 4 weeks")})
    # low Hb not evaluated
    if p.get("hb") is not None and p["hb"] < 11 and (int(p["id"][1:]) % 3 == 0):
        gaps.append({"rule": "WCV-CBC-12", "item": f"Hb {p['hb']} g/dL — etiologic evaluation not recorded",
                     "status": "overdue", "days": 30, "source": "WCV §3 Anaemia (Hb < 11 g/dL)"})
    return gaps

def fmt_m(v): return f"{v} m" if v < 24 else (f"{v//12} y" if v % 12 == 0 else f"{v/12:.1f} y")

def adult_gaps(p):
    gaps = []; a = p["age"]; hh = H[p["hh"]]
    thiqa = hh["insurance"] == "Thiqa"
    if not (18 <= a <= 75): return gaps
    if not thiqa:
        if not p.get("last_employer_check"):
            gaps.append({"rule": "PATHWAY-GAP", "item": "No funded comprehensive screening pathway (non-Thiqa)",
                         "status": "system", "days": 0,
                         "source": "IFHAS eligibility is Thiqa 18-75; route to insurer/employer check or ADPHC community campaign"})
        return gaps
    for r in ADULT_RULES:
        lo, hi = r["age"]
        if not (lo <= a <= hi): continue
        if r["sex"] != "any" and r["sex"] != p["sex"]: continue
        if r.get("requires") == "tobacco" and p["smoke"] == "none": continue
        key = {"IF-CORE": "last_ifhas", "IF-CRC": "last_fit", "IF-MAMMO": "last_mammo", "IF-CERV": "last_cerv",
               "IF-FUNDUS": "last_fundus", "IF-DEXA": "last_dexa", "IF-MOCA": "last_moca", "LDCT": "last_ldct"}[r["id"]]
        ds = days_since(p.get(key)); lim = r["interval_y"] * 365
        if ds is None or ds > lim:
            gaps.append({"rule": r["id"], "item": r["item"], "status": "never" if ds is None else "overdue",
                         "days": 0 if ds is None else int(ds - lim), "source": r["source"], "note": r.get("risk_note")})
    return gaps

for p in people:
    p["gaps"] = child_gaps(p) if p["age"] < 18 else adult_gaps(p)

# =========================================================== 2. RISK MODELS
def adult_features(p, consent=None):
    c = consent or p["consent"]
    hb = p.get("hba1c")
    gen_ok = c["genomic"] and p["genomic_available"]
    return {
        "age_per10": (p["age"] - 40) / 10,
        "bmi_per5": (p["bmi"] - 27) / 5,
        "hypertension": float(p["htn"]),
        "existing_diabetes": float(p["t2d_known"]),
        "family_hx_diabetes": float(p["famhx_t2d_reported"]),
        "hba1c_prediabetes": float(hb is not None and 5.7 <= hb < 6.5),
        "hba1c_missing": float(hb is None),
        "tobacco_any": float(p["smoke"] != "none"),
        "physically_active": float(p["active"]),
        "south_asian_ancestry": float(p["group"] == "South Asian"),
        "fh_variant": float(gen_ok and p["variants"]["FH"]),
        "genomic_not_available": float(not gen_ok),
    }

def child_features(p, consent=None):
    c = consent or p["consent"]; hh = H[p["hh"]]
    m = p["age"] * 12
    mchat = p["mchat24"] if p["mchat24"] is not None else p["mchat18"]
    fam_ok = c["family_link"]
    return {
        "preterm": float(p.get("preterm", False)),
        "male": float(p["sex"] == "M"),
        "consanguinity": float(fam_ok and hh["consang"]),
        "family_hx_developmental": float(fam_ok and p["famhx_dev"]),
        "high_screen_time": float(c["social"] and p["screen_time_high"]),
        "mchat_positive": float(mchat is not None and mchat >= 3),
        "mchat_missing_after_18m": float(mchat is None and m >= 18),
        "family_data_not_shared": float(not fam_ok),
    }

def engage_features(p, consent=None):
    c = consent or p["consent"]; hh = H[p["hh"]]
    soc = c["social"]
    return {
        "non_arabic_english_language": float(hh["lang"] not in ("Arabic", "English")),
        "distance_per10km": hh["dist_km"] / 10 if soc else 0.8,
        "shift_work": float(soc and hh["shift_work"]),
        "prior_no_shows": min(p["noshow_hist"], 4),
        "is_child": float(p["age"] < 7),
        "social_data_not_shared": float(not soc),
    }

def fit_model(rows, y, name, n_boot=30):
    keys = list(rows[0].keys())
    X = np.array([[r[k] for k in keys] for r in rows]); y = np.array(y, int)
    idx = rng.permutation(len(y)); cut = int(0.6 * len(y)); tr, te = idx[:cut], idx[cut:]
    m = LogisticRegression(C=1.0, max_iter=2000).fit(X[tr], y[tr])
    pt = m.predict_proba(X[te])[:, 1]
    boots = []
    for b in range(n_boot):
        bi = rng.choice(tr, len(tr), replace=True)
        if len(set(y[bi])) < 2: continue
        boots.append(LogisticRegression(C=1.0, max_iter=2000).fit(X[bi], y[bi]))
    # calibration deciles on test
    order = np.argsort(pt); bins = np.array_split(order, 10)
    calib = [{"pred": float(pt[b].mean()), "obs": float(y[te][b].mean()), "n": int(len(b))} for b in bins]
    mdl = {"name": name, "features": keys, "coef": [float(c) for c in m.coef_[0]], "intercept": float(m.intercept_[0]),
           "means": [float(v) for v in X[tr].mean(0)],
           "auc_test": float(roc_auc_score(y[te], pt)), "brier_test": float(brier_score_loss(y[te], pt)),
           "prevalence": float(y.mean()), "n_train": int(len(tr)), "n_test": int(len(te)), "calibration": calib,
           "boot_coef": [[float(c) for c in bm.coef_[0]] + [float(bm.intercept_[0])] for bm in boots]}
    print(f"{name}: AUC {mdl['auc_test']:.3f} Brier {mdl['brier_test']:.3f} prev {mdl['prevalence']:.3f}")
    return mdl, te

def predict(mdl, feats, off=0.0):
    x = np.array([feats[k] for k in mdl["features"]])
    z = mdl["intercept"] + off + float(np.dot(mdl["coef"], x))
    bz = [bc[-1] + off + float(np.dot(bc[:-1], x)) for bc in mdl["boot_coef"]]
    bp = sig(np.array(bz))
    contrib = sorted(((k, c * (v - mu)) for k, c, v, mu in zip(mdl["features"], mdl["coef"], x, mdl["means"])),
                     key=lambda t: -abs(t[1]))
    return float(sig(z)), float(np.percentile(bp, 5)), float(np.percentile(bp, 95)), contrib

adults = [p for p in people if p["age"] >= 18]
kids = [p for p in people if 0.5 <= p["age"] < 7]
M_ADULT, te_a = fit_model([adult_features(p) for p in adults], [p["y_cardiomet_3y"] for p in adults], "Cardiometabolic 3-year risk (adults)")
M_CHILD, te_c = fit_model([child_features(p) for p in kids], [p["dev_delay_true"] for p in kids], "Developmental concern risk (children 6 m-7 y)")
# engagement ground truth: one observed response to a past standard invitation
eng_y = [bool(rng.random() < sig(p["_base_logit_attend"])) for p in people]
M_ENG, _ = fit_model([engage_features(p) for p in people], eng_y, "Attendance after standard invite (all)")
test_ids_adult = set(adults[i]["id"] for i in te_a); test_ids_child = set(kids[i]["id"] for i in te_c)

# ---------- per-segment recalibration (calibration-in-the-large), fitted on the training fold only
def logit(q): q = min(max(q, 1e-4), 1 - 1e-4); return math.log(q / (1 - q))
def seg_keys(p):
    hh = H[p["hh"]]
    band = ("Adult 18-39" if p["age"] < 40 else "Adult 40-64" if p["age"] < 65 else "Adult 65+") if p["age"] >= 18 else "Child"
    return {"Life stage": band, "Nationality group": hh["group"], "Region": hh["region"]}
def fit_offsets(mdl, pop, feat_fn, ycol, test_ids, min_n=200, passes=3):
    train = [p for p in pop if p["id"] not in test_ids]
    off = collections.defaultdict(dict)
    base = {p["id"]: mdl["intercept"] + float(np.dot(mdl["coef"], [feat_fn(p)[k] for k in mdl["features"]])) for p in train}
    def tot(p): return sum(off[d].get(v, 0.0) for d, v in seg_keys(p).items())
    for _ in range(passes):
        for d in ("Life stage", "Nationality group", "Region"):
            groups = collections.defaultdict(list)
            for p in train: groups[seg_keys(p)[d]].append(p)
            for v, ps in groups.items():
                if len(ps) < min_n: continue
                obs = np.mean([p[ycol] for p in ps]); pred = np.mean([sig(base[p["id"]] + tot(p)) for p in ps])
                shrink = len(ps) / (len(ps) + 400)   # empirical-Bayes style shrinkage toward zero for small segments
                off[d][v] = float(np.clip(off[d].get(v, 0.0) + shrink * (logit(obs) - logit(pred)), -1.0, 1.0))
    return {d: {k: round(x, 3) for k, x in vv.items()} for d, vv in off.items()}
def seg_offset(mdl, p): return sum(mdl.get("offsets", {}).get(d, {}).get(v, 0.0) for d, v in seg_keys(p).items())

def calib_by_segment(mdl, pop, feat_fn, ycol, test_ids, use_off):
    out = {}
    for d in ("Life stage", "Nationality group", "Region"):
        g = collections.defaultdict(lambda: [0, 0.0, 0])
        for p in pop:
            if p["id"] not in test_ids: continue
            off = seg_offset(mdl, p) if use_off else 0.0
            pr = predict(mdl, feat_fn(p), off)[0]
            k = seg_keys(p)[d]; g[k][0] += 1; g[k][1] += pr; g[k][2] += p[ycol]
        out[d] = {k: (round(v[1] / v[2], 2) if v[2] >= 11 and v[0] >= 30 else None) for k, v in g.items()}
    return out

cal_before = calib_by_segment(M_ADULT, adults, adult_features, "y_cardiomet_3y", test_ids_adult, False)
M_ADULT["offsets"] = fit_offsets(M_ADULT, adults, adult_features, "y_cardiomet_3y", test_ids_adult)
cal_after = calib_by_segment(M_ADULT, adults, adult_features, "y_cardiomet_3y", test_ids_adult, True)
M_CHILD["offsets"] = {}
print("adult offsets:", M_ADULT["offsets"])

# ---------- benchmark against a published, validated score (FINDRISC, Lindström & Tuomilehto 2003)
def findrisc(p):
    a, b, w = p["age"], p["bmi"], p["waist"]
    sc = 0 if a < 45 else 2 if a < 55 else 3 if a < 65 else 4
    sc += 0 if b < 25 else 1 if b <= 30 else 3
    sc += (0 if w < 94 else 3 if w <= 102 else 4) if p["sex"] == "M" else (0 if w < 80 else 3 if w <= 88 else 4)
    sc += 0 if p["active"] else 2
    sc += 0 if p["veg_daily"] else 1
    sc += 2 if p["htn"] else 0
    sc += 5 if (p.get("hba1c") is not None and p["hba1c"] >= 5.7) else 0
    sc += 5 if p["famhx_t2d_reported"] else 0
    return sc
bench = [p for p in adults if p["id"] in test_ids_adult and not p["t2d_known"]]
yb = np.array([p["y_cardiomet_3y"] for p in bench], int)
s_model = np.array([predict(M_ADULT, adult_features(p), seg_offset(M_ADULT, p))[0] for p in bench])
s_find = np.array([findrisc(p) for p in bench], float)
s_age = np.array([p["age"] for p in bench], float)
def top_decile_capture(sc):
    k = max(1, len(sc) // 10); idx = np.argsort(-sc)[:k]; return float(yb[idx].sum() / max(1, yb.sum()))
VALID = {
    "benchmark_population": f"{len(bench)} held-out adults without known diabetes",
    "auc": {"S.C.O.P.E model": round(float(roc_auc_score(yb, s_model)), 3),
            "FINDRISC (published score)": round(float(roc_auc_score(yb, s_find)), 3),
            "Age only (current rule logic)": round(float(roc_auc_score(yb, s_age)), 3)},
    "top_decile_capture": {"S.C.O.P.E model": round(top_decile_capture(s_model), 3),
                           "FINDRISC (published score)": round(top_decile_capture(s_find), 3),
                           "Age only (current rule logic)": round(top_decile_capture(s_age), 3)},
    "calibration_before": cal_before, "calibration_after": cal_after,
}
print("VALID", VALID["auc"], VALID["top_decile_capture"])
print("cal before", cal_before); print("cal after", cal_after)

LABEL = {
    "age_per10": "Age", "bmi_per5": "BMI", "hypertension": "Hypertension", "existing_diabetes": "Known diabetes",
    "family_hx_diabetes": "Family history of diabetes", "hba1c_prediabetes": "HbA1c in prediabetes range",
    "hba1c_missing": "No HbA1c in last 3 years", "tobacco_any": "Tobacco (cigarette/shisha/medwakh)",
    "physically_active": "Physically active", "south_asian_ancestry": "South Asian ancestry (higher risk at lower BMI)",
    "fh_variant": "Consented genomic finding: familial hypercholesterolaemia", "genomic_not_available": "No consented genomic data",
    "preterm": "Born preterm", "male": "Male sex", "consanguinity": "Parental consanguinity",
    "family_hx_developmental": "Family history of developmental disorder", "high_screen_time": "High screen time",
    "mchat_positive": "M-CHAT-R positive", "mchat_missing_after_18m": "M-CHAT-R not done after 18 m",
    "family_data_not_shared": "Family data not shared",
    "non_arabic_english_language": "Preferred language not Arabic/English", "distance_per10km": "Distance to clinic",
    "shift_work": "Shift work", "prior_no_shows": "Previous missed appointments", "is_child": "Child visit",
    "social_data_not_shared": "Social data not shared",
}

# =========================================================== 3. FAMILY CASCADE
for p in people:
    rel = fdr(p)
    for v, rule in (("FH", "CASCADE-FH"), ("BRCA", "CASCADE-HBOC"), ("LYNCH", "CASCADE-LYNCH")):
        idx = [r for r in rel if r["variants"][v] and r["consent"]["genomic"] and r["genomic_available"]
               and r["consent"]["family_link"] and (r["age"] >= 18 or v == "FH")]
        # a child's variant does not trigger cascade to a parent when the other parent is a known carrier
        def explained(r):
            if p["id"] not in (r.get("mother"), r.get("father")): return False
            other = r.get("father") if p["id"] == r.get("mother") else r.get("mother")
            return bool(other and P[other]["variants"][v] and P[other]["consent"]["genomic"] and P[other]["genomic_available"])
        idx = [r for r in idx if not explained(r)]
        if not idx: continue
        if p["age"] > 75: continue
        if p["consent"]["genomic"] and p["genomic_available"]: continue  # already tested
        if v == "BRCA" and p["age"] < 18: continue
        if v == "LYNCH" and p["age"] < 18: continue
        if v == "FH" and p["age"] < 2: continue
        p["gaps"].append({"rule": rule, "item": next(x["item"] for x in RISK_PATHWAYS if x["id"] == rule),
                          "status": "risk-based", "days": 0, "source": "Family cascade (index-mediated, no disclosure of relative's result)",
                          "via": idx[0]["id"]})
    if p["age"] < 2 and p.get("hbb_parents", 0) == 2 and not p.get("cbc_done") and p["age"] * 12 >= 6:
        p["gaps"].append({"rule": "EARLY-CBC", "item": "Earlier CBC (both parents carry a haemoglobin variant)",
                          "status": "risk-based", "days": 0, "source": "WCV §3 Anaemia risk factors"})

# =========================================================== 4. SCORES, UNCERTAINTY, PRIORITY
def completeness(p):
    c = p["consent"]; dom = []
    if p["age"] >= 18:
        dom = [p.get("hba1c") is not None, c["genomic"] and p["genomic_available"], c["family_link"], c["social"],
               bool(p.get("last_ifhas") or p.get("last_employer_check"))]
    else:
        dom = [bool(p["wcv_attended"]), c["genomic"] and p["genomic_available"], c["family_link"], c["social"],
               (p["mchat18"] is not None or p["mchat24"] is not None or p["age"] < 1.5)]
    return sum(dom) / len(dom)

def score_person(p, consent=None):
    res = {}
    if p["age"] >= 18:
        pr, lo, hi, con = predict(M_ADULT, adult_features(p, consent), seg_offset(M_ADULT, p)); res["model"] = "adult"
    elif 0.5 <= p["age"] < 7:
        pr, lo, hi, con = predict(M_CHILD, child_features(p, consent)); res["model"] = "child"
    else:
        return None
    prev = (M_ADULT if res["model"] == "adult" else M_CHILD)["prevalence"]
    res.update({"risk": round(pr, 4), "lo": round(lo, 4), "hi": round(hi, 4), "rr": round(pr / prev, 2),
                "factors": [{"f": LABEL[k], "v": round(v, 3)} for k, v in con[:4] if abs(v) > 0.05]})
    return res

for p in people:
    s = score_person(p)
    pe, _, _, econ = predict(M_ENG, engage_features(p))
    comp = completeness(p)
    p["score"] = s
    p["p_attend"] = round(pe, 3)
    p["barriers"] = [{"f": LABEL[k], "v": round(v, 3)} for k, v in econ[:3] if v < -0.05]
    p["completeness"] = round(comp, 2)
    width = (s["hi"] - s["lo"]) if s else 0
    p["confidence"] = ("insufficient data" if comp < 0.4 else
                       "high" if comp >= 0.8 and width < 0.12 else "medium" if comp >= 0.6 else "low")
    if s and 18 <= p["age"] <= 75 and not p["t2d_known"] and s["rr"] >= 2.2 and p["hh"] and H[p["hh"]]["insurance"] == "Thiqa":
        p["gaps"].append({"rule": "DPP", "item": "Diabetes prevention programme (confirm with HbA1c)",
                          "status": "risk-based", "days": 0, "source": "Population prioritisation — clinician confirms"})
    if s and s["model"] == "child" and s["rr"] >= 2.0 and p["age"] < 6:
        p["gaps"].append({"rule": "DEV-PRIORITY", "item": "Priority developmental surveillance at next WCV",
                          "status": "risk-based", "days": 0, "source": "WCV §3 Development (warning signs, Appendix 6)"})
    need = sum(GAP_WEIGHT[g["rule"]] * (1.3 if g["status"] == "overdue" else 1.0) for g in p["gaps"])
    rr = min(s["rr"], 4) if s else 1.0
    if any(g["rule"].startswith("CASCADE") for g in p["gaps"]): rr = max(rr, 2.5)   # 50% prior of carrying a familial variant
    if any(g["rule"] == "WCV-MCHAT-REF" for g in p["gaps"]): rr = max(rr, 3.0)     # screen-positive, awaiting referral
    # suppress outreach when consent withdrawn
    p["priority"] = 0.0 if not p["consent"]["outreach"] else round(need * (0.5 + 0.5 * rr) * (0.6 + (1 - pe)), 3)
    p["priority_parts"] = {"need": round(need, 2), "risk_mult": round(0.5 + 0.5 * rr, 2), "barrier_mult": round(0.6 + (1 - pe), 2)}

# =========================================================== 5. HOUSEHOLD PLAN + TIMING
CAL = [(date.fromisoformat(c["start"]), date.fromisoformat(c["end"]), c) for c in CALENDAR_2026_27]
def cal_rule(d):
    for s, e, c in CAL:
        if s <= d <= e: return c
    return None

SLOT_LOAD = collections.Counter()
def plan_slot(hh, members):
    has_school = any(5 <= P[m]["age"] < 18 for m in members)
    work = hh["shift_work"] or any(P[m]["role"] in ("father", "mother", "self") and P[m]["age"] < 60 for m in members)
    d = TODAY + timedelta(days=7)
    for _ in range(120):
        c = cal_rule(d); wd = d.weekday()  # Mon=0 .. Sat=5 Sun=6
        ok = True
        if c and c["rule"] == "avoid": ok = False
        if hh["shift_work"] and wd not in (4, 5): ok = False   # Fri afternoon / Sat for workers
        if wd == 6 and not hh["shift_work"]: pass
        if SLOT_LOAD[(hh["region"], d)] >= (3 if hh["region"] == "Al Dhafra" else 6): ok = False
        if ok:
            if c and c["rule"].startswith("evening"): t = "20:30 (after iftar)"
            elif hh["shift_work"]: t = "16:00" if wd == 4 else "10:00"
            elif has_school and not (c and c["rule"] == "family-friendly"): t = "15:30 (after school)"
            elif work: t = "17:00"
            else: t = "10:00"
            why = []
            if c: why.append(c["name"] + " — " + c["rule"])
            if hh["shift_work"]: why.append("shift-work household: weekend slot")
            if has_school: why.append("school-age child: after school hours")
            SLOT_LOAD[(hh["region"], d)] += 1
            return {"date": d.isoformat(), "time": t, "why": why}
        d += timedelta(days=1)
    return None

def contact_person(hh, members):
    roles = {P[m]["role"]: m for m in members}
    if hh["group"] == "Emirati" and ("grandmother" in roles or "grandfather" in roles) and rng.random() < 0.35:
        return roles.get("grandmother") or roles.get("grandfather"), "elder decision-maker"
    if "mother" in roles and any(P[m]["age"] < 18 for m in members): return roles["mother"], "parent"
    if "self" in roles: return roles["self"], "adult"
    return roles.get("father") or members[0], "adult"

def channel(hh, cp):
    p = P[cp]
    if hh["digital"] < 0.4 or p["age"] >= 65: return "WhatsApp voice note"
    if hh["housing"] == "labour accommodation": return "WhatsApp voice note + site visit by mobile clinic"
    return "WhatsApp message" if hh["digital"] < 0.85 else "App notification + WhatsApp"

hh_out = []
for hh in D["households"]:
    mem = hh["members"]
    pr = round(sum(P[m]["priority"] for m in mem), 3)
    gaps_n = sum(len(P[m]["gaps"]) for m in mem)
    cp, aud = contact_person(hh, mem)
    hh_out.append({**{k: hh[k] for k in ("id", "group", "region", "district", "dist_km", "lang", "insurance", "housing", "surname", "consang", "shift_work")},
                   "digital": round(hh["digital"], 2), "members": mem, "priority": pr, "n_gaps": gaps_n,
                   "contact": cp, "audience": aud, "channel": channel(hh, cp),
                   "slot": None})
hh_out.sort(key=lambda h: -h["priority"])
for i, h in enumerate(hh_out): h["rank"] = i + 1

# =========================================================== 6. OUTCOME SIMULATION (Monte Carlo)
# Tailoring effects on log-odds of attendance — explicit, adjustable ASSUMPTIONS
EFFECTS = {"language_concordant": 0.6, "family_bundle_per_extra_member": 0.15, "right_time_channel": 0.25,
           "voice_note_low_literacy": 0.3}
CAPACITY = 600  # people reachable by the outreach team per 90-day cycle (same budget for every strategy)

def model_need(p):
    """Expected need used for equity floors -- model-based, never ground truth."""
    if not p["gaps"] or not p["consent"]["outreach"]: return 0.0
    return p["priority"]

def allocate(equity_floor=0.0, dim=lambda h: h["group"]):
    """Greedy household allocation by priority under a people budget.
    equity_floor in [0,1]: each segment is guaranteed at least floor x its share of model-estimated need."""
    tot = sum(model_need(P[m]) for h in hh_out for m in h["members"]) or 1
    share = collections.Counter()
    for h in hh_out:
        share[dim(h)] += sum(model_need(P[m]) for m in h["members"]) / tot
    quota = {g: equity_floor * CAPACITY * sh for g, sh in share.items()}
    used = collections.Counter(); chosen = []; budget = 0
    cand = [h for h in hh_out if h["n_gaps"] and h["priority"] > 0]
    # pass 1: fill floors
    for g in quota:
        for h in cand:
            if dim(h) != g or h in chosen: continue
            n = sum(1 for m in h["members"] if P[m]["gaps"] and P[m]["consent"]["outreach"])
            if used[g] + n > quota[g] or budget + n > CAPACITY: continue
            chosen.append(h); used[g] += n; budget += n
    # pass 2: pure priority
    for h in cand:
        if h in chosen: continue
        n = sum(1 for m in h["members"] if P[m]["gaps"] and P[m]["consent"]["outreach"])
        if budget + n > CAPACITY: continue
        chosen.append(h); budget += n
    return chosen

ALLOC_PLAIN = allocate(0.0)
ALLOC_EQUITY = allocate(0.8, dim=lambda h: h["group"] + "|" + h["lang"])

def true_high_risk(p):
    if p["age"] >= 18: return p["y_cardiomet_3y"]
    return p.get("dev_delay_true", False) or p.get("anaemia_true", False) and p["age"] < 3

def simulate(strategy, effects_scale=1.0, n_runs=200, alloc=None):
    out = collections.defaultdict(list)
    eligible_people = [p for p in people if p["gaps"] and p["consent"]["outreach"] and
                       not all(g["status"] == "system" for g in p["gaps"])]
    for run in range(n_runs):
        r = np.random.default_rng(1000 + run)
        if strategy == "baseline":
            # age/sex rule: anyone with an age-based item due, contacted individually, random order, generic SMS
            pool = [p for p in eligible_people if any(not g["rule"].startswith(("CASCADE", "DPP", "DEV", "EARLY")) for g in p["gaps"])]
            chosen = [pool[i] for i in r.permutation(len(pool))[:CAPACITY]]
            contacted = [(p, 0.0) for p in chosen]
        else:
            contacted = []
            for h in (alloc if alloc is not None else ALLOC_EQUITY if strategy == "bayt" else ALLOC_PLAIN):
                hh = H[h["id"]]
                mem = [P[m] for m in h["members"] if P[m]["gaps"] and P[m]["consent"]["outreach"]]
                boost = (EFFECTS["language_concordant"] * (hh["lang"] not in ("Arabic", "English"))
                         + EFFECTS["family_bundle_per_extra_member"] * max(0, len(mem) - 1)
                         + EFFECTS["right_time_channel"]
                         + EFFECTS["voice_note_low_literacy"] * (hh["digital"] < 0.4))
                if strategy == "bayt_prioritisation_only": boost = 0.0
                contacted += [(p, boost * effects_scale) for p in mem]
        comp_wcv = comp_adult = hr_reached = cascade = mchat = items = people_n = vax = undx = 0
        lang_minority_reached = 0
        for p, b in contacted:
            people_n += 1
            att = r.random() < sig(p["_base_logit_attend"] + b)
            if not att: continue
            n_items = len([g for g in p["gaps"] if g["status"] != "system"]) if strategy != "baseline" else \
                len([g for g in p["gaps"] if not g["rule"].startswith(("CASCADE", "DPP", "DEV", "EARLY", "PATHWAY"))])
            items += n_items
            if p["age"] < 18: comp_wcv += 1
            else: comp_adult += 1
            if true_high_risk(p): hr_reached += 1
            if strategy != "baseline" and any(g["rule"].startswith("CASCADE") for g in p["gaps"]): cascade += 1
            if any(g["rule"].startswith("WCV-MCHAT") for g in p["gaps"]): mchat += 1
            if H[p["hh"]]["lang"] not in ("Arabic", "English"): lang_minority_reached += 1
            if any(g["rule"] == "VAX" for g in p["gaps"]): vax += 1
            det = ("IF-CORE",) if strategy == "baseline" else ("IF-CORE", "DPP", "PATHWAY-GAP")
            if p["age"] >= 18 and p["t2d"] and not p["t2d_known"] and any(g["rule"] in det for g in p["gaps"]): undx += 1
        for k, v in (("people_contacted", people_n), ("completed_child_visits", comp_wcv), ("completed_adult_screens", comp_adult),
                     ("care_gaps_closed", items), ("true_high_risk_reached", hr_reached), ("cascade_tests", cascade),
                     ("mchat_completed", mchat), ("language_minority_reached", lang_minority_reached),
                     ("vaccines_caught_up", vax), ("undiagnosed_diabetes_found", undx)):
            out[k].append(v)
    return {k: {"mean": round(float(np.mean(v)), 1), "lo": round(float(np.percentile(v, 2.5)), 1),
                "hi": round(float(np.percentile(v, 97.5)), 1)} for k, v in out.items()}

SIM = {"capacity": CAPACITY, "effects": EFFECTS,
       "baseline_age_sex_rules": simulate("baseline"),
       "bayt_prioritisation_only": simulate("bayt_prioritisation_only"),
       "bayt_full": simulate("bayt"),
       "bayt_full_no_equity_floor": simulate("bayt", 1.0, alloc=ALLOC_PLAIN),
       "bayt_full_half_effects": simulate("bayt", 0.5)}
for k in ("baseline_age_sex_rules", "bayt_prioritisation_only", "bayt_full_no_equity_floor", "bayt_full", "bayt_full_half_effects"):
    s = SIM[k]; print(k, {m: s[m]["mean"] for m in s})

# =========================================================== 6b. CLINICS, CLINICIANS, TREATING PHYSICIANS, APPOINTMENTS
srng = np.random.default_rng(42)
CLIN_NAMES = {
    "Arab": (["Ahmed", "Khalid", "Omar", "Yousef", "Hamad", "Saeed"], ["Fatima", "Maryam", "Noura", "Hessa", "Aisha", "Reem"], ["Al Hashemi", "Al Ali", "Haddad", "Al Suwaidi", "Nasser", "Al Zaabi"], ["Arabic", "English"]),
    "Urdu": (["Imran", "Bilal", "Kamran"], ["Sana", "Hira", "Saima"], ["Qureshi", "Siddiqui", "Malik"], ["Urdu", "Hindi", "English"]),
    "Malayalam": (["Anil", "Thomas", "Arun"], ["Lakshmi", "Mary", "Sneha"], ["Nair", "Varghese", "Menon"], ["Malayalam", "English"]),
    "Hindi": (["Rahul", "Vikram", "Sanjay"], ["Priya", "Kavya", "Neha"], ["Sharma", "Gupta", "Joshi"], ["Hindi", "Urdu", "English"]),
    "Tagalog": (["Mark", "Carlo"], ["Grace", "Angelica", "Joy"], ["Santos", "Reyes", "Cruz"], ["Tagalog", "English"]),
    "Bengali": (["Rafiq", "Tanvir"], ["Nasrin", "Farzana", "Sumaiya"], ["Rahman", "Hossain", "Chowdhury"], ["Bengali", "English"]),
    "Western": (["James", "Daniel"], ["Claire", "Emma"], ["Brown", "Martin"], ["English"]),
}
CLIN_MIX = {"Family physician": [("Arab", .55), ("Urdu", .15), ("Hindi", .1), ("Malayalam", .1), ("Western", .1)],
            "Paediatrician": [("Arab", .55), ("Urdu", .15), ("Hindi", .1), ("Malayalam", .1), ("Western", .1)],
            "Nurse": [("Malayalam", .3), ("Tagalog", .3), ("Arab", .2), ("Hindi", .1), ("Bengali", .1)]}
def pick_w(pairs):
    keys = [k for k, _ in pairs]; w = np.array([v for _, v in pairs]); return keys[srng.choice(len(keys), p=w / w.sum())]

def hm(s): h, m = s.split(":"); return int(h) * 60 + int(m)
def fmt_hm(x): return f"{x // 60:02d}:{x % 60:02d}"

district_pop = collections.Counter(H[p["hh"]]["district"] for p in people)
district_region = {h["district"]: h["region"] for h in D["households"]}
labour_districts = {h["district"] for h in D["households"] if h["housing"] == "labour accommodation"}
largest = {}
for dname, n in district_pop.items():
    r = district_region[dname]
    if n > largest.get(r, ("", 0))[1]: largest[r] = (dname, n)
CLINICS, CLINICIANS = [], []
cid = did = 0
for dname in sorted(district_pop, key=lambda x: (district_region[x], x)):
    n_cl = 2 if district_pop[dname] > 450 else 1
    for k in range(n_cl):
        cid += 1
        name = f"{dname} Healthcare Centre" if k == 0 else f"{dname} Family Clinic"
        sat = k == 0 and (dname in labour_districts or largest[district_region[dname]][0] == dname)
        c = {"id": f"L{cid:02d}", "name": name, "district": dname, "region": district_region[dname], "saturday": bool(sat), "staff": []}
        roster = ["Family physician", "Family physician", "Paediatrician", "Nurse"] if district_region[dname] != "Al Dhafra" else ["Family physician", "Paediatrician", "Nurse"]
        used_names = set()
        for i, role in enumerate(roster):
            did += 1
            grp = "Arab" if i == 0 else pick_w(CLIN_MIX[role]); fm, ff, ln, langs = CLIN_NAMES[grp]
            langs = list(langs)
            if grp != "Arab" and srng.random() < 0.45: langs.insert(0, "Arabic")   # working Arabic among non-Arab staff
            sex = "F" if srng.random() < (0.85 if role == "Nurse" else 0.5) else "M"
            for _ in range(20):
                first = str(srng.choice(ff if sex == "F" else fm)); last = str(srng.choice(ln))
                if (first, last) not in used_names: break
            used_names.add((first, last))
            title = "" if role == "Nurse" else "Dr "
            cl = {"id": f"D{did:03d}", "name": f"{title}{first} {last}", "role": role, "clinic": c["id"], "languages": langs,
                  "saturday": bool(sat and (i == 0 or role != "Family physician"))}
            CLINICIANS.append(cl); c["staff"].append(cl["id"])
        CLINICS.append(c)
CLI = {c["id"]: c for c in CLINICIANS}; LOC = {c["id"]: c for c in CLINICS}
clinics_in = collections.defaultdict(list)
for c in CLINICS: clinics_in[c["district"]].append(c["id"])

# home clinic per household, treating physician per person
for h in D["households"]:
    cl = clinics_in[h["district"]]
    h["home_clinic"] = cl[int(h["id"][1:]) % len(cl)]
for p in people:
    c = LOC[H[p["hh"]]["home_clinic"]]
    role = "Paediatrician" if p["age"] < 18 else "Family physician"
    staff = [s for s in c["staff"] if CLI[s]["role"] == role]
    lang = H[p["hh"]]["lang"]
    speaks = [s for s in staff if lang in CLI[s]["languages"]]
    pool = speaks or staff                       # language-concordant treating physician when the clinic has one
    p["tp"] = pool[int(p["hh"][1:]) % len(pool)]  # one treating physician per role per household
    p["clinic"] = c["id"]

def purposes_of(p):
    ps = sorted({RULE_PURPOSE[g["rule"]] for g in p["gaps"] if g["rule"] in RULE_PURPOSE}, key=lambda k: -PURPOSES[k]["weight"])
    return ps
def visit_role(p, ps):
    phys = [k for k in ps if PURPOSES[k]["role"] != "Nurse"]
    if not phys: return "Nurse"
    return "Paediatrician" if p["age"] < 18 else "Family physician"
def visit_minutes(ps, role):
    mins = sum(PURPOSES[k]["minutes"] for k in ps if PURPOSES[k]["role"] != "Nurse" or role == "Nurse")
    if role != "Nurse" and any(PURPOSES[k]["role"] == "Nurse" for k in ps): mins += 5   # vaccines or checks given in the same visit
    return int(min(45, max(10, mins)))

CAL_RULES = [(date.fromisoformat(c["start"]), date.fromisoformat(c["end"]), c) for c in CALENDAR_2026_27]
def cal_of(d):
    for s, e, c in CAL_RULES:
        if s <= d <= e: return c
    return None
def sessions_on(d, clinic):
    c = cal_of(d)
    if c and c["rule"] == "avoid": return []
    wd = d.weekday()
    if c and c["rule"].startswith("evening"):
        return ["ramadan_evening"] if wd in SESSIONS["ramadan_evening"]["days"] else []
    out = [k for k, s in SESSIONS.items() if k != "ramadan_evening" and wd in s["days"]]
    if not clinic["saturday"]: out = [k for k in out if k != "saturday_morning"]
    return out
def allowed_sessions(h, members, d):
    c = cal_of(d); winter = bool(c and c["rule"] == "family-friendly")
    working = any(P2[m]["role"] in ("father", "mother", "self") and P2[m]["age"] < 60 for m in members)
    school = any(5 <= P2[m]["age"] < 18 for m in members)
    if H[h["id"]]["shift_work"]: return {"friday_afternoon", "saturday_morning", "ramadan_evening"}
    if (working or school) and not winter: return {"weekday_evening", "friday_afternoon", "saturday_morning", "ramadan_evening"}
    return set(SESSIONS)
P2 = P
used = collections.Counter()          # (clinician, date, session) -> minutes booked
APPTS = []; aid = 0
for h in hh_out:                      # priority order
    mem = [m for m in h["members"] if P[m]["gaps"] and P[m]["consent"]["outreach"]]
    h["appts"] = []; h["slot"] = None; h["home_clinic"] = H[h["id"]]["home_clinic"]
    if not mem or h["priority"] <= 0: continue
    clinic = LOC[h["home_clinic"]]
    booked = None
    for off in range(7, 85):
        d = TODAY + timedelta(days=off)
        allow = allowed_sessions(h, mem, d)
        for sk in sessions_on(d, clinic):
            if sk not in allow: continue
            s = SESSIONS[sk]; cap = int((hm(s["end"]) - hm(s["start"])) * FHD_SHARE)
            plan, tmp = [], collections.Counter()
            ok = True
            for m in sorted(mem, key=lambda x: P[x]["age"]):
                p = P[m]; ps = purposes_of(p)
                if not ps: continue
                role = visit_role(p, ps); dur = visit_minutes(ps, role)
                cands = [p["tp"]] if role == CLI[p["tp"]]["role"] else []
                extra = [x for x in clinic["staff"] if CLI[x]["role"] == role and x not in cands and (off > 21 or role == "Nurse" or not cands)]
                cands += sorted(extra, key=lambda x: h["lang"] not in CLI[x]["languages"])
                if sk == "saturday_morning": cands = [x for x in cands if CLI[x]["saturday"]]
                chosen = None
                for x in cands:
                    k = (x, d, sk)
                    if used[k] + tmp[k] + dur <= cap: chosen = x; break
                if not chosen: ok = False; break
                k = (chosen, d, sk); start = hm(s["start"]) + used[k] + tmp[k]; tmp[k] += dur
                plan.append((m, chosen, start, dur, ps, role))
            if ok and plan:
                for k, v in tmp.items(): used[k] += v
                booked = (d, sk, plan); break
        if booked: break
    if not booked:
        h["waitlist"] = True; continue
    d, sk, plan = booked
    for m, chosen, start, dur, ps, role in plan:
        aid += 1
        cl = CLI[chosen]; lang = h["lang"]
        a = {"id": f"A{aid:05d}", "hh": h["id"], "pid": m, "clinic": clinic["id"], "clinician": chosen, "date": d.isoformat(),
             "start": fmt_hm(start), "end": fmt_hm(start + dur), "minutes": dur, "session": sk, "purposes": ps, "role": role,
             "continuity": chosen == P[m]["tp"], "interpreter": lang not in cl["languages"]}
        APPTS.append(a); h["appts"].append(a["id"]); P[m]["appt"] = a["id"]
    first = min((x for x in APPTS if x["hh"] == h["id"]), key=lambda x: x["start"])
    c = cal_of(d); why = []
    if c: why.append(c["name"] + " — " + c["rule"])
    if H[h["id"]]["shift_work"]: why.append("shift-work household: weekend session")
    if any(5 <= P[m]["age"] < 18 for m in mem) and sk == "weekday_evening": why.append("school-age child: after school hours")
    why.append(f"{clinic['name']}, treating physicians first")
    h["slot"] = {"date": d.isoformat(), "time": first["start"] + (" (after iftar)" if sk == "ramadan_evening" else ""), "why": why}
n_cont = sum(a["continuity"] for a in APPTS if a["role"] != "Nurse"); n_phys = sum(a["role"] != "Nurse" for a in APPTS)
print(f"clinics {len(CLINICS)} clinicians {len(CLINICIANS)} appointments {len(APPTS)} households booked {sum(1 for h in hh_out if h['appts'])} "
      f"waitlisted {sum(1 for h in hh_out if h.get('waitlist'))} continuity {n_cont}/{n_phys} interpreter {sum(a['interpreter'] for a in APPTS)}")

# =========================================================== 7. EQUITY & SAFEGUARDS AUDIT
def members_sel(alloc):
    out = set()
    for h in alloc: out.update(m for m in h["members"] if P[m]["gaps"] and P[m]["consent"]["outreach"])
    return out
prioritised = members_sel(ALLOC_EQUITY); prioritised_plain = members_sel(ALLOC_PLAIN)
for h in hh_out: h["selected"] = any(h is a for a in ALLOC_EQUITY)
rng_b = np.random.default_rng(99)
pool = [p for p in people if p["gaps"] and p["consent"]["outreach"] and any(not g["rule"].startswith(("CASCADE", "DPP", "DEV", "EARLY", "PATHWAY")) for g in p["gaps"])]
baseline_sel = set(pool[i]["id"] for i in rng_b.permutation(len(pool))[:CAPACITY])
print("selected people: equity", len(prioritised), "plain", len(prioritised_plain), "baseline", len(baseline_sel))

def seg_key(p, dim):
    hh = H[p["hh"]]
    if dim == "Nationality group": return hh["group"]
    if dim == "Region": return hh["region"]
    if dim == "Preferred language": return hh["lang"]
    if dim == "Sex": return {"M": "Male", "F": "Female"}[p["sex"]]
    if dim == "Life stage": return "Child <7" if p["age"] < 7 else ("Child/teen 7-17" if p["age"] < 18 else ("Adult 18-39" if p["age"] < 40 else ("Adult 40-64" if p["age"] < 65 else "Adult 65+")))
    if dim == "Insurance": return hh["insurance"]

from scipy.stats import chi2 as _chi2
def cal_ci(c):
    """Expected/observed ratio with an exact Poisson 95% interval on the observed count."""
    if c["cal_n"] < 30 or c["cal_obs"] < SMALL_CELL_THRESHOLD: return {"cal_ratio": None, "cal_lo": None, "cal_hi": None}
    O, E = c["cal_obs"], c["cal_pred"]
    o_lo, o_hi = _chi2.ppf(0.025, 2 * O) / 2, _chi2.ppf(0.975, 2 * O + 2) / 2
    return {"cal_ratio": round(E / O, 2), "cal_lo": round(E / o_hi, 2), "cal_hi": round(E / o_lo, 2)}

def audit(dim):
    rows = collections.defaultdict(lambda: collections.Counter())
    for p in people:
        k = seg_key(p, dim); c = rows[k]
        c["n"] += 1
        need = bool(p["gaps"]) and true_high_risk(p)
        c["need"] += need
        for tag, sel in (("bayt", prioritised), ("plain", prioritised_plain), ("base", baseline_sel)):
            s = p["id"] in sel
            c[tag + "_sel"] += s
            c[tag + "_tp"] += s and need
            c[tag + "_fn"] += (not s) and need
            c[tag + "_fp"] += s and not need
        if p["score"] and p["id"] in test_ids_adult | test_ids_child:
            c["cal_n"] += 1; c["cal_pred"] += p["score"]["risk"]
            c["cal_obs"] += p["y_cardiomet_3y"] if p["age"] >= 18 else p["dev_delay_true"]
    res = []
    for k, c in sorted(rows.items(), key=lambda t: -t[1]["n"]):
        n = c["n"]; small = n < SMALL_CELL_THRESHOLD
        def rate(a, b): return None if small or b < SMALL_CELL_THRESHOLD else round(a / b, 3)
        res.append({"segment": k, "n": n if not small else f"<{SMALL_CELL_THRESHOLD}", "suppressed": small,
                    "need": None if small or c["need"] < SMALL_CELL_THRESHOLD else c["need"],
                    "bayt_reach": rate(c["bayt_sel"], n), "base_reach": rate(c["base_sel"], n),
                    "bayt_sens": rate(c["bayt_tp"], c["need"]), "base_sens": rate(c["base_tp"], c["need"]),
                    "plain_sens": rate(c["plain_tp"], c["need"]), "plain_reach": rate(c["plain_sel"], n),
                    "bayt_fnr": rate(c["bayt_fn"], c["need"]), "base_fnr": rate(c["base_fn"], c["need"]),
                    "bayt_ppv": rate(c["bayt_tp"], c["bayt_sel"]), "base_ppv": rate(c["base_tp"], c["base_sel"]),
                    **cal_ci(c),
                    "cal_n": c["cal_n"]})
    return res

AUDIT = {d: audit(d) for d in ("Nationality group", "Region", "Preferred language", "Sex", "Life stage", "Insurance")}
# fairness alerts: sensitivity gap > 0.15 vs overall, or calibration ratio outside 0.8-1.25
alerts = []
for d, rows in AUDIT.items():
    sens = [r["plain_sens"] for r in rows if r["plain_sens"] is not None]
    if not sens: continue
    overall = np.mean(sens)
    for r in rows:
        if r["plain_sens"] is not None and r["plain_sens"] < overall - 0.15:
            fixed = r["bayt_sens"]
            alerts.append({"level": "resolved" if fixed is not None and fixed >= overall - 0.15 else "open",
                           "text": f"{d} = {r['segment']}: sensitivity {r['plain_sens']:.0%} vs mean {overall:.0%} under pure-priority allocation"
                                   + (f" → {fixed:.0%} with equity floor" if fixed is not None else "")})
        if r["cal_ratio"] is not None and not (0.8 <= r["cal_ratio"] <= 1.25):
            sig_dev = r["cal_hi"] < 1.0 or r["cal_lo"] > 1.0
            alerts.append({"level": "open" if sig_dev else "watch",
                           "text": f"{d} = {r['segment']}: predicted/observed {r['cal_ratio']} (95% CI {r['cal_lo']}–{r['cal_hi']}). "
                                   + (f"Significant {'over' if r['cal_ratio'] > 1 else 'under'}-estimation: recalibrate this segment before the next cycle."
                                      if sig_dev else "Interval includes 1: under watch, no action until more outcomes accrue.")})
print("alerts:", len(alerts)); [print(" -", a["level"], a["text"][:110]) for a in alerts]

# =========================================================== 8. EXPORT
GAP_META = {}
for p in people:
    for g in p["gaps"]:
        GAP_META.setdefault(g["rule"], {"source": g.get("source"), "followup": g.get("followup"), "note": g.get("note")})
def slim_gap(g):
    o = {"r": g["rule"], "i": g["item"], "s": g["status"], "d": g["days"]}
    if g.get("via"): o["via"] = g["via"]
    return o

def slim(p):
    keep = ["id", "hh", "group", "sex", "age", "role", "mother", "father", "first", "last", "consent", "genomic_available", "tp", "clinic", "appt",
            "gaps", "score", "p_attend", "barriers", "completeness", "confidence", "priority", "priority_parts"]
    o = {k: p.get(k) for k in keep}
    o["gaps"] = [slim_gap(g) for g in p["gaps"]]
    if p["age"] >= 18: o["off"] = round(seg_offset(M_ADULT, p), 3)
    o["age"] = round(p["age"], 1)
    if p["age"] >= 18:
        o["clin"] = {"bmi": p["bmi"], "hba1c": p.get("hba1c"), "htn": p["htn"], "t2d": p["t2d_known"], "smoke": p["smoke"],
                     "active": p["active"], "famhx_t2d": p["famhx_t2d_reported"], "last_ifhas": p.get("last_ifhas")}
        o["feat"] = adult_features(p, {"genomic": True, "family_link": True, "social": True, "outreach": True})
        o["feat_raw_gen"] = bool(p["genomic_available"] and p["variants"]["FH"])
    elif p["age"] >= 0.5 and p["age"] < 7:
        o["clin"] = {"preterm": p.get("preterm"), "wcv_attended": p["wcv_attended"], "mchat18": p["mchat18"],
                     "mchat24": p["mchat24"], "cbc_done": p["cbc_done"], "hb": p.get("hb")}
        o["feat"] = child_features(p, {"genomic": True, "family_link": True, "social": True, "outreach": True})
    else:
        o["clin"] = {"wcv_attended": p.get("wcv_attended")} if p["age"] < 18 else {}
    # genomic flags shown only when consented (never raw variant for non-consented)
    if p["consent"]["genomic"] and p["genomic_available"]:
        o["genomic"] = [v for v, on in p["variants"].items() if on and (p["age"] >= 18 or v in ("FH", "HBB"))]
    o["truth"] = {"high_risk": bool(true_high_risk(p))}  # for evaluation views only (synthetic)
    return o

def strip_boot(m): return {k: v for k, v in m.items() if k != "boot_coef"} | {"labels": [LABEL[f] for f in m["features"]]}

counts = collections.Counter(g["rule"] for p in people for g in p["gaps"])
summary = {
    "people": len(people), "households": len(hh_out),
    "children_u7": sum(1 for p in people if p["age"] < 7), "adults": len(adults),
    "people_with_gaps": sum(1 for p in people if p["gaps"]),
    "gap_counts": dict(counts.most_common()),
    "overdue_wcv": sum(1 for p in people for g in p["gaps"] if g["rule"] == "WCV-VISIT" and g["status"] == "overdue"),
    "mchat_gaps": counts["WCV-MCHAT-18"] + counts["WCV-MCHAT-24"],
    "cascade_relatives": sum(1 for p in people if any(g["rule"].startswith("CASCADE") for g in p["gaps"])),
    "pathway_gap_adults": counts["PATHWAY-GAP"],
    "consent_withdrawn_outreach": sum(1 for p in people if not p["consent"]["outreach"]),
}
# community view: district-level aggregates with suppression
dist = collections.defaultdict(lambda: collections.Counter())
for p in people:
    hh = H[p["hh"]]; k = (hh["region"], hh["district"]); c = dist[k]
    c["n"] += 1; c["gaps"] += len(p["gaps"]); c["with_gap"] += bool(p["gaps"])
    c["workers"] += hh["housing"] == "labour accommodation"; c["pathway_gap"] += any(g["rule"] == "PATHWAY-GAP" for g in p["gaps"])
    c["overdue_child"] += any(g["rule"].startswith("WCV") and g["status"] == "overdue" for g in p["gaps"])
community = [{"region": k[0], "district": k[1], **{kk: (v if c["n"] >= SMALL_CELL_THRESHOLD else None) for kk, v in c.items()},
              "gap_rate": round(c["with_gap"] / c["n"], 3) if c["n"] >= SMALL_CELL_THRESHOLD else None}
             for k, c in dist.items()]
community.sort(key=lambda r: -(r["gap_rate"] or 0))

ad2079 = [p for p in people if 20 <= p["age"] < 80]
ANCH_OUT = {k: dict(v) for k, v in ANCHORS.items()}
ANCH_OUT["diabetes_prevalence_20_79"]["synthetic"] = round(sum(p["t2d"] for p in ad2079) / len(ad2079), 3)
t2all = [p for p in ad2079 if p["t2d"]]
ANCH_OUT["diabetes_undiagnosed_share"]["synthetic"] = round(sum(not p["t2d_known"] for p in t2all) / len(t2all), 3)
summary["vax_gaps"] = sum(1 for p in people if any(g["rule"] == "VAX" for g in p["gaps"]))
summary["school_gaps"] = sum(1 for p in people if any(g["rule"] == "SCH-ANNUAL" for g in p["gaps"]))
summary["undiagnosed_diabetes"] = len([p for p in people if p["age"] >= 18 and p["t2d"] and not p["t2d_known"]])
OUT = {"version": GUIDELINE_VERSION, "today": D["today"], "summary": summary, "validation": VALID, "anchors": ANCH_OUT,
       "models": {"adult": strip_boot(M_ADULT), "child": strip_boot(M_CHILD), "engage": strip_boot(M_ENG)},
       "households": hh_out, "people": {p["id"]: slim(p) for p in people},
       "simulation": SIM, "audit": AUDIT, "alerts": alerts, "community": community,
       "calendar": CALENDAR_2026_27, "rules": {"child": CHILD_RULES, "adult": ADULT_RULES, "risk": RISK_PATHWAYS,
                                               "wcv_ages": WCV_AGES_MONTHS},
       "small_cell": SMALL_CELL_THRESHOLD, "gap_meta": GAP_META, "gap_weight": GAP_WEIGHT,
       "clinics": CLINICS, "clinicians": CLINICIANS, "appointments": APPTS, "purposes": PURPOSES, "rule_purpose": RULE_PURPOSE}
# compact encoding: feature vectors as arrays (model feature order), factor labels as label-table indices
LABEL_LIST = list(LABEL.values()); LIDX = {v: i for i, v in enumerate(LABEL_LIST)}
for o in OUT["people"].values():
    if "feat" in o:
        mk = "adult" if o["age"] >= 18 else "child"
        o["feat"] = [round(o["feat"][k], 3) for k in OUT["models"][mk]["features"]]
    if o.get("score"):
        o["score"]["factors"] = [[LIDX[f["f"]], round(f["v"], 2)] for f in o["score"]["factors"]]
    o["barriers"] = [[LIDX[f["f"]], round(f["v"], 2)] for f in o["barriers"]]
    o["priority_parts"] = [o["priority_parts"]["need"], o["priority_parts"]["risk_mult"], o["priority_parts"]["barrier_mult"]]
    o["consent"] = [int(o["consent"][k]) for k in ("genomic", "family_link", "social", "outreach")]
    o["hr"] = int(o.pop("truth")["high_risk"])
OUT["labels"] = LABEL_LIST
json.dump(OUT, open(str(ROOT / "data" / "scope.json"), "w"), separators=(",", ":"))
print("summary", summary)
import os; print("json MB", round(os.path.getsize(str(ROOT / "data" / "scope.json")) / 1e6, 2))
