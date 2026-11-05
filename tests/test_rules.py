"""Guideline layer: every flag must trace to an approved rule and respect its eligibility window."""
from guidelines import VAX_SCHEDULE, IFHAS_ELIGIBLE_AGE

ADULT_RULES = {"IF-CORE", "IF-CRC", "IF-MAMMO", "IF-CERV", "IF-FUNDUS", "IF-DEXA", "IF-MOCA", "LDCT", "DPP", "PATHWAY-GAP",
               "CASCADE-FH", "CASCADE-HBOC", "CASCADE-LYNCH"}

def test_every_gap_has_a_source(data):
    rules = {g["r"] for p in data["people"].values() for g in p["gaps"]}
    for r in rules:
        assert data["gap_meta"].get(r, {}).get("source"), f"rule {r} has no source"

def test_wcv_items_only_under_7(data):
    for p in data["people"].values():
        for g in p["gaps"]:
            if g["r"].startswith("WCV") or g["r"] == "DEV-PRIORITY":
                assert p["age"] < 7.05, (p["id"], g["r"], p["age"])

def test_adult_rules_only_for_adults(data):
    for p in data["people"].values():
        for g in p["gaps"]:
            if g["r"] in ADULT_RULES - {"CASCADE-FH"}:
                assert p["age"] >= 18, (p["id"], g["r"])

def test_ifhas_window_and_sex_specific_rules(data):
    lo, hi = IFHAS_ELIGIBLE_AGE
    for p in data["people"].values():
        rs = {g["r"] for g in p["gaps"]}
        if rs & {"IF-CORE", "IF-CRC", "IF-MAMMO", "IF-CERV"}:
            assert lo <= p["age"] <= hi + 1
        if rs & {"IF-MAMMO", "IF-CERV"}:
            assert p["sex"] == "F"
        if "IF-CRC" in rs or "IF-MAMMO" in rs:
            assert p["age"] >= 40

def test_non_thiqa_adults_get_pathway_gap_not_ifhas(data):
    H = {h["id"]: h for h in data["households"]}
    for p in data["people"].values():
        rs = {g["r"] for g in p["gaps"]}
        if H[p["hh"]]["insurance"] != "Thiqa":
            assert not rs & {"IF-CORE", "IF-CRC", "IF-MAMMO", "IF-CERV"}, p["id"]

def test_vaccine_gaps_match_schedule(data):
    labels = {f'{v["label"]}: {v["vaccines"]}': v["due_m"] for v in VAX_SCHEDULE}
    for p in data["people"].values():
        for g in p["gaps"]:
            if g["r"] == "VAX":
                assert g["i"] in labels
                assert p["age"] * 12 >= labels[g["i"]] - 0.1, (p["id"], g["i"])

def test_dpp_only_for_eligible_adults_without_known_diabetes(data):
    for p in data["people"].values():
        if any(g["r"] == "DPP" for g in p["gaps"]):
            assert 18 <= p["age"] <= 75
            assert not p["clin"]["t2d"]
