"""Bundle the single-file web app: inject the engine output and the emblem as data URIs."""
import base64
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "web"
tpl = (W / "app.html").read_text()
data = (ROOT / "data" / "scope.json").read_text().replace("</", "<\\/")
b64 = lambda p: "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
out = tpl.replace("__LOGO_BIG__", b64(W / "emblem_520.png")).replace("__LOGO_SMALL__", b64(W / "emblem_180.png")).replace("/*__DATA__*/", data)
(W / "dist").mkdir(exist_ok=True)
(W / "dist" / "scope.html").write_text(out)
print("web/dist/scope.html", round(len(out) / 1e6, 2), "MB")
