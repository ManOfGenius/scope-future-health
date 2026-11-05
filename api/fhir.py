"""
FHIR R4 mappers for S.C.O.P.E.

Standard terminologies are used where they exist (HL7 v3 RoleCode, risk-probability,
immunization-recommendation-status, consentscope, BCP-47). Local codes use the
placeholder canonical base below until a DoH-assigned namespace is available.
"""
from __future__ import annotations

from datetime import date

BASE = "https://fhir.scope.example"
CS_GAP = f"{BASE}/CodeSystem/care-gap"
CS_CONSENT = f"{BASE}/CodeSystem/data-category"
SID = f"{BASE}/sid/synthetic-person"
LANG = {"Arabic": "ar", "English": "en", "Urdu": "ur", "Hindi": "hi", "Malayalam": "ml", "Tagalog": "tl", "Bengali": "bn"}
ROLE_CODE = {"mother": ("MTH", "mother"), "father": ("FTH", "father"), "grandmother": ("GRMTH", "grandmother"),
             "grandfather": ("GRFTH", "grandfather"), "child": ("CHILD", "child")}
SEVERITY = {"overdue": "moderate", "never": "moderate", "due": "low", "risk-based": "moderate", "system": "low"}
DISCLAIMER = "Population prioritisation only. Clinical decisions are made by the treating clinician."


def ref(rt: str, rid: str) -> dict:
    return {"reference": f"{rt}/{rid}"}


def patient(S, pid: str) -> dict:
    p, raw = S.people[pid], S.raw[pid]
    hh = S.households[p["hh"]]
    return {
        "resourceType": "Patient", "id": pid,
        "meta": {"tag": [{"system": f"{BASE}/tags", "code": "synthetic", "display": "Synthetic record"}]},
        "identifier": [{"system": SID, "value": pid}],
        "name": [{"family": p["last"], "given": [p["first"]]}],
        "gender": "female" if p["sex"] == "F" else "male",
        "birthDate": raw["dob"],
        "address": [{"district": hh["district"], "city": hh["region"], "state": "Abu Dhabi", "country": "AE"}],
        "communication": [{"language": {"coding": [{"system": "urn:ietf:bcp:47", "code": LANG.get(hh["lang"], "en"),
                                                     "display": hh["lang"]}]}, "preferred": True}],
        "extension": [{"url": f"{BASE}/StructureDefinition/household", "valueReference": ref("Group", p["hh"])},
                      {"url": f"{BASE}/StructureDefinition/insurance-programme", "valueString": hh["insurance"]}],
    }


def group(S, hid: str) -> dict:
    h = S.households[hid]
    return {
        "resourceType": "Group", "id": hid, "type": "person", "actual": True, "name": f"{h['surname']} household",
        "quantity": len(h["members"]),
        "characteristic": [
            {"code": {"text": "region"}, "valueCodeableConcept": {"text": h["region"]}, "exclude": False},
            {"code": {"text": "preferred language"}, "valueCodeableConcept": {"text": h["lang"]}, "exclude": False}],
        "member": [{"entity": ref("Patient", m)} for m in h["members"]],
    }


def related_people(S, hid: str) -> list[dict]:
    out = []
    for m in S.households[hid]["members"]:
        p = S.people[m]
        for k in ("mother", "father"):
            par = p.get(k)
            if par and par in S.people:
                q = S.people[par]
                code, disp = ROLE_CODE[k]
                out.append({"resourceType": "RelatedPerson", "id": f"{m}-{k}", "patient": ref("Patient", m),
                            "relationship": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                                                          "code": code, "display": disp}]}],
                            "name": [{"family": q["last"], "given": [q["first"]]}],
                            "extension": [{"url": f"{BASE}/StructureDefinition/same-as-patient", "valueReference": ref("Patient", par)}]})
    return out


def detected_issue(S, pid: str, g: dict, i: int) -> dict:
    meta = S.D["gap_meta"].get(g["r"], {})
    res = {
        "resourceType": "DetectedIssue", "id": f"{pid}-gap-{i}", "status": "preliminary",
        "code": {"coding": [{"system": CS_GAP, "code": g["r"]}], "text": g["i"]},
        "severity": SEVERITY.get(g["s"], "low"), "patient": ref("Patient", pid),
        "identifiedDateTime": S.D["today"],
        "detail": g["i"] + (f" ({g['d']} days late)" if g["s"] == "overdue" and g["d"] > 0 else ""),
        "reference": meta.get("source") or "",
        "extension": [{"url": f"{BASE}/StructureDefinition/gap-status", "valueCode": g["s"]},
                      {"url": f"{BASE}/StructureDefinition/rule-version", "valueString": S.D["version"]}],
    }
    if meta.get("followup"):
        res["mitigation"] = [{"action": {"text": meta["followup"]}}]
    if g.get("via"):
        res["extension"].append({"url": f"{BASE}/StructureDefinition/index-mediated", "valueBoolean": True})
    return res


