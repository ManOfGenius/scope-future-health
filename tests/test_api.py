"""API behaviour: FHIR shape, access control, consent recomputation, audit trail."""
import collections

def first(data, pred):
    return next(p for p in data["people"].values() if pred(p))

def test_health_and_metadata_are_open(client):
    assert client.call("GET", "/health")[0] == 200
    st, b, h = client.call("GET", "/fhir/metadata")
    assert st == 200 and b["resourceType"] == "CapabilityStatement" and b["fhirVersion"] == "4.0.1"
    assert h["Content-Type"].startswith("application/fhir+json")

def test_requires_token_and_purpose(client, data):
    pid = next(iter(data["people"]))
    assert client.call("GET", f"/fhir/Patient/{pid}")[0] == 401
    assert client.call("GET", f"/fhir/Patient/{pid}", "clinician-demo", "PUBHLTH")[0] == 403
    st, b, _ = client.call("GET", f"/fhir/Patient/{pid}", "clinician-demo", "TREAT")
    assert st == 200 and b["resourceType"] == "Patient" and b["meta"]["tag"][0]["code"] == "synthetic"

def test_analyst_sees_only_aggregates(client, data):
    pid = next(iter(data["people"]))
    assert client.call("GET", f"/fhir/Patient/{pid}", "analyst-demo", "PUBHLTH")[0] == 403
    st, b, _ = client.call("GET", "/api/audit?dim=Region", "analyst-demo", "PUBHLTH")
    assert st == 200 and b["smallCellThreshold"] == 11

def test_family_scope_limited_to_own_household(client, data):
    H = data["households"]
    h1, h2 = H[0], H[1]
    me = h1["contact"]
    assert client.call("GET", f"/fhir/Group/{h1['id']}/$family-plan", f"family-{me}", "PATRQT")[0] == 200
    assert client.call("GET", f"/fhir/Group/{h2['id']}/$family-plan", f"family-{me}", "PATRQT")[0] == 403
    assert client.call("GET", "/api/worklist", f"family-{me}", "PATRQT")[0] == 403

def test_care_gaps_bundle_is_fhir(client, data):
    p = first(data, lambda p: p.get("score") and p["gaps"])
    st, b, _ = client.call("GET", f"/fhir/Patient/{p['id']}/$care-gaps", "clinician-demo", "TREAT")
    assert st == 200 and b["resourceType"] == "Bundle"
    types = {e["resource"]["resourceType"] for e in b["entry"]}
    assert "RiskAssessment" in types
    ra = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "RiskAssessment")
    assert 0 <= ra["prediction"][0]["probabilityDecimal"] <= 1
    assert "Population prioritisation" in ra["note"][0]["text"]
    for e in b["entry"]:
        assert e["resource"]["id"] and e["fullUrl"].endswith(e["resource"]["id"])

def test_vaccines_returned_as_immunization_recommendation(client, data):
    p = first(data, lambda p: any(g["r"] == "VAX" for g in p["gaps"]))
    st, b, _ = client.call("GET", f"/fhir/Patient/{p['id']}/$care-gaps", "clinician-demo", "TREAT")
    ir = [e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "ImmunizationRecommendation"]
    assert ir and ir[0]["recommendation"][0]["forecastStatus"]["coding"][0]["code"] in ("due", "overdue")

def test_withdrawing_genomic_consent_removes_relatives_cascade(client, data):
    P = data["people"]
    rel = first(data, lambda p: any(g["r"].startswith("CASCADE") for g in p["gaps"]))
    idx = next(g["via"] for g in rel["gaps"] if g["r"].startswith("CASCADE"))
    S = client.app.S
    assert any(g["r"].startswith("CASCADE") for g in S.visible_gaps(rel["id"]))
    idx_hh = P[idx]["hh"]
    token = f"family-{idx}" if P[idx]["age"] >= 18 else "clinician-demo"
    if token == "clinician-demo":
        S.set_consent(idx, "genomic", False)
    else:
        st, b, _ = client.call("PUT", f"/fhir/Consent/{idx}-genomic", token, "PATRQT", {"provision": {"type": "deny"}})
        assert st == 200
        assert next(p for p in b["parameter"] if p["name"] == "affectedRelatives")["valueInteger"] >= 1
    assert not any(g["r"].startswith("CASCADE") for g in S.visible_gaps(rel["id"]))

def test_adult_cannot_change_another_adults_consent(client, data):
    h = next(h for h in data["households"] if sum(data["people"][m]["age"] >= 18 for m in h["members"]) >= 2)
    adults = [m for m in h["members"] if data["people"][m]["age"] >= 18]
    st, _, _ = client.call("PUT", f"/fhir/Consent/{adults[1]}-social", f"family-{adults[0]}", "PATRQT", {"provision": {"type": "deny"}})
    assert st == 403

def test_parent_can_change_minor_consent_and_risk_recomputes(client, data):
    P = data["people"]
    ci = data["labels"].index("Parental consanguinity")
    kid = first(data, lambda p: p.get("score") and p["score"]["model"] == "child" and p["consent"][1] == 1 and p.get("mother") in P
                and any(f[0] == ci for f in p["score"]["factors"]))  # consanguinity is among the top factors
    st, b, _ = client.call("PUT", f"/fhir/Consent/{kid['id']}-family_link", f"family-{kid['mother']}", "PATRQT", {"provision": {"type": "deny"}})
    assert st == 200
    vals = {p["name"]: p.get("valueDecimal") for p in b["parameter"]}
    assert vals["riskAfter"] != vals["riskBefore"]

