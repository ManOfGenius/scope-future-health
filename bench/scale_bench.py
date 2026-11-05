"""Scalability evidence: score the whole emirate, measure per-person engine cost and API latency."""
import io, json, statistics, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from api.core import Store
from api.server import App

S = Store(); D = S.D; m = D["models"]["adult"]
rng = np.random.default_rng(0)
res = {}
# 1) vectorised risk scoring at emirate scale (feature vectors resampled from the synthetic adults)
adults = np.array([p["feat"] for p in D["people"].values() if p.get("score") and p["score"]["model"] == "adult"])
coef, b0 = np.array(m["coef"]), m["intercept"]
for n in (1_000_000, 3_800_000):
    X = adults[rng.integers(0, len(adults), n)]
    t = time.perf_counter(); z = X @ coef + b0; pr = 1 / (1 + np.exp(-z)); dt = time.perf_counter() - t
    res[f"vectorised_scoring_{n}"] = round(dt, 3)
# 2) full per-person live evaluation (consent-aware gaps + risk + priority), pure Python, one core
ids = list(D["people"]); t = time.perf_counter()
for pid in ids: S.live(pid)
per = (time.perf_counter() - t) / len(ids)
res["live_eval_us_per_person"] = round(per * 1e6, 1)
res["live_eval_3_8M_minutes_one_core"] = round(per * 3.8e6 / 60, 1)
res["live_eval_3_8M_minutes_16_cores"] = round(per * 3.8e6 / 60 / 16, 2)
# 3) API latency for the heaviest read ($family-plan), in-process WSGI
app = App(S); lat = []
hh = [h["id"] for h in D["households"]][:500]
for hid in hh:
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": f"/fhir/Group/{hid}/$family-plan", "QUERY_STRING": "", "wsgi.input": io.BytesIO(b""),
           "HTTP_AUTHORIZATION": "Bearer coordinator-demo", "HTTP_X_PURPOSE_OF_USE": "CAREMGT"}
    t = time.perf_counter(); b"".join(app(env, lambda s, h: None)); lat.append((time.perf_counter() - t) * 1000)
lat.sort()
res["family_plan_ms_p50"] = round(statistics.median(lat), 2); res["family_plan_ms_p95"] = round(lat[int(0.95 * len(lat))], 2)
print(json.dumps(res, indent=1))
(ROOT / "bench" / "results.json").write_text(json.dumps(res, indent=1))
