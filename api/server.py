"""
S.C.O.P.E API — dependency-free WSGI application.

Run locally:   python -m api.server --port 8080
Production:    any WSGI server (gunicorn "api.server:app") behind TLS and the DoH identity provider.

Access control (demo tokens; production uses UAE PASS / DoH IdP with OAuth2 + SMART scopes):
  clinician-demo    patient-level read, consent read, plan read            purposes TREAT, CAREMGT
  coordinator-demo  patient-level read for outreach, plan read             purposes CAREMGT, PATADMIN
  analyst-demo      aggregated, small-cell-suppressed endpoints only       purpose  PUBHLTH, HOPERAT
  auditor-demo      AuditEvent read                                        purpose  HOPERAT
  family-<Pxxxxx>   own household only; may change own and own minors' consent
Every request is written to the audit trail, including refusals.
"""
from __future__ import annotations

import argparse
import json
import re
from urllib.parse import parse_qs

from . import fhir
from .core import Store, CONSENT_KEYS

ROLES = {"clinician-demo": "clinician", "coordinator-demo": "coordinator", "analyst-demo": "analyst", "auditor-demo": "auditor"}
PURPOSES = {"clinician": {"TREAT", "CAREMGT"}, "coordinator": {"CAREMGT", "PATADMIN"}, "analyst": {"PUBHLTH", "HOPERAT"},
            "auditor": {"HOPERAT"}, "family": {"PATRQT"}}
SMALL = None


class HTTPError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg); self.status, self.msg = status, msg


def outcome(status: int, msg: str) -> dict:
    sev = "error" if status >= 400 else "information"
    return {"resourceType": "OperationOutcome", "issue": [{"severity": sev, "code": "forbidden" if status in (401, 403) else "processing", "diagnostics": msg}]}