def test_outreach_withdrawal_revokes_invitation(client, data):
    h = next(h for h in data["households"] if h.get("slot") and data["people"][h["contact"]]["consent"][3] == 1)
    st, _, _ = client.call("PUT", f"/fhir/Consent/{h['contact']}-outreach", f"family-{h['contact']}", "PATRQT", {"provision": {"type": "deny"}})
    assert st == 200
    st, b, _ = client.call("GET", f"/fhir/Group/{h['id']}/$family-plan", "coordinator-demo", "CAREMGT")
    cr = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "CommunicationRequest")
    assert cr["status"] == "revoked"

def test_every_access_is_audited_including_refusals(client, data):
    pid = next(iter(data["people"]))
    client.call("GET", f"/fhir/Patient/{pid}", "clinician-demo", "TREAT")
    client.call("GET", f"/fhir/Patient/{pid}", "analyst-demo", "PUBHLTH")
    assert client.call("GET", "/fhir/AuditEvent", "clinician-demo", "TREAT")[0] == 403
    st, b, _ = client.call("GET", "/fhir/AuditEvent", "auditor-demo", "HOPERAT")
    assert st == 200
    outcomes = [e["resource"]["outcome"] for e in b["entry"]]
    assert "0" in outcomes and "4" in outcomes

def _appt(data, purpose):
    return next(a for a in data["appointments"] if purpose in a["purposes"] and a["role"] != "Nurse")

def test_family_plan_carries_appointments_practitioners_location(client, data):
    h = next(h for h in data["households"] if h.get("appts"))
    st, b, _ = client.call("GET", f"/fhir/Group/{h['id']}/$family-plan", "coordinator-demo", "CAREMGT")
    types = collections.Counter(e["resource"]["resourceType"] for e in b["entry"])
    assert types["Appointment"] == len(h["appts"]) and types["Practitioner"] >= 1 and types["Location"] == 1

def test_only_booked_or_covering_clinician_can_sign(client, data):
    a = _appt(data, "CMR")
    other = next(c for c in data["clinicians"] if c["clinic"] != a["clinic"])
    body = {"findings": {"sbp": 150, "dbp": 95}, "conclusions": {k: "Referred" for k in a["purposes"]}, "icd": ["R03.0"]}
    assert client.call("POST", f"/fhir/Appointment/{a['id']}/$sign-encounter", f"practitioner-{other['id']}", "TREAT", body)[0] == 403
    assert client.call("POST", f"/fhir/Appointment/{a['id']}/$sign-encounter", "clinician-demo", "TREAT", body)[0] == 403
    assert client.call("POST", f"/fhir/Appointment/{a['id']}/$sign-encounter", f"practitioner-{a['clinician']}", "CAREMGT", body)[0] == 403

def test_signing_records_fhir_resources_and_closes_items(client, data):
    a = _appt(data, "CMR")
    before = len(client.app.S.visible_gaps(a["pid"]))
    body = {"findings": {"sbp": 150, "dbp": 95, "a1c": 6.8, "tobacco": "Shisha"}, "conclusions": {k: "Referred" for k in a["purposes"]},
            "icd": ["R03.0", "Z13.1"], "referrals": [{"to": "Diabetes clinic", "by": "2026-12-01"}], "labs": ["HbA1c (repeat)"],
            "counselling": ["Tobacco, shisha and medwakh cessation"], "note": "Synthetic test encounter."}
    st, b, _ = client.call("POST", f"/fhir/Appointment/{a['id']}/$sign-encounter", f"practitioner-{a['clinician']}", "TREAT", body)
    assert st == 200 and b["type"] == "transaction-response" and b["closedItems"] >= 1
    rs = [e["resource"] for e in b["entry"]]
    loinc = {c["code"] for r in rs if r["resourceType"] == "Observation" for c in r["code"]["coding"] if c["system"] == "http://loinc.org"}
    assert {"8480-6", "8462-4", "4548-4"} <= loinc
    assert {r["code"]["coding"][0]["code"] for r in rs if r["resourceType"] == "Condition"} == {"R03.0", "Z13.1"}
    assert any(r["resourceType"] == "ServiceRequest" and r["code"]["text"] == "Diabetes clinic" for r in rs)
    assert len(client.app.S.visible_gaps(a["pid"])) < before
    st, b, _ = client.call("GET", f"/fhir/Appointment?patient={a['pid']}", "clinician-demo", "TREAT")
    assert next(e["resource"] for e in b["entry"] if e["resource"]["id"] == a["id"])["status"] == "fulfilled"

def test_signing_requires_a_conclusion_per_purpose(client, data):
    a = _appt(data, "CMR")
    st, b, _ = client.call("POST", f"/fhir/Appointment/{a['id']}/$sign-encounter", f"practitioner-{a['clinician']}", "TREAT", {"conclusions": {}})
    assert st == 400
