"""Privacy and safety invariants."""
import re

def test_no_adult_onset_genomics_shown_for_minors(data):
    for p in data["people"].values():
        if p["age"] < 18:
            assert not set(p.get("genomic", [])) & {"BRCA", "LYNCH"}, p["id"]

def test_genomic_only_with_consent(data):
    for p in data["people"].values():
        if p.get("genomic"):
            assert p["consent"][0] == 1 and p["genomic_available"]

def test_cascade_index_consented(data):
    P = data["people"]
    for p in P.values():
        for g in p["gaps"]:
            if g["r"].startswith("CASCADE"):
                idx = P[g["via"]]
                assert idx["consent"][0] == 1 and idx["consent"][1] == 1, "index must consent to genomic use and family linkage"

def test_small_cells_suppressed(data):
    k = data["small_cell"]
    for dim, rows in data["audit"].items():
        for r in rows:
            if isinstance(r["n"], int):
                assert r["n"] >= k
            else:
                assert r["suppressed"] and all(r[f] is None for f in ("bayt_sens", "base_sens", "bayt_ppv", "need"))

def test_invitation_text_names_no_condition(client, data):
    banned = re.compile(r"diabet|cancer|autis|genetic|genom|variant|thalass|cholesterol|anaemi|anemi|mammo|HPV|M-CHAT", re.I)
    for h in [h for h in data["households"] if h.get("slot")][:150]:
        st, b, _ = client.call("GET", f"/fhir/Group/{h['id']}/$family-plan", "coordinator-demo", "CAREMGT")
        assert st == 200
        cr = [e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "CommunicationRequest"]
        for c in cr:
            assert not banned.search(c["payload"][0]["contentString"]), c["payload"][0]["contentString"]

def test_withdrawn_outreach_means_zero_priority(data):
    for p in data["people"].values():
        if p["consent"][3] == 0:
            assert p["priority"] == 0
