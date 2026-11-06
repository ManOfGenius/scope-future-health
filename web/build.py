"""Bundle the single-file web app: inject the engine output and the emblem as data URIs."""
import base64, gzip, io, json, re
import markdown
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
def doc(md_path):
    """Markdown -> HTML for the Documents view: figures inlined, wide tables scrollable, external links in a new tab."""
    md = md_path.read_text(encoding="utf-8")
    conv = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
    html = conv.convert(md)
    def img(m):
        im = Image.open(md_path.parent / m.group(1)).convert("RGB"); im.thumbnail((1400, 1400)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        return 'src="data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode() + '"'
    html = re.sub(r'src="(img/[^"]+)"', img, html)
    html = html.replace("<table>", '<div class="tbl-wrap"><table>').replace("</table>", "</table></div>")
    html = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', html)
    html = html.replace('href="business-case.md"', 'href="#docs"').replace('href="technical-documentation.md"', 'href="#docs-technical"')
    toc = [(t["id"], t["name"]) for t in conv.toc_tokens[0]["children"]] if conv.toc_tokens else []
    return {"html": html, "toc": toc}
D = ROOT / "docs"
docs = {"business": doc(D / "business-case.md"), "technical": doc(D / "technical-documentation.md")} if (D / "business-case.md").exists() else None
tpl = tpl.replace("/*__DOCS__*/null", json.dumps(docs).replace("</", "<\\/"))
out = tpl.replace("__LOGO_BIG__", b64(W / "emblem_520.png", 340)).replace("__LOGO_SMALL__", b64(W / "emblem_180.png", 120)).replace("/*__DATA__*/", data)
(W / "dist").mkdir(exist_ok=True)
(W / "dist" / "scope.html").write_text(out)
print("web/dist/scope.html", round(len(out) / 1e6, 2), "MB")