def immunization_recommendation(S, pid: str, gaps: list[dict]) -> dict | None:
    vg = [g for g in gaps if g["r"] == "VAX"]
    if not vg:
        return None
    return {
        "resourceType": "ImmunizationRecommendation", "id": f"{pid}-imm", "patient": ref("Patient", pid), "date": S.D["today"],
        "authority": {"display": "DoH Circular 2026/77, Immunization Schedule (Apr 2026)"},
        "recommendation": [{"vaccineCode": [{"text": g["i"]}],
                            "forecastStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/immunization-recommendation-status",
                                                           "code": "overdue" if g["s"] == "overdue" else "due"}]}} for g in vg],
    }


def risk_assessment(S, pid: str, lv: dict) -> dict | None:
    if lv["risk"] is None:
        return None
    m = S.models[lv["model"]]
    q = "high" if lv["rr"] >= 2 else "moderate" if lv["rr"] >= 1 else "low"
    return {
        "resourceType": "RiskAssessment", "id": f"{pid}-risk", "status": "final", "subject": ref("Patient", pid),
        "occurrenceDateTime": S.D["today"],
        "method": {"text": f"{m['name']} · logistic regression · {S.D['version']}"},
        "prediction": [{
            "outcome": {"text": m["name"]},
            "probabilityDecimal": round(lv["risk"], 4),
            "qualitativeRisk": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/risk-probability", "code": q}]},
            "relativeRisk": round(lv["rr"], 2),
            "whenPeriod": {"start": S.D["today"]} if lv["model"] == "child" else {"start": S.D["today"], "end": _plus_years(S.D["today"], 3)},
            "rationale": f"90% interval {lv['lo']:.3f}-{lv['hi']:.3f}; confidence {lv['confidence']}; data completeness {lv['completeness']:.0%}",
        }],
        "basis": [{"display": f"{lab}: {'raises' if v > 0 else 'lowers'} score (log-odds {v:+.2f})"} for lab, v in lv["factors"]],
        "note": [{"text": DISCLAIMER}],
    }


def consents(S, pid: str) -> list[dict]:
    out = []
    for k, on in S.consent[pid].items():
        out.append({
            "resourceType": "Consent", "id": f"{pid}-{k}", "status": "active",
            "scope": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "patient-privacy"}]},
            "category": [{"coding": [{"system": CS_CONSENT, "code": k}]}],
            "patient": ref("Patient", pid), "dateTime": S.D["today"],
            "provision": {"type": "permit" if on else "deny",
                          "purpose": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActReason", "code": "HPRGRP" if k != "outreach" else "PATADMIN"}],
                          "class": [{"system": CS_CONSENT, "code": k}]},
        })
    return out


def task(S, hid: str) -> dict | None:
    h = S.households[hid]
    if not h.get("slot"):
        return None
    start = f"{h['slot']['date']}T{h['slot']['time'][:5]}:00+04:00"
    return {
        "resourceType": "Task", "id": f"{hid}-fhd", "status": "requested", "intent": "plan",
        "priority": "urgent" if h["rank"] <= 50 else "routine",
        "code": {"text": "Family Health Day outreach"}, "for": ref("Group", hid),
        "authoredOn": S.D["today"], "executionPeriod": {"start": start},
        "input": [{"type": {"text": "timing rationale"}, "valueString": "; ".join(h["slot"]["why"]) or "earliest suitable slot"}],
        "note": [{"text": DISCLAIMER}],
    }


def communication_request(S, hid: str) -> dict | None:
    h = S.households[hid]
    if not h.get("slot"):
        return None
    cp = S.people[h["contact"]]
    n = sum(1 for m in h["members"] if S.visible_gaps(m) and S.consent[m]["outreach"])
    if not S.consent[h["contact"]]["outreach"] or n == 0:
        status = "revoked"
    else:
        status = "active"
    text = (f"Hello {cp['first']}, this is Abu Dhabi Public Health Centre. {n} member(s) of your family are due for routine "
            f"preventive check-ups. We have reserved one Family Health Day: {h['slot']['date']} at {h['slot']['time'][:5]}, "
            f"{h['district']}. Reply 1 to confirm, 2 for another time, 3 to talk to your doctor first, or STOP.")
    return {
        "resourceType": "CommunicationRequest", "id": f"{hid}-invite", "status": status, "subject": ref("Group", hid),
        "category": [{"text": "preventive-care invitation"}], "priority": "routine",
        "medium": [{"text": h["channel"]}], "recipient": [ref("Patient", h["contact"])],
        "payload": [{"contentString": text}],
        "extension": [{"url": f"{BASE}/StructureDefinition/language", "valueCode": LANG.get(h["lang"], "en")}],
        "about": [ref("Task", f"{hid}-fhd")],
    }


