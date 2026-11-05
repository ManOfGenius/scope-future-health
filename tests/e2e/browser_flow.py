import asyncio
from playwright.async_api import async_playwright
URL = "file://" + str(__import__("pathlib").Path(__file__).resolve().parents[2] / "web/dist/scope.html") + ""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        errs = []
        for scheme, w, h in (("light", 1360, 900), ("dark", 1360, 900), ("dark", 400, 860)):
            ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme)
            pg = await ctx.new_page()
            pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" and "TUNNEL" not in m.text else None)
            pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
            await pg.goto(URL, wait_until="domcontentloaded"); await pg.wait_for_timeout(700)
            for v in ("home", "overview", "worklist", "family", "family-app", "safeguards", "outcomes", "governance"):
                await pg.evaluate(f"location.hash='{v}'"); await pg.wait_for_timeout(250)
                if await pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): errs.append(f"overflow {v} {w}")
                if v in ("home", "family-app"): await pg.screenshot(path=f"/tmp/scope-shots-s-{v}-{scheme}-{w}.png", full_page=True)
            if w > 500 and scheme == "light":
                # theme toggle
                await pg.evaluate("location.hash='home'"); await pg.wait_for_timeout(200)
                await pg.click("#themebtn"); await pg.wait_for_timeout(200)
                print("theme after toggle:", await pg.evaluate("document.documentElement.dataset.theme"), await pg.inner_text("#themebtn"))
                await pg.screenshot(path="/tmp/scope-shots-s-home-toggled-dark.png")
                await pg.click("#themebtn"); await pg.wait_for_timeout(100)
                # family app flow
                await pg.evaluate("location.hash='family-app'"); await pg.wait_for_timeout(300)
                await pg.click("#fa-chat .qr button[data-r='1']"); await pg.wait_for_timeout(150)
                await pg.click("#fa-chat .qr button[data-alt='0']"); await pg.wait_for_timeout(150)
                await pg.click("#fa-open"); await pg.wait_for_timeout(150)
                await pg.click("#fa-login"); await pg.wait_for_timeout(150)
                await pg.click("#fa-phone [data-mem]"); await pg.wait_for_timeout(150)
                await pg.screenshot(path="/tmp/scope-shots-s-fa-member.png")
                await pg.click("#fa-phone [data-scr='choices']"); await pg.wait_for_timeout(150)
                tg = await pg.evaluate("[...document.querySelectorAll('#fa-phone .tog input:not(:disabled)')].map(i=>i.id)")
                await pg.click(f"label:has(#{tg[1]})"); await pg.wait_for_timeout(150)
                for st in (1, 2, 3):
                    await pg.click(f"[data-stage='{st}']"); await pg.wait_for_timeout(120)
                await pg.click("#fa-phone [data-ui='ar']"); await pg.wait_for_timeout(150)
                has_letter = await pg.evaluate("!!document.querySelector(\"#fa-phone [data-scr='letter']\")")
                if has_letter:
                    await pg.click("#fa-phone [data-scr='letter']"); await pg.wait_for_timeout(150)
                    s = await pg.query_selector("#fa-send")
                    if s: await s.click(); await pg.wait_for_timeout(150)
                print("letter tab:", has_letter, "chat bubbles:", await pg.evaluate("document.querySelectorAll('#fa-chat .bubble, #fa-chat .reply').length"),
                      "sync note:", await pg.evaluate("!!document.querySelector('.fa-side .sync')"))
                await pg.screenshot(path="/tmp/scope-shots-s-fa-flow-ar.png", full_page=True)
            await ctx.close()
        await b.close()
        print("ERRORS:", errs)
asyncio.run(main())
