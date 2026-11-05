"""Appointments: clinic, clinician, treating physician, timing and capacity constraints."""
import collections
from datetime import date
from guidelines import SESSIONS, FHD_SHARE, CALENDAR_2026_27, PURPOSES

def hm(s): h, m = s.split(":"); return int(h) * 60 + int(m)

def test_every_appointment_is_at_the_households_district(data):
    H = {h["id"]: h for h in data["households"]}; L = {c["id"]: c for c in data["clinics"]}
    for a in data["appointments"]:
        assert L[a["clinic"]]["district"] == H[a["hh"]]["district"]

def test_clinician_works_at_that_clinic_and_has_the_right_role(data):
    C = {c["id"]: c for c in data["clinicians"]}
    for a in data["appointments"]:
        assert C[a["clinician"]]["clinic"] == a["clinic"]
        assert C[a["clinician"]]["role"] == a["role"]
        needs = {PURPOSES[k]["role"] for k in a["purposes"]} - {"Nurse"}
        if needs: assert a["role"] != "Nurse", a
        if a["role"] == "Paediatrician": assert data["people"][a["pid"]]["age"] < 18

def test_household_seen_in_one_session(data):
    by = collections.defaultdict(set)
    for a in data["appointments"]: by[a["hh"]].add((a["clinic"], a["date"], a["session"]))
    assert all(len(v) == 1 for v in by.values())

def test_treating_physician_continuity_above_90_percent(data):
    phys = [a for a in data["appointments"] if a["role"] != "Nurse"]
    assert sum(a["continuity"] for a in phys) / len(phys) >= 0.9

def test_capacity_never_exceeded(data):
    used = collections.Counter()
    for a in data["appointments"]: used[(a["clinician"], a["date"], a["session"])] += a["minutes"]
    for (cl, d, s), m in used.items():
        cap = (hm(SESSIONS[s]["end"]) - hm(SESSIONS[s]["start"])) * FHD_SHARE
        assert m <= cap, (cl, d, s, m)

def test_times_fall_inside_their_session(data):
    for a in data["appointments"]:
        s = SESSIONS[a["session"]]
        assert hm(s["start"]) <= hm(a["start"]) and hm(a["end"]) <= hm(s["end"])
        assert date.fromisoformat(a["date"]).weekday() in s["days"]

def test_calendar_rules(data):
    cal = [(date.fromisoformat(c["start"]), date.fromisoformat(c["end"]), c["rule"]) for c in CALENDAR_2026_27]
    for a in data["appointments"]:
        d = date.fromisoformat(a["date"])
        rules = [r for s, e, r in cal if s <= d <= e]
        assert "avoid" not in rules, a
        if any(r.startswith("evening") for r in rules): assert a["session"] == "ramadan_evening", a

def test_shift_workers_only_friday_afternoon_or_weekend(data):
    H = {h["id"]: h for h in data["households"]}
    for a in data["appointments"]:
        if H[a["hh"]]["shift_work"]: assert a["session"] in ("friday_afternoon", "saturday_morning", "ramadan_evening"), a

def test_saturday_only_at_saturday_clinics_and_rota(data):
    L = {c["id"]: c for c in data["clinics"]}; C = {c["id"]: c for c in data["clinicians"]}
    for a in data["appointments"]:
        if a["session"] == "saturday_morning":
            assert L[a["clinic"]]["saturday"] and C[a["clinician"]]["saturday"]