def bundle(resources: list[dict], btype: str = "collection") -> dict:
    res = [r for r in resources if r]
    return {"resourceType": "Bundle", "type": btype, "total": len(res),
            "entry": [{"fullUrl": f"{BASE}/{r['resourceType']}/{r['id']}", "resource": r} for r in res]}


def capability() -> dict:
    rs = ["Patient", "Group", "RelatedPerson", "DetectedIssue", "ImmunizationRecommendation", "RiskAssessment",
          "Consent", "Task", "CommunicationRequest", "AuditEvent"]
    return {"resourceType": "CapabilityStatement", "status": "active", "kind": "instance", "fhirVersion": "4.0.1",
            "format": ["json"], "date": date.today().isoformat(), "software": {"name": "S.C.O.P.E API", "version": "1.0"},
            "rest": [{"mode": "server", "resource": [{"type": t, "interaction": [{"code": "read"}]} for t in rs],
                      "operation": [{"name": "care-gaps", "definition": f"{BASE}/OperationDefinition/care-gaps"},
                                    {"name": "family-plan", "definition": f"{BASE}/OperationDefinition/family-plan"}]}]}


def audit_event(ev: dict, i: int) -> dict:
    return {"resourceType": "AuditEvent", "id": f"ae-{i}",
            "type": {"system": "http://terminology.hl7.org/CodeSystem/audit-event-type", "code": "rest"},
            "action": ev["action"], "recorded": ev["recorded"], "outcome": ev["outcome"],
            "purposeOfEvent": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActReason", "code": ev["purpose"]}]}],
            "agent": [{"who": {"display": ev["actor"]}, "role": [{"text": ev["role"]}], "requestor": True}],
            "source": {"observer": {"display": "S.C.O.P.E API"}},
            "entity": [{"what": {"display": ev["entity"]}}]}


def _plus_years(iso: str, n: int) -> str:
    y, m, d = map(int, iso.split("-"))
    return f"{y + n:04d}-{m:02d}-{min(d, 28):02d}"


LOINC = {"sbp": ("8480-6", "Systolic blood pressure", "mm[Hg]"), "dbp": ("8462-4", "Diastolic blood pressure", "mm[Hg]"),
         "bmi": ("39156-5", "Body mass index", "kg/m2"), "waist": ("8280-0", "Waist circumference", "cm"),
         "a1c": ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%"), "hb": ("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL"),
         "mcv": ("787-2", "MCV [Entitic volume]", "fL"), "ldl": ("2089-1", "Cholesterol in LDL [Moles/volume] in Serum or Plasma", "mmol/L"),
         "rbg": ("2339-0", "Glucose [Mass/volume] in Blood", "mmol/L")}
CS_FINDING = f"{BASE}/CodeSystem/visit-finding"
CS_PURPOSE = f"{BASE}/CodeSystem/visit-purpose"


def practitioner(S, did: str) -> dict:
    x = S.clinicians[did]
    return {"resourceType": "Practitioner", "id": did, "name": [{"text": x["name"]}],
            "communication": [{"text": l} for l in x["languages"]],
            "meta": {"tag": [{"system": f"{BASE}/tags", "code": "synthetic"}]}}


def practitioner_role(S, did: str) -> dict:
    x = S.clinicians[did]
    return {"resourceType": "PractitionerRole", "id": f"{did}-role", "practitioner": ref("Practitioner", did),
            "location": [ref("Location", x["clinic"])], "code": [{"text": x["role"]}]}


def location(S, lid: str) -> dict:
    x = S.clinics[lid]
    return {"resourceType": "Location", "id": lid, "name": x["name"], "status": "active",
            "address": {"district": x["district"], "city": x["region"], "state": "Abu Dhabi", "country": "AE"},
            "hoursOfOperation": [{"daysOfWeek": ["mon", "tue", "wed", "thu", "fri"] + (["sat"] if x["saturday"] else [])}]}


