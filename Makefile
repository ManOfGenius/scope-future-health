# S.C.O.P.E build pipeline (Python 3.11+, numpy, scikit-learn, scipy)
.PHONY: all data engine web test bench serve clean
all: data engine web test
data:      ; python3 engine/generate.py
engine:    ; python3 engine/engine.py
web:       ; python3 web/build.py
test:      ; python3 -m pytest -q tests
bench:     ; python3 bench/scale_bench.py
e2e:       ; python3 tests/e2e/browser_flow.py   # needs Chrome + Playwright
serve:     ; python3 -m api.server --port 8080
clean:     ; rm -rf data/*.json web/dist
