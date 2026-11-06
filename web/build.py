"""Bundle the single-file web app: inject the engine output and the emblem as data URIs."""
import base64, gzip, io, json
from PIL import Image
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "web"
tpl = (W / "app.html").read_text()
data = base64.b64encode(gzip.compress(json.dumps(json.loads((ROOT / "data" / "scope.json").read_text()), separators=(",", ":")).encode(), 9, mtime=0)).decode()
def b64(p, size):
    im = Image.open(p); im.thumbnail((size, size)); buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
bench = (ROOT / "bench" / "results.json")
tpl = tpl.replace("/*__BENCH__*/null", bench.read_text() if bench.exists() else "null")
out = tpl.replace("__LOGO_BIG__", b64(W / "emblem_520.png", 340)).replace("__LOGO_SMALL__", b64(W / "emblem_180.png", 120)).replace("/*__DATA__*/", data)
(W / "dist").mkdir(exist_ok=True)
(W / "dist" / "scope.html").write_text(out)
print("web/dist/scope.html", round(len(out) / 1e6, 2), "MB")