def appointment(S, aid: str) -> dict:
    a = S.appointments[aid]
    status = "fulfilled" if aid in S.encounters else "booked"
    return {"resourceType": "Appointment", "id": aid, "status": status,
            "serviceType": [{"text": "Family Health Day"}],
            "reasonCode": [{"coding": [{"system": CS_PURPOSE, "code": k}], "text": S.D["purposes"][k]["label"]} for k in a["purposes"]],
            "start": f"{a['date']}T{a['start']}:00+04:00", "end": f"{a['date']}T{a['end']}:00+04:00", "minutesDuration": a["minutes"],
            "participant": [{"actor": ref("Patient", a["pid"]), "status": "accepted"},
                            {"actor": ref("Practitioner", a["clinician"]), "status": "accepted", "type": [{"text": "treating physician" if a["continuity"] else "covering clinician"}]},
                            {"actor": ref("Location", a["clinic"]), "status": "accepted"}],
            "extension": [{"url": f"{BASE}/StructureDefinition/interpreter-needed", "valueBoolean": a["interpreter"]},
                          {"url": f"{BASE}/StructureDefinition/household", "valueReference": ref("Group", a["hh"])}]}


def encounter_resources(S, aid: str, enc: dict, practitioner_id: str) -> list[dict]:
    a = S.appointments[aid]; pid = a["pid"]; eid = f"{aid}-enc"; subj = ref("Patient", pid); e_ref = ref("Encounter", eid)
    out = [{"resourceType": "Encounter", "id": eid, "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
            "subject": subj, "appointment": [ref("Appointment", aid)], "serviceProvider": ref("Location", a["clinic"]),
            "participant": [{"individual": ref("Practitioner", practitioner_id)}],
            "period": {"start": f"{a['date']}T{a['start']}:00+04:00", "end": f"{a['date']}T{a['end']}:00+04:00"},
            "reasonCode": [{"coding": [{"system": CS_PURPOSE, "code": k}]} for k in a["purposes"]]}]
    for k, v in (enc.get("findings") or {}).items():
        if v in ("", None, False):
            continue
        obs = {"resourceType": "Observation", "id": f"{eid}-{k}", "status": "final", "subject": subj, "encounter": e_ref,
               "effectiveDateTime": f"{a['date']}T{a['start']}:00+04:00"}
        if k in LOINC and not isinstance(v, bool):
            code, disp, unit = LOINC[k]
            obs["code"] = {"coding": [{"system": "http://loinc.org", "code": code, "display": disp}]}
            obs["valueQuantity"] = {"value": float(v), "unit": unit, "system": "http://unitsofmeasure.org", "code": unit}
        else:
            obs["code"] = {"coding": [{"system": CS_FINDING, "code": k}]}
            obs["valueString" if not isinstance(v, bool) else "valueBoolean"] = v
        out.append(obs)
    for i, code in enumerate(enc.get("icd") or []):
        out.append({"resourceType": "Condition", "id": f"{eid}-dx{i}", "subject": subj, "encounter": e_ref,
                    "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": code}]},
                    "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "provisional"}]}})
    for i, r in enumerate(enc.get("referrals") or []):
        out.append({"resourceType": "ServiceRequest", "id": f"{eid}-ref{i}", "status": "active", "intent": "order", "subject": subj,
                    "encounter": e_ref, "code": {"text": r["to"]}, "category": [{"text": "referral"}], "occurrencePeriod": {"end": r["by"]},
                    "requester": ref("Practitioner", practitioner_id)})
    for i, lab in enumerate(enc.get("labs") or []):
        out.append({"resourceType": "ServiceRequest", "id": f"{eid}-lab{i}", "status": "active", "intent": "order", "subject": subj,
                    "encounter": e_ref, "code": {"text": lab}, "category": [{"text": "laboratory"}], "requester": ref("Practitioner", practitioner_id)})
    for i, v in enumerate(enc.get("vaccines") or []):
        out.append({"resourceType": "Immunization", "id": f"{eid}-imm{i}", "status": "completed", "patient": subj, "encounter": e_ref,
                    "vaccineCode": {"text": v}, "occurrenceDateTime": a["date"], "performer": [{"actor": ref("Practitioner", practitioner_id)}]})
    for i, c in enumerate(enc.get("counselling") or []):
        out.append({"resourceType": "Procedure", "id": f"{eid}-cou{i}", "status": "completed", "subject": subj, "encounter": e_ref,
                    "code": {"text": c}, "category": {"text": "counselling"}})
    out.append({"resourceType": "ClinicalImpression", "id": f"{eid}-impression", "status": "completed", "subject": subj, "encounter": e_ref,
                "assessor": ref("Practitioner", practitioner_id),
                "finding": [{"itemCodeableConcept": {"text": f"{S.D['purposes'][k]['label']}: {enc.get('conclusions', {}).get(k, '')}"}} for k in a["purposes"]],
                "summary": (enc.get("note") or "")[:4000]})
    return out