class App:
    def __init__(self, store: Store | None = None):
        self.S = store or Store()
        self.routes = [
            ("GET", r"/health", self.health, None),
            ("GET", r"/fhir/metadata", self.metadata, None),
            ("GET", r"/fhir/Patient/(P\d+)", self.get_patient, "person"),
            ("GET", r"/fhir/Patient/(P\d+)/\$care-gaps", self.care_gaps, "person"),
            ("GET", r"/fhir/Group/(H\d+)", self.get_group, "household"),
            ("GET", r"/fhir/Group/(H\d+)/\$family-plan", self.family_plan, "household"),
            ("GET", r"/fhir/Consent", self.get_consent, "person-query"),
            ("PUT", r"/fhir/Consent/(P\d+)-(genomic|family_link|social|outreach)", self.put_consent, "person-consent"),
            ("GET", r"/fhir/AuditEvent", self.audit_events, "audit"),
            ("GET", r"/api/worklist", self.worklist, "operational"),
            ("GET", r"/api/audit", self.equity_audit, "aggregate"),
        ]

    # ---------------------------------------------------------------- auth
    def who(self, environ) -> tuple[str, str, str | None]:
        auth = environ.get("HTTP_AUTHORIZATION", "")
        tok = auth[7:] if auth.startswith("Bearer ") else ""
        if tok in ROLES:
            return tok, ROLES[tok], None
        m = re.fullmatch(r"family-(P\d+)", tok)
        if m and m.group(1) in self.S.people:
            return tok, "family", m.group(1)
        raise HTTPError(401, "missing or unknown bearer token")

    def authorise(self, role: str, self_pid: str | None, scope: str | None, args: tuple, purpose: str, q: dict):
        if scope is None:
            return
        if purpose not in PURPOSES[role]:
            raise HTTPError(403, f"purpose of use '{purpose}' not allowed for role {role}")
        if role == "analyst" and scope != "aggregate":
            raise HTTPError(403, "analysts may only use aggregated, small-cell-suppressed endpoints")
        if role == "auditor" and scope != "audit":
            raise HTTPError(403, "auditors may only read the audit trail")
        if scope == "audit" and role != "auditor":
            raise HTTPError(403, "audit trail is restricted to auditors")
        if role == "family":
            hh = self.S.people[self_pid]["hh"]
            if scope == "household" and args[0] != hh:
                raise HTTPError(403, "family accounts can only see their own household")
            if scope in ("person", "person-consent"):
                target = self.S.people.get(args[0])
                if not target or target["hh"] != hh:
                    raise HTTPError(403, "family accounts can only see their own household")
                if scope == "person-consent" and not self.manages(self_pid, args[0]):
                    raise HTTPError(403, "each adult manages their own data choices")
            if scope == "person-query":
                target = self.S.people.get(q.get("patient", [""])[0])
                if not target or target["hh"] != hh:
                    raise HTTPError(403, "family accounts can only see their own household")
            if scope in ("operational", "aggregate", "audit"):
                raise HTTPError(403, "not available to family accounts")
        if role in ("clinician", "coordinator") and scope == "aggregate":
            return

    def manages(self, actor: str, target: str) -> bool:
        if actor == target:
            return True
        t = self.S.people[target]
        return t["age"] < 18 and actor in (t.get("mother"), t.get("father"))

    # ---------------------------------------------------------------- WSGI
    def __call__(self, environ, start_response):
        method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/")
        q = parse_qs(environ.get("QUERY_STRING", ""))
        purpose = environ.get("HTTP_X_PURPOSE_OF_USE", "")
        actor, role = "anonymous", "none"
        try:
            for mth, pat, fn, scope in self.routes:
                m = re.fullmatch(pat, path)
                if not m or mth != method:
                    continue
                if scope is not None:
                    actor, role, self_pid = self.who(environ)
                    self.authorise(role, self_pid, scope, m.groups(), purpose, q)
                else:
                    self_pid = None
                body = None
                if method in ("PUT", "POST"):
                    n = int(environ.get("CONTENT_LENGTH") or 0)
                    body = json.loads(environ["wsgi.input"].read(n) or b"{}")
                res = fn(*m.groups(), q=q, body=body, actor=actor)
                if scope is not None:
                    self.S.log(actor=actor, role=role, action="U" if method == "PUT" else "R", entity=path, purpose=purpose)
                return self._send(start_response, 200, res)
            raise HTTPError(404, f"no route for {method} {path}")
        except HTTPError as e:
            if e.status in (401, 403):
                self.S.log(actor=actor, role=role, action="R" if method == "GET" else "U", entity=path, purpose=purpose or "-", outcome="4")
            return self._send(start_response, e.status, outcome(e.status, e.msg))
        except (KeyError, ValueError) as e:
            return self._send(start_response, 400, outcome(400, str(e)))

    def _send(self, start_response, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found"}[status]
        start_response(f"{status} {reason}", [("Content-Type", "application/fhir+json; charset=utf-8"), ("Content-Length", str(len(data))),
                                              ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
        return [data]

    # ---------------------------------------------------------------- handlers
    def health(self, **_):
        return {"status": "ok", "people": len(self.S.people), "households": len(self.S.households), "rules": self.S.D["version"]}

    def metadata(self, **_):
        return fhir.capability()

    def get_patient(self, pid, **_):
        return fhir.patient(self.S, pid)

    def care_gaps(self, pid, **_):
        lv = self.S.live(pid)
        gaps = lv["gaps"]
        res = [fhir.detected_issue(self.S, pid, g, i) for i, g in enumerate(gaps) if g["r"] != "VAX"]
        res += [fhir.immunization_recommendation(self.S, pid, gaps), fhir.risk_assessment(self.S, pid, lv)]
        return fhir.bundle(res)

    def get_group(self, hid, **_):
        return fhir.group(self.S, hid)

    def family_plan(self, hid, **_):
        h = self.S.households[hid]
        res = [fhir.group(self.S, hid), fhir.task(self.S, hid), fhir.communication_request(self.S, hid)]
        res += fhir.related_people(self.S, hid)
        for m in h["members"]:
            if not self.S.consent[m]["outreach"]:
                continue
            for i, g in enumerate(self.S.visible_gaps(m)):
                if g["r"] != "VAX":
                    res.append(fhir.detected_issue(self.S, m, g, i))
            res.append(fhir.immunization_recommendation(self.S, m, self.S.visible_gaps(m)))
        return fhir.bundle(res)

    def get_consent(self, q, **_):
        pid = q.get("patient", [""])[0]
        if pid not in self.S.people:
            raise HTTPError(404, "unknown patient")
        return fhir.bundle(fhir.consents(self.S, pid), "searchset")

    def put_consent(self, pid, key, body, **_):
        status = (body or {}).get("provision", {}).get("type")
        if status not in ("permit", "deny"):
            raise HTTPError(400, "body must contain provision.type permit|deny")
        before = self.S.live(pid)
        self.S.set_consent(pid, key, status == "permit")
        after = self.S.live(pid)
        return {"resourceType": "Parameters", "parameter": [
            {"name": "consent", "resource": next(c for c in fhir.consents(self.S, pid) if c["id"] == f"{pid}-{key}")},
            {"name": "riskBefore", "valueDecimal": round(before["risk"], 4) if before["risk"] is not None else None},
            {"name": "riskAfter", "valueDecimal": round(after["risk"], 4) if after["risk"] is not None else None},
            {"name": "confidenceAfter", "valueString": after["confidence"]},
            {"name": "priorityAfter", "valueDecimal": round(after["priority"], 3)},
            {"name": "affectedRelatives", "valueInteger": sum(1 for m in self.S.people.values() if any(g.get("via") == pid for g in m["gaps"]))},
        ]}

    def audit_events(self, **_):
        return fhir.bundle([fhir.audit_event(e, i) for i, e in enumerate(self.S.audit)], "searchset")

    def worklist(self, q, **_):
        lim = min(int(q.get("limit", ["50"])[0]), 500)
        region, lang = q.get("region", [None])[0], q.get("lang", [None])[0]
        rows = []
        for h in self.S.households.values():
            if region and h["region"] != region: continue
            if lang and h["lang"] != lang: continue
            pr = sum(self.S.live(m)["priority"] for m in h["members"])
            if pr <= 0: continue
            rows.append({"household": h["id"], "priority": round(pr, 2), "district": h["district"], "language": h["lang"],
                         "openItems": sum(len(self.S.visible_gaps(m)) for m in h["members"]), "slot": h.get("slot"), "channel": h["channel"]})
        rows.sort(key=lambda r: -r["priority"])
        return {"generated": self.S.D["today"], "count": len(rows), "items": rows[:lim], "note": fhir.DISCLAIMER}

    def equity_audit(self, q, **_):
        dim = q.get("dim", ["Nationality group"])[0]
        if dim not in self.S.D["audit"]:
            raise HTTPError(400, f"dim must be one of {list(self.S.D['audit'])}")
        return {"dimension": dim, "smallCellThreshold": self.S.D["small_cell"], "rows": self.S.D["audit"][dim], "alerts": self.S.D["alerts"]}


app = App()

if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8080); a = ap.parse_args()
    print(f"S.C.O.P.E API on http://127.0.0.1:{a.port}  (try /health, /fhir/metadata)")
    make_server("127.0.0.1", a.port, app).serve_forever()
