"""
S.C.O.P.E core store: loads the engine output and recomputes risk, confidence,
visible gaps and priority under a person's current consent state.

The logic mirrors the browser's live() function so the console, the family
app and the API always agree.
"""
from __future__ import annotations

import json
import math
import threading
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSENT_KEYS = ("genomic", "family_link", "social", "outreach")


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


class Store:
    def __init__(self, scope_json: Path | None = None, population_json: Path | None = None):
        scope_json = scope_json or ROOT / "data" / "scope.json"
        population_json = population_json or ROOT / "data" / "population.json"
        self.D = json.loads(Path(scope_json).read_text())
        pop = json.loads(Path(population_json).read_text())
        self.people = self.D["people"]
        self.households = {h["id"]: h for h in self.D["households"]}
        self.models = self.D["models"]
        self.raw = {p["id"]: p for p in pop["people"]}           # dob, sex, language source
        self.hh_raw = {h["id"]: h for h in pop["households"]}
        self.consent = {pid: dict(zip(CONSENT_KEYS, map(bool, p["consent"]))) for pid, p in self.people.items()}
        self._lock = threading.Lock()
        self.audit: list[dict] = []
        self.appointments = {a["id"]: a for a in self.D.get("appointments", [])}
        self.clinicians = {x["id"]: x for x in self.D.get("clinicians", [])}
        self.clinics = {x["id"]: x for x in self.D.get("clinics", [])}
        self.encounters: dict[str, dict] = {}
        self.closed: set[tuple[str, int]] = set()

    # ------------------------------------------------------------ consent
    def set_consent(self, pid: str, key: str, value: bool) -> None:
        if key not in CONSENT_KEYS:
            raise KeyError(key)
        if key == "genomic" and not self.people[pid]["genomic_available"]:
            raise ValueError("no genomic result on record for this person")
        with self._lock:
            self.consent[pid][key] = bool(value)

    def consent_changed(self, pid: str) -> bool:
        orig = self.people[pid]["consent"]
        return any(self.consent[pid][k] != bool(orig[i]) for i, k in enumerate(CONSENT_KEYS))

    # ------------------------------------------------------------ gaps
    def gap_visible(self, pid: str, g: dict) -> bool:
        if g["r"].startswith("CASCADE") and g.get("via") in self.people:
            cv, cp = self.consent[g["via"]], self.consent[pid]
            return cv["genomic"] and cv["family_link"] and cp["family_link"]
        return True

    def visible_gaps(self, pid: str) -> list[dict]:
        return [g for i, g in enumerate(self.people[pid]["gaps"]) if self.gap_visible(pid, g) and (pid, i) not in self.closed]

    def may_sign(self, practitioner: str, appt: dict) -> bool:
        """The booked clinician, or a colleague with the same role at the same clinic (cover)."""
        if practitioner == appt["clinician"]:
            return True
        me, booked = self.clinicians.get(practitioner), self.clinicians[appt["clinician"]]
        return bool(me and me["clinic"] == booked["clinic"] and me["role"] == booked["role"])

    def record_encounter(self, appt_id: str, enc: dict) -> list[int]:
        a = self.appointments[appt_id]
        p = self.people[a["pid"]]
        rp = self.D["rule_purpose"]
        closed = [i for i, g in enumerate(p["gaps"]) if rp.get(g["r"]) in a["purposes"] and self.gap_visible(a["pid"], g)]
        with self._lock:
            self.encounters[appt_id] = {**enc, "appt": appt_id, "pid": a["pid"], "closed": closed}
            self.closed.update((a["pid"], i) for i in closed)
        return closed

    # ------------------------------------------------------------ risk
    def live(self, pid: str) -> dict:
        p, c = self.people[pid], self.consent[pid]
        out = {"risk": None, "lo": None, "hi": None, "rr": 1.0, "factors": [], "model": None}
        if p.get("score") and p.get("feat"):
            mk = p["score"]["model"]
            m = self.models[mk]
            f, x = m["features"], list(p["feat"])

            def put(k, v):
                if k in f:
                    x[f.index(k)] = v

            if mk == "adult" and not c["genomic"]:
                put("fh_variant", 0.0); put("genomic_not_available", 1.0)
            if mk == "child":
                if not c["family_link"]:
                    put("consanguinity", 0.0); put("family_hx_developmental", 0.0); put("family_data_not_shared", 1.0)
                if not c["social"]:
                    put("high_screen_time", 0.0)
            z = m["intercept"] + p.get("off", 0.0) + sum(ci * xi for ci, xi in zip(m["coef"], x))
            r = _sig(z)
            w0, w1 = p["score"]["risk"] - p["score"]["lo"], p["score"]["hi"] - p["score"]["risk"]
            out.update(risk=r, lo=max(0.0, r - w0), hi=min(1.0, r + w1), rr=r / m["prevalence"], model=mk)
            contrib = [(m["labels"][i], m["coef"][i] * (x[i] - m["means"][i])) for i in range(len(f))]
            out["factors"] = [(lab, v) for lab, v in sorted(contrib, key=lambda t: -abs(t[1])) if abs(v) > 0.05][:4]
        # completeness / confidence
        o = p["consent"]
        comp = p["completeness"]
        if p["genomic_available"]:
            comp += 0.2 * (int(c["genomic"]) - o[0])
        comp += 0.2 * (int(c["family_link"]) - o[1]) + 0.2 * (int(c["social"]) - o[2])
        comp = max(0.0, min(1.0, comp))
        width = (out["hi"] - out["lo"]) if out["hi"] is not None else 0.0
        conf = ("insufficient data" if comp < 0.4 else "high" if comp >= 0.8 and width < 0.12
                else "medium" if comp >= 0.6 else "low")
        out["completeness"], out["confidence"] = comp, (conf if self.consent_changed(pid) else p["confidence"])
        # priority
        gaps = self.visible_gaps(pid)
        need = sum(self.D["gap_weight"].get(g["r"], 1.0) * (1.3 if g["s"] == "overdue" else 1.0) for g in gaps)
        rr = min(out["rr"], 4.0) if p.get("score") else 1.0
        if any(g["r"].startswith("CASCADE") for g in gaps):
            rr = max(rr, 2.5)
        if any(g["r"] == "WCV-MCHAT-REF" for g in gaps):
            rr = max(rr, 3.0)
        out["priority"] = need * (0.5 + 0.5 * rr) * (0.6 + (1 - p["p_attend"])) if c["outreach"] else 0.0
        out["gaps"] = gaps
        return out

    # ------------------------------------------------------------ audit
    def log(self, *, actor: str, role: str, action: str, entity: str, purpose: str, outcome: str = "0") -> dict:
        from datetime import datetime, timezone
        ev = {"recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"), "actor": actor, "role": role,
              "action": action, "entity": entity, "purpose": purpose, "outcome": outcome}
        with self._lock:
            self.audit.append(ev)
        return ev

    def snapshot(self) -> dict:
        return deepcopy(self.consent)
