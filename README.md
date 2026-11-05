# S.C.O.P.E — Screening & Care Orchestration for Prevention Everywhere

*Every family seen. Every risk reached, in time.*

S.C.O.P.E finds children, adults and households in Abu Dhabi with unmet or elevated preventive need and connects them to the right pathway — Well-Child Visit, immunisation, school health check, IFHAS adult screening, or a risk-based preventive intervention — through one coordinated **Family Health Day**, invited in the family's own language.

Submitted to the **Future Health Digital Innovation Challenge 2026 · Population Health**.

> **All data in this repository is synthetic.** No real patient record is used. Rates are anchored to published UAE figures where available (see *Validation*).

## What it does

| Layer | What happens | Where |
|---|---|---|
| Guideline rules | Due and overdue items from the DoH Well-Child Visit standard (v10, 2025), DoH immunisation schedule (Circular 2026/77), UAE school health guideline (2024), IFHAS (2025), ADPHC lung screening | `engine/guidelines.py`, `engine/engine.py` |
| Calibrated risk | Explainable logistic models (adult cardiometabolic 3-year; child developmental concern), 30 bootstrap refits for intervals, shrinkage recalibration per segment | `engine/engine.py` |
| Family graph | Bundles a household into one visit; index-mediated genetic cascade (FH, HBOC, Lynch) that never discloses a relative's result | `engine/engine.py` |
| Equity guard | Language-by-nationality equity floor; small-cell suppression (n < 11); calibration alerts with exact Poisson intervals | `engine/engine.py` |
| Scheduling | Several clinics per district, clinicians with roles, languages, sessions and capacity; a treating physician per person; one session per household; cover only when capacity forces it; interpreter flagged | `engine/engine.py` |
| Visit purposes | Each open item maps to a predictive purpose (development, anaemia, cardiometabolic, cancer, genetic cascade, immunisation, school check, community check) that sets the clinician role, the slot length and the examination protocol | `engine/guidelines.py` |
| Clinician workspace | Personal schedule, protocol by purpose, guideline decision support, orders, referrals with due dates, ICD-10-CM codes, signed encounters saved to a shared record | `web/app.html` |
| Engagement | Channel, addressee and timing per household (school, shift work, Ramadan); seven-language invitations with no health detail | `web/app.html` |
| Interoperability | FHIR R4 API with roles, purpose-of-use and a full audit trail | `api/` |

## Quick start

```bash
pip install -r requirements.txt
make all        # generate population → run engine → build web app → run tests
make serve      # FHIR API on http://127.0.0.1:8080
make bench      # scalability benchmark
```

Open `web/dist/scope.html` in a browser for the console and the family app.

## API (FHIR R4)

| Method | Path | Returns |
|---|---|---|
| GET | `/fhir/metadata` | CapabilityStatement |
| GET | `/fhir/Patient/{id}` | Patient |
| GET | `/fhir/Patient/{id}/$care-gaps` | Bundle: DetectedIssue, ImmunizationRecommendation, RiskAssessment |
| GET | `/fhir/Group/{hh}/$family-plan` | Bundle: Group, Task, CommunicationRequest, RelatedPerson, DetectedIssue, ImmunizationRecommendation |
| GET | `/fhir/Appointment?patient={id}` | Appointments with Practitioner and Location |
| GET | `/fhir/Practitioner/{id}` · `/fhir/Location/{id}` | Clinician (with PractitionerRole) · clinic |
| POST | `/fhir/Appointment/{id}/$sign-encounter` | Encounter, Observation (LOINC), Condition (ICD-10-CM), ServiceRequest, Immunization, Procedure, ClinicalImpression; closes the visit's open items |
| GET | `/fhir/Consent?patient={id}` | Consent per data category |
| PUT | `/fhir/Consent/{id}-{category}` | Updated Consent + recomputed risk, confidence, priority and affected relatives |
| GET | `/fhir/AuditEvent` | Audit trail (auditor role only) |
| GET | `/api/worklist` | Ranked households (operational) |
| GET | `/api/audit?dim=` | Small-cell-suppressed equity audit |

Every call needs `Authorization: Bearer <token>` and `X-Purpose-Of-Use` (HL7 v3 ActReason). Demo tokens: `practitioner-<ClinicianId>` (TREAT; may sign only their own or a same-role colleague's appointment at the same clinic), `clinician-demo` (TREAT, CAREMGT), `coordinator-demo` (CAREMGT, PATADMIN), `analyst-demo` (PUBHLTH, HOPERAT, aggregates only), `auditor-demo` (HOPERAT), `family-<PersonId>` (PATRQT, own household; may change own and own minors' consent). Production replaces tokens with UAE PASS / DoH identity provider and SMART-on-FHIR scopes.

```bash
curl -H "Authorization: Bearer clinician-demo" -H "X-Purpose-Of-Use: TREAT" \
     http://127.0.0.1:8080/fhir/Patient/P00012/\$care-gaps
```

## Validation (synthetic data)

| | AUC | Share of future cases in top 10% |
|---|---|---|
| S.C.O.P.E adult model | 0.81 | 42% |
| FINDRISC (published score) | 0.77 | 34% |
| Age only (current rule logic) | 0.74 | 31% |

Anchors: diabetes prevalence 20–79 synthetic 20.6% vs IDF 2024 20.7%; undiagnosed share 58% vs 64%.

Outcome simulation (600 people contacted per 90-day cycle, 200 cycles): S.C.O.P.E reaches about twice as many genuinely high-risk people as age/sex rules, and about 1.7× with tailoring effects halved. Tailoring effects are explicit assumptions in `engine/engine.py` (`EFFECTS`).

## Tests

`make test` runs 37 tests covering clinic and clinician assignment, session timing, capacity, treating-physician continuity, Ramadan and shift-work rules, encounter signing rights and FHIR output, guideline windows, sex-specific rules, immunisation schedule conformance, Thiqa eligibility, genomic ethics for minors, consent-gated cascade, small-cell suppression, invitations free of condition names, role and purpose-of-use enforcement, consent recomputation, revoked invitations after opt-out, and audit of refusals.

## Scalability (single laptop core)

From `bench/results.json`: vectorised scoring of 3.8 M people in under 0.1 s; full consent-aware evaluation ≈ 15 µs per person (under a minute for the emirate on one core); `$family-plan` p95 ≈ 0.3 ms in-process.

## Repository

```
engine/   guidelines.py (rule base) · generate.py (synthetic population) · engine.py (gaps, models, cascade, equity, simulation)
api/      core.py (consent-aware store) · fhir.py (R4 mappers) · server.py (WSGI app, auth, audit)
web/      app.html (console + family app) · build.py · emblem
tests/    rules, privacy, API; e2e/ browser flow
bench/    scale_bench.py
data/     generated JSON (synthetic)
```

## Limits

Synthetic data only; real-world performance must be established on Malaffi records in a pilot. Tailoring effects are assumptions. Message translations need native-speaker and clinical review. UAE PASS sign-in is simulated. Rule texts should be re-checked against the full DoH standards at integration.
