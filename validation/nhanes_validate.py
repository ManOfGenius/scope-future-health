"""
External validation of the frozen S.C.O.P.E adult model on real people: NHANES 2017–March 2020 (pre-pandemic).

Question: does the model trained on the synthetic Abu Dhabi population rank real adults by their chance of having
undiagnosed diabetes at least as well as the published FINDRISC score and age alone?

Population: adults 20–79 without diagnosed diabetes, with HbA1c and BMI measured.
Primary outcome: undiagnosed diabetes = HbA1c >= 6.5% or fasting glucose >= 126 mg/dL (fasting subsample).
Secondary outcome: dysglycaemia = HbA1c >= 5.7%.

The model is applied as shipped (data/scope.json), with no refitting. Measured HbA1c defines the outcome, so the model
never sees it: its HbA1c inputs come from the questionnaire instead (told prediabetes; blood tested in the past 3 years),
exactly the history a primary-care record would hold. FINDRISC gets the same information ("told high glucose").

Usage:  python validation/nhanes_validate.py <folder with P_*.xpt>   ->  validation/nhanes_results.json
Files:  P_DEMO P_GHB P_GLU P_DIQ P_BMX P_BPQ P_MCQ P_PAQ P_SMQ  (https://wwwn.cdc.gov/nchs/nhanes/, cycle 2017-2020)
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "validation" / "nhanes"
rd = lambda n: pd.read_sas(SRC / f"{n}.xpt", format="xport")

df = rd("P_DEMO")[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "WTMECPRP", "SDMVPSU", "SDMVSTRA"]]
for n, cols in [("P_GHB", ["LBXGH"]), ("P_GLU", ["LBXGLU", "WTSAFPRP"]), ("P_DIQ", ["DIQ010", "DIQ160", "DIQ180"]),
                ("P_BMX", ["BMXBMI", "BMXWAIST"]), ("P_BPQ", ["BPQ020", "BPQ040A"]), ("P_MCQ", ["MCQ300C"]),
                ("P_PAQ", ["PAQ605", "PAQ620", "PAQ635", "PAQ650", "PAQ665"]), ("P_SMQ", ["SMQ020", "SMQ040"])]:
    df = df.merge(rd(n)[["SEQN"] + cols], on="SEQN", how="left")

n_all = len(df)
pop = df[(df.RIDAGEYR >= 20) & (df.RIDAGEYR <= 79)]
n_age = len(pop)
pop = pop[pop.DIQ010 != 1]                          # exclude diagnosed diabetes
n_nodx = len(pop)
pop = pop[pop.LBXGH.notna() & pop.BMXBMI.notna() & (pop.WTMECPRP > 0)].copy()
yes = lambda s: (s == 1).astype(float)

# ---- predictors, as a record would hold them
pop["age"] = pop.RIDAGEYR; pop["male"] = pop.RIAGENDR == 1
pop["htn"] = yes(pop.BPQ020)
pop["htn_med"] = yes(pop.BPQ040A)
pop["famhx"] = yes(pop.MCQ300C)
pop["told_prediabetes"] = yes(pop.DIQ160)
pop["no_test_3y"] = (pop.DIQ180 == 2).astype(float)
pop["active"] = ((pop[["PAQ605", "PAQ620", "PAQ635", "PAQ650", "PAQ665"]] == 1).any(axis=1)).astype(float)
pop["smoker"] = pop.SMQ040.isin([1, 2]).astype(float)
pop["asian"] = (pop.RIDRETH3 == 6).astype(float)  # NHANES 'Non-Hispanic Asian' stands in for South Asian ancestry

# ---- outcomes
pop["y_undx"] = ((pop.LBXGH >= 6.5) | (pop.LBXGLU >= 126)).astype(int)
pop["y_dysg"] = (pop.LBXGH >= 5.7).astype(int)

# ---- frozen S.C.O.P.E adult model
M = json.loads((ROOT / "data" / "scope.json").read_text())["models"]["adult"]
X = {
    "age_per10": (pop.age - 40) / 10, "bmi_per5": (pop.BMXBMI - 27) / 5, "hypertension": pop.htn,
    "existing_diabetes": 0.0, "family_hx_diabetes": pop.famhx, "hba1c_prediabetes": pop.told_prediabetes,
    "hba1c_missing": pop.no_test_3y, "tobacco_any": pop.smoker, "physically_active": pop.active,
    "south_asian_ancestry": pop.asian, "fh_variant": 0.0, "genomic_not_available": 1.0,
}
z = M["intercept"] + sum(c * (X[f] if not np.isscalar(X[f]) else np.full(len(pop), X[f])) for f, c in zip(M["features"], M["coef"]))
pop["s_scope"] = 1 / (1 + np.exp(-z))

# ---- FINDRISC (Lindström & Tuomilehto 2003); the fruit-and-vegetable item is not in NHANES and is scored 0 for everyone
w = pop.BMXWAIST
f = np.select([pop.age < 45, pop.age < 55, pop.age < 65], [0, 2, 3], 4)
f = f + np.select([pop.BMXBMI < 25, pop.BMXBMI <= 30], [0, 1], 3)
waist = np.where(pop.male, np.select([w < 94, w <= 102], [0, 3], 4), np.select([w < 80, w <= 88], [0, 3], 4))
f = f + np.where(w.isna(), 0, waist)
f = f + np.where(pop.active == 1, 0, 2) + np.where(pop.htn_med == 1, 2, 0)
f = f + np.where(pop.told_prediabetes == 1, 5, 0) + np.where(pop.famhx == 1, 5, 0)
pop["s_findrisc"] = f.astype(float)
pop["s_age"] = pop.age.astype(float)

def wauc(y, s, w):
    """Weighted AUC: probability a random case outranks a random non-case, ties counted half."""
    o = np.argsort(s, kind="mergesort"); y, s, w = y[o], s[o], w[o]
    wp, wn = w * (y == 1), w * (y == 0)
    auc, cum_neg, i = 0.0, 0.0, 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]: j += 1
        p, n = wp[i:j].sum(), wn[i:j].sum()
        auc += p * (cum_neg + n / 2); cum_neg += n; i = j
    return auc / (wp.sum() * wn.sum())

def top10(y, s, w):
    o = np.argsort(-s, kind="mergesort"); cw = np.cumsum(w[o]); k = cw <= 0.1 * w.sum()
    return float((w[o][k] * y[o][k]).sum() / (w * y).sum())

SCORES = {"S.C.O.P.E model (frozen)": "s_scope", "FINDRISC": "s_findrisc", "Age only": "s_age"}
rng = np.random.default_rng(2026)
strata = pop.groupby("SDMVSTRA").SDMVPSU.unique().to_dict()

def boot_idx():
    """Resample PSUs within each stratum (design-based bootstrap)."""
    parts = []
    for st, psus in strata.items():
        pick = rng.choice(psus, size=len(psus), replace=True)
        for p in pick: parts.append(np.flatnonzero((pop.SDMVSTRA.values == st) & (pop.SDMVPSU.values == p)))
    return np.concatenate(parts)

def evaluate(ycol, B=400):
    y, w = pop[ycol].values, pop.WTMECPRP.values
    res = {k: {"auc": wauc(y, pop[c].values, w), "top10": top10(y, pop[c].values, w)} for k, c in SCORES.items()}
    boots = {k: [] for k in SCORES}; diffs = []
    for _ in range(B):
        ix = boot_idx(); yb, wb = y[ix], w[ix]
        a = {k: wauc(yb, pop[c].values[ix], wb) for k, c in SCORES.items()}
        for k in SCORES: boots[k].append(a[k])
        diffs.append(a["S.C.O.P.E model (frozen)"] - a["FINDRISC"])
    for k in SCORES:
        lo, hi = np.percentile(boots[k], [2.5, 97.5]); res[k]["auc_ci"] = [float(lo), float(hi)]
    d = np.array(diffs)
    res["difference_scope_minus_findrisc"] = {"auc": float(res["S.C.O.P.E model (frozen)"]["auc"] - res["FINDRISC"]["auc"]),
                                              "ci": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}
    res["cases"] = int(y.sum()); res["weighted_prevalence"] = float((w * y).sum() / w.sum())
    # observed prevalence by model decile (weighted)
    q = pd.qcut(pop.s_scope.rank(method="first"), 10, labels=False)
    res["prevalence_by_scope_decile"] = [float((w[q == d] * y[q == d]).sum() / w[q == d].sum()) for d in range(10)]
    return res

# ---- sensitivity: the model without the "no blood test in 3 years" input, which FINDRISC does not use
zi = M["features"].index("hba1c_missing")
pop["s_scope_no_test_item"] = 1 / (1 + np.exp(-(z - M["coef"][zi] * pop.no_test_3y + M["coef"][zi] * pop.no_test_3y.mean())))
y0, w0 = pop.y_undx.values, pop.WTMECPRP.values
sens = {"S.C.O.P.E without the testing-history input": wauc(y0, pop.s_scope_no_test_item.values, w0)}

# ---- fairness: AUC within each NHANES race and ethnicity group (primary outcome)
GROUPS = {1: "Mexican American", 2: "Other Hispanic", 3: "Non-Hispanic White", 4: "Non-Hispanic Black", 6: "Non-Hispanic Asian", 7: "Other or multiracial"}
by_group = {}
for code, name in GROUPS.items():
    g = (pop.RIDRETH3 == code).values
    if pop.y_undx.values[g].sum() >= 15:
        by_group[name] = {"n": int(g.sum()), "cases": int(pop.y_undx.values[g].sum()),
                          **{k: round(wauc(y0[g], pop[c].values[g], w0[g]), 3) for k, c in SCORES.items()}}

out = {
    "sensitivity_undiagnosed_diabetes": sens,
    "auc_by_group_undiagnosed_diabetes": by_group,
    "data": "NHANES 2017-March 2020 pre-pandemic (CDC/NCHS), public-use files",
    "flow": {"participants": n_all, "aged_20_79": n_age, "without_diagnosed_diabetes": n_nodx, "analysed": len(pop)},
    "undiagnosed_diabetes": evaluate("y_undx"),
    "dysglycaemia": evaluate("y_dysg"),
    "notes": [
        "Model applied as shipped, no refitting; segment offsets not applied.",
        "Measured HbA1c is the outcome and is never a predictor; history comes from the questionnaire.",
        "Non-Hispanic Asian stands in for South Asian ancestry; no genomic data.",
        "FINDRISC fruit-and-vegetable item unavailable (scored 0 for all).",
        "Fasting glucose exists only for the fasting subsample; others are classified on HbA1c.",
        "Weighted with WTMECPRP; 95% intervals from 400 PSU-within-stratum bootstrap replicates.",
    ],
}
(ROOT / "validation" / "nhanes_results.json").write_text(json.dumps(out, indent=1))
for o in ("undiagnosed_diabetes", "dysglycaemia"):
    r = out[o]; print(f"\n{o}: {r['cases']} cases, weighted prevalence {r['weighted_prevalence']:.3f}")
    for k in SCORES: print(f"  {k:28s} AUC {r[k]['auc']:.3f} ({r[k]['auc_ci'][0]:.3f}-{r[k]['auc_ci'][1]:.3f})  top10 {r[k]['top10']:.3f}")
    print("  diff vs FINDRISC", r["difference_scope_minus_findrisc"])
print(out["flow"]); print(sens); print(json.dumps(by_group, indent=0))
