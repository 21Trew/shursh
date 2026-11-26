"""PR #4 acceptance: six authenticated tabs × four responsive viewports.

Runs only against browser_http, a localhost Flask server backed by disposable
shursh_ci PostgreSQL; Supabase Auth transport is mocked by the test fixture.
Never execute this module against a hosted database or a real user account.

MutationObserver counts DOM mutations, NOT browser paint/compositor frames.
The navigation time is browser performance.now() through the E2E readiness
assertion (includes the automation scheduling/polling overhead).
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect

from test_cloud import browser_http, browser_login, application, db_setup

ROUTES = (
    ("/", "С возвращением", 'header .nav [data-nav="/"]'),
    ("/lists", "Вишлисты", 'header .nav [data-nav="/lists"]'),
    ("/santas", "Тайный Санта", 'header .nav [data-nav="/santas"]'),
    ("/friends", "Друзья", 'header .nav [data-nav="/friends"]'),
    ("/profile", "Мой профиль", 'header .nav [data-nav="/profile"]'),
    ("/notifications", "Уведомления", "header .header-bell"),
)
VIEWPORTS = (375, 390, 768, 1024, 1440)



@pytest.fixture
def browser_https(application, tmp_path):
    """HTTPS test origin is required: WebKit does not persist Secure cookies
    on HTTP localhost, while all real Production auth uses HTTPS.
    Only the CI-local Flask application and disposable database are used.
    """
    import subprocess
    import threading
    from werkzeug.serving import make_server, WSGIRequestHandler

    cert=tmp_path/"localhost.crt"
    key=tmp_path/"localhost.key"
    subprocess.run(
        ["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
         "-subj","/CN=localhost","-addext",
         "subjectAltName=DNS:localhost,IP:127.0.0.1",
         "-keyout",str(key),"-out",str(cert)],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,
    )
    class PrivateHttpsHandler(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            pass

    server=make_server(
        "127.0.0.1",0,application,threaded=True,
        ssl_context=(str(cert),str(key)),
        request_handler=PrivateHttpsHandler,
    )
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        yield f"https://localhost:{server.server_port}"
    finally:
        server.shutdown()
        worker.join(timeout=5)
OUTPUT = Path("artifacts/pr4-ui")

AUDIT_JS = r"""() => {
  const root = document.querySelector('#app');
  if (!root) throw new Error('App root missing');
  const seen = new WeakSet();
  root.querySelectorAll('*').forEach(el => seen.add(el));
  seen.add(root);
  const empty = () => ({mutationRecords:0, attributes:0, characterData:0,
    childList:0, addedElements:0, removedElements:0,
    newElements:0, reusedElements:0});
  const audit = {counts:empty(), started:0};
  const inspect = (node, added) => {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const all = [node, ...node.querySelectorAll('*')];
    audit.counts[added ? 'addedElements' : 'removedElements'] += all.length;
    if (added) for (const el of all) {
      if (seen.has(el)) audit.counts.reusedElements++;
      else {seen.add(el);audit.counts.newElements++;}
    }
  };
  const tally = records => {
    for (const record of records) {
      audit.counts.mutationRecords++;
      audit.counts[record.type]++;
      if (record.type === 'childList') {
        record.addedNodes.forEach(n => inspect(n, true));
        record.removedNodes.forEach(n => inspect(n, false));
      }
    }
  };
  const observer = new MutationObserver(tally);
  observer.observe(root,{subtree:true,childList:true,attributes:true,
                         characterData:true});
  audit.begin = () => {
    observer.takeRecords(); // ignore mutations from the previous navigation
    audit.counts = empty();
    audit.started = performance.now();
  };
  audit.end = () => {
    tally(observer.takeRecords());
    return {...audit.counts,
      observedNavMs:Math.round((performance.now()-audit.started)*10)/10};
  };
  window.__pr4Audit = audit;
}"""


def _layout(page, width, path):
    return page.evaluate("""({width, path}) => {
      const doc = document.documentElement;
      const header = document.querySelector('.site-header');
      const footer = document.querySelector('footer');
      const bell = header?.querySelector('.header-bell');
      const main = document.querySelector('#page-view main');
      const nav = header?.querySelector('.nav');
      const r = el => {
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return {x:Math.round(b.x), right:Math.round(b.right),
                width:Math.round(b.width), height:Math.round(b.height)};
      };
      return {width,path,docWidth:doc.scrollWidth,viewport:innerWidth,
        header:r(header),footer:r(footer),main:r(main),bell:r(bell),
        nav:r(nav),navScrollWidth:nav?.scrollWidth||0,
        navClientWidth:nav?.clientWidth||0,
        hasMetrics:!!document.querySelector('.dashboard-metrics'),
        hasHeaderNotificationsNav:!!nav?.querySelector('[data-nav="/notifications"]'),
        hasEmojiAvatar:!!main?.querySelector('.emoji-avatar'),
        errorVisible:!!main?.querySelector('.error-page'),
        heading:main?.querySelector('h1')?.textContent?.trim()||''};
    }""", {"width":width,"path":path})


@pytest.mark.browser
def test_pr4_six_tabs_dom_http_timings_and_all_viewports(browser_http):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    findings = []
    errors = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for width in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width":width,"height":860},
                    device_scale_factor=1,
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(browser_http + "/", wait_until="domcontentloaded")
                browser_login(page)
                expect(page.locator(".dashboard-page")).to_be_visible()
                expect(page.locator("header .header-bell")).to_be_visible()
                page.wait_for_function("() => typeof ownerWarmupReady !== 'undefined' && ownerWarmupReady && !socialUnreadBusy",timeout=15000)
                page.evaluate("""() => {
                    window.__pr4Header = document.querySelector("header");
                    window.__pr4Footer = document.querySelector("footer");
                }""")
                page.locator("main").evaluate(
                    "(el) => el.dataset.acceptanceTab = '/'"
                )
                page.evaluate(AUDIT_JS)
                requests = []
                page.on("request", lambda request: requests.append({
                    "method":request.method,
                    "url":request.url,
                }) if request.url.startswith(browser_http) else None)

                # First visits load data, warm visits must use the original
                # six DOM trees without new API reads or reconstruction.
                for phase, routes in (
                    ("cold", ROUTES[1:]),
                    ("warm", ROUTES),
                ):
                    for path, heading, selector in routes:
                        before = len(requests)
                        page.evaluate("window.__pr4Audit.begin()")
                        (page.evaluate("() => nav('/notifications')") if path=='/notifications' else page.locator(selector).click())
                        expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                        expect(page.locator("#page-view")).not_to_have_attribute(
                            "aria-busy", "true"
                        )
                        dom = page.evaluate("window.__pr4Audit.end()")
                        calls = requests[before:]
                        api = [r for r in calls
                               if urlsplit(r["url"]).path.startswith("/api/")]
                        layout = _layout(page, width, path)
                        findings.append({
                            "width":width,"phase":phase,"tab":path,
                            "dom":dom,"httpRequests":len(calls),
                            "apiRequests":len(api),
                            "apiByMethod":{
                                method:sum(r["method"] == method for r in api)
                                for method in ("GET","POST","PATCH","DELETE")
                            },
                            "layout":layout
                        })
                        assert not layout["errorVisible"], (width, phase, path)
                        assert layout["docWidth"] <= width + 2, (
                            "Page-wide horizontal overflow",width,phase,path,
                            layout["docWidth"]
                        )
                        assert layout["header"] and layout["footer"] and layout["main"]
                        assert layout["bell"] and layout["bell"]["width"] >= 40
                        assert not layout["hasHeaderNotificationsNav"]
                        assert not layout["hasMetrics"]
                        if path == "/profile":
                            assert layout["hasEmojiAvatar"]
                        if phase == "cold":
                            page.locator("main").evaluate(
                                "(el, key) => el.dataset.acceptanceTab = key",
                                path
                            )
                        else:
                            assert page.locator("main").get_attribute(
                                "data-acceptance-tab"
                            ) == path, ("DOM tree was rebuilt",width,path)
                            assert dom["newElements"] == 0, (
                                "New elements during cached tab return",
                                width,path,dom
                            )
                            assert not api, ("Unexpected warm navigation API",width,path,api)
                        # Screenshots contain only fake CI fixture users, no
                        # real cookies, credentials, or hosted account details.
                        page.screenshot(
                            path=str(OUTPUT / f"{width}-{phase}-{path.strip('/') or 'home'}.png"),
                            full_page=True, animations="disabled"
                        )
                        assert page.evaluate("""() =>
                            document.querySelector("header") === window.__pr4Header &&
                            document.querySelector("footer") === window.__pr4Footer
                        """)

                # Clicking already active tab should do no app work.
                page.evaluate("window.__pr4Audit.begin()")
                before = len(requests)
                assert page.locator('header .nav [data-nav="/notifications"]').count() == 0
                page.locator("header .header-bell").click()
                expect(page.get_by_role("dialog",name="Уведомления")).to_be_visible()
                expect(page.locator('[data-notification-tab]')).to_have_count(4)
                page.evaluate("window.__pr4Audit.end()")
                page.keyboard.press("Escape")
                expect(page.get_by_role("dialog",name="Уведомления")).to_have_count(0)
                context.close()
        finally:
            browser.close()

    OUTPUT.joinpath("metrics.json").write_text(
        json.dumps(findings,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    assert not errors, ("Browser runtime errors",errors)
    summary = {
        "scope":"CI-local-PostgreSQL-mocked-Auth-Chromium",
        "viewports":list(VIEWPORTS),"tabs":[r[0] for r in ROUTES],
        "measure":"MutationObserver DOM mutations (not visual paints); "
                  "browser-to-E2E-ready elapsed time",
        "results":[{
            "width":width,"phase":phase,
            "n":len(samples),
            "http":sum(x["httpRequests"] for x in samples),
            "api":sum(x["apiRequests"] for x in samples),
            "newElements":sum(x["dom"]["newElements"] for x in samples),
            "mutationRecords":sum(x["dom"]["mutationRecords"] for x in samples),
            "maxObservedNavMs":max(x["dom"]["observedNavMs"] for x in samples),
        } for width in VIEWPORTS for phase in ("cold","warm")
          if (samples := [x for x in findings
                          if x["width"] == width and x["phase"] == phase])]
    }
    print("SHURSH_PR4_UI_AUDIT="+json.dumps(summary,ensure_ascii=False))


@pytest.mark.browser
def test_pr4_profile_mobile_sheet_and_footer(browser_http):
    """Protect removal of profile cruft and bottom sheet position at 375px."""
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width":375,"height":812},
                                    reduced_motion="reduce")
            page.goto(browser_http + "/")
            browser_login(page)
            page.locator('header .nav [data-nav="/profile"]').click()
            expect(page.locator("main h1").first).to_have_text("Мой профиль")
            expect(page.locator(".profile-public-lists")).to_have_count(0)
            expect(page.locator(".profile-visibility")).to_have_count(0)
            expect(page.locator(".social-page-heading")).to_contain_text(
                "Почта остаётся приватной"
            )
            assert "Почта остаётся приватной." not in page.locator(
                ".social-page-heading"
            ).inner_text()
            expect(page.locator("footer nav")).to_have_count(0)
            expect(page.locator("header .header-bell")).to_be_visible()
            assert page.locator("header .header-bell").evaluate(
                "(el) => getComputedStyle(el).borderTopWidth"
            ) == "0px"
            page.locator('[data-social-action="edit-profile"]').click()
            expect(page.locator(".modal")).to_be_visible()
            box = page.locator(".modal").bounding_box()
            assert box is not None and box["y"] >= 11 and abs(box["y"]+box["height"]-812)<=1, box
            assert abs(box["x"])<=1 and abs(box["width"]-375)<=1, box
            assert page.locator(".modal-backdrop").evaluate("(el) => +getComputedStyle(el).zIndex") > page.locator("header.site-header").evaluate("(el) => +getComputedStyle(el).zIndex")
        finally:
            browser.close()


@pytest.mark.browser
def test_pr4_santa_illustration_and_panels(browser_http):
    """The gift-card ornament must remain SVG; never render as a system emoji."""
    import re
    from uuid import uuid4
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width":390,"height":844},
                                    reduced_motion="reduce")
            page.goto(browser_http + "/")
            browser_login(page)
            page.locator('button[data-open="santa"]').first.click()
            page.locator("#fld-title").fill("UI polish "+uuid4().hex[:7])
            page.locator(
                '#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]'
            ).click()
            expect(page).to_have_url(re.compile(r"/santa/\d+$"))
            expect(page.locator("#game-chat")).to_be_visible()
            cards = page.locator(".santa-detail-layout > div:first-child > .panel")
            assert cards.count() >= 2
            first = cards.nth(0).bounding_box()
            second = cards.nth(1).bounding_box()
            assert first and second
            assert second["y"]-first["y"]-first["height"] >= 12, (
                "Missing Santa panel gap",first,second
            )
            page.locator('header [data-nav="/santas"]').click()
            expect(page.locator(".santa-list-card")).to_have_count(1)
            expect(page.locator(".santa-list-card .sparkle-deco svg")).to_have_count(1)
            assert "✳" not in page.locator(".santa-list-card").first.inner_text()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        finally:
            browser.close()


@pytest.mark.browser
def test_pr4_prefetch_makes_first_visits_and_hour_old_tabs_nonblocking(browser_http):
    '''Authenticated root prefetches all six owner tabs, and restores them offline.'''
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=["--no-sandbox"])
        try:
            page=browser.new_page(viewport={"width":390,"height":844},
                                  reduced_motion="reduce")
            page.goto(browser_http+"/")
            browser_login(page)
            page.wait_for_function("() => typeof ownerWarmupReady !== 'undefined' && ownerWarmupReady && !socialUnreadBusy",timeout=15000)
            traffic=[]
            page.on("request", lambda request: traffic.append(request.url)
                    if "/api/" in request.url else None)
            # All first visits are in-memory, including social routes which
            # previously blocked on three separate HTTP requests.
            for path,heading,selector in ROUTES[1:]:
                (page.evaluate("() => nav('/notifications')") if path=='/notifications' else page.locator(selector).click())
                expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                expect(page.locator(".route-skeleton")).to_have_count(0)
            assert not traffic, ("Prefetched first visits unexpectedly fetched", traffic)
            page.context.set_offline(True)
            page.evaluate("() => { window.__pr4Clock=Date.now; Date.now=()=>window.__pr4Clock()+60*60*1000; }")
            # One hour later (> previous 10min DOM cache and 45s API TTL)
            # the app must still work offline with its intact DOM trees.
            for path,heading,selector in ROUTES:
                (page.evaluate("() => nav('/notifications')") if path=='/notifications' else page.locator(selector).click())
                expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                expect(page.locator(".route-skeleton")).to_have_count(0)
                expect(page.locator(".error-page")).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        finally:
            browser.close()


@pytest.mark.browser
def test_ui_gallery_layout_and_interaction_regression():
    """Local UI-kit browser visual contract + screenshots, not a pixel diff.

    Uses the same production CSS as the application, but no real account/API.
    Exact pixels of screenshots are reviewed as artifacts; computed layout/token
    invariants fail CI automatically on supported responsive widths.
    """
    from pathlib import Path
    import json

    from playwright.sync_api import sync_playwright, expect

    root = Path(__file__).resolve().parents[1]
    gallery = root / "tools" / "ui-gallery.html"
    assert gallery.exists()
    out = root / "artifacts" / "pr4-ui" / "gallery"
    out.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for width in (375, 390, 768, 1024, 1440):
                context = browser.new_context(
                    viewport={"width": width, "height": 860},
                    reduced_motion="reduce",
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(gallery.as_uri(), wait_until="load")
                expect(page.locator("#gallery-open-modal")).to_be_visible()
                expect(page.locator(".gallery-swatch")).to_have_count(8)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), (
                    "Page-wide overflow", width
                )
                values = page.evaluate("""() => {
                    const css = getComputedStyle(document.documentElement);
                    const prop = name => css.getPropertyValue(name).trim();
                    const style = el => getComputedStyle(document.querySelector(el));
                    const rect = el => {
                        const b=document.querySelector(el).getBoundingClientRect();
                        return {width:b.width,height:b.height,x:b.x,right:b.right};
                    };
                    return {
                        color:prop('--paper'),
                        focus:prop('--focus-color'),
                        controlRadius:prop('--radius-control'),
                        panelRadius:prop('--radius-panel'),
                        buttonRadius:style('.btn').borderRadius,
                        panelComputedRadius:style('.panel').borderRadius,
                        fieldComputedRadius:style('.field input').borderRadius,
                        buttonMinHeight:parseFloat(style('.btn').minHeight),
                        fieldMinHeight:parseFloat(style('.field input').minHeight),
                        galleryIndex:rect('.gallery-index'),
                        panel:rect('.gallery-demo-forms'),
                    };
                }""")
                assert values["color"] == "#f9f7ef", values
                assert values["focus"] == "#7760b9", values
                assert values["controlRadius"] == "13px", values
                assert values["panelRadius"] == "24px", values
                assert values["buttonRadius"] == "100px", values
                assert values["panelComputedRadius"] == "24px", values
                assert values["fieldComputedRadius"] == "13px", values
                assert values["buttonMinHeight"] >= 49, values
                assert values["fieldMinHeight"] >= 48, values
                assert values["panel"]["x"] >= -1, values
                assert values["panel"]["right"] <= width + 1, values
                # Interactive UI: toast and tabs (no re-render of unrelated cards).
                page.locator('[data-gallery-toast]').first.click()
                expect(page.locator("#toast-root .toast")).to_have_text("Создан новый вишлист")
                page.locator('#gallery-nav-2').click()
                expect(page.locator('#gallery-nav-2')).to_have_attribute("aria-selected", "true")
                expect(page.locator('#gallery-tab-2')).to_be_visible()
                expect(page.locator('#gallery-tab-1')).to_be_hidden()
                page.locator('#gallery-nav-1').click()
                expect(page.locator('#gallery-tab-1')).to_be_visible()
                page.screenshot(
                    path=str(out / f"{width}-gallery.png"),
                    full_page=True,
                    animations="disabled",
                )
                page.locator("#toast-root").evaluate("(el) => el.replaceChildren()")
                page.locator("#gallery-open-modal").click()
                expect(page.get_by_role("dialog", name="Добавить желание")).to_be_visible()
                geometry = page.locator("#gallery-modal .modal").bounding_box()
                assert geometry
                if width <= 760:
                    assert geometry["x"] <= 2
                    assert geometry["width"] >= width-2
                    assert abs(geometry["y"]+geometry["height"]-860) <= 2
                page.screenshot(
                    path=str(out / f"{width}-dialog.png"),
                    full_page=False,
                    animations="disabled",
                )
                page.keyboard.press("Escape")
                expect(page.locator("#gallery-modal")).to_be_hidden()
                expect(page.locator("#gallery-open-modal")).to_be_focused()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), width
                report.append({"viewport":width,"tokens":values,"dialog":geometry})
                context.close()
        finally:
            browser.close()
    (out/"geometry.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))


@pytest.mark.browser
def test_ui_gallery_stable_palette_screenshot_baseline_chromium_webkit():
    """Pixel compare stable screenshot paint samples; other visuals are reviewed."""
    from io import BytesIO
    from PIL import Image, ImageChops

    root=Path(__file__).resolve().parents[1]
    gallery=root/"tools"/"ui-gallery.html"
    baseline=Image.open(root/"tests"/"baselines"/"ui-gallery-palette.png").convert("RGB")
    assert baseline.size==(96,192)
    with sync_playwright() as play:
        for engine in ("chromium","webkit"):
            browser=getattr(play,engine).launch(headless=True,args=["--no-sandbox"] if engine=="chromium" else [])
            try:
                for width in (375,390,768,1024,1440):
                    context=browser.new_context(
                        viewport={"width":width,"height":860},
                        reduced_motion="reduce",device_scale_factor=1,
                        is_mobile=(engine=="webkit" and width<=390),
                        has_touch=(engine=="webkit" and width<=390),
                    )
                    page=context.new_page()
                    page.goto(gallery.as_uri(),wait_until="load")
                    swatches=page.locator(".gallery-swatch-color")
                    expect(swatches).to_have_count(8)
                    actual=Image.new("RGB",(96,192))
                    for i in range(8):
                        # Screenshot the actual rendered element, then sample
                        # its flat-color center with no borders or text.
                        image=Image.open(BytesIO(swatches.nth(i).screenshot())).convert("RGB")
                        assert image.width>=96 and image.height>=44, (
                            engine,width,i,image.size
                        )
                        left=(image.width-96)//2
                        actual.paste(image.crop((left,20,left+96,44)),(0,i*24))
                    target=OUTPUT/"palette"
                    target.mkdir(parents=True,exist_ok=True)
                    actual.save(target/f"{engine}-{width}-actual.png")
                    delta=ImageChops.difference(actual,baseline)
                    assert delta.getbbox() is None, (
                        "Unexpected UI palette pixels",
                        engine,width,
                        sum(1 for p in delta.getdata() if p!=(0,0,0)),
                    )
                    context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_webkit_responsive_ui_gallery_visual_and_keyboard():
    """Mobile Safari engine + tablet/desktop width: screenshot/keyboard gates."""
    gallery=Path(__file__).resolve().parents[1]/"tools"/"ui-gallery.html"
    errors=[]
    with sync_playwright() as play:
        browser=play.webkit.launch(headless=True)
        try:
            for width in (375,390,768,1024,1440):
                context=browser.new_context(
                    viewport={"width":width,"height":860},device_scale_factor=1,
                    reduced_motion="reduce",has_touch=width<=390,
                    is_mobile=width<=390,
                )
                page=context.new_page()
                page.on("pageerror",lambda error:errors.append(str(error)))
                page.goto(gallery.as_uri(),wait_until="load")
                expect(page.locator(".gallery-swatch")).to_have_count(8)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"), (
                    width,"horizontal overflow in WebKit gallery"
                )
                page.locator("#gallery-nav-2").click()
                expect(page.locator("#gallery-tab-2")).to_be_visible()
                expect(page.locator("#gallery-tab-1")).to_be_hidden()
                output=OUTPUT/"webkit"
                output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/f"{width}-gallery.png"),
                                full_page=True,animations="disabled")
                page.locator("#gallery-open-modal").click()
                modal=page.get_by_role("dialog",name="Добавить желание")
                expect(modal).to_be_visible()
                rect=page.locator("#gallery-modal .modal").bounding_box()
                assert rect is not None
                if width<=760:
                    assert rect["x"]<=2 and rect["width"]>=width-2,rect
                    assert abs(rect["y"]+rect["height"]-860)<=2,rect
                expect(page.locator("#gallery-wish-modal")).to_be_focused()
                page.screenshot(path=str(output/f"{width}-dialog.png"),
                                full_page=False,animations="disabled")
                page.keyboard.press("Escape")
                expect(page.locator("#gallery-modal")).to_be_hidden()
                expect(page.locator("#gallery-open-modal")).to_be_focused()
                context.close()
        finally:
            browser.close()
    assert not errors, errors


@pytest.mark.browser
def test_webkit_mobile_six_tabs_and_create_flows(browser_https):
    """Mock-account WebKit: responsive navigation, wishlist and Santa details."""
    from uuid import uuid4
    import re
    errors=[]
    with sync_playwright() as play:
        browser=play.webkit.launch(headless=True)
        try:
            for width in (375,390):
                context=browser.new_context(
                    viewport={"width":width,"height":844},
                    is_mobile=True,has_touch=True,device_scale_factor=1,
                    reduced_motion="reduce",ignore_https_errors=True,
                )
                page=context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror",lambda error:errors.append(str(error)))
                statuses=[]
                page.on("response", lambda response: statuses.append(
                    (urlsplit(response.url).path, response.status)
                ) if urlsplit(response.url).path.startswith("/api/") else None)
                page.goto(browser_https+"/",wait_until="domcontentloaded")
                login_requests=[]
                page.on("request",lambda req: login_requests.append((req.is_navigation_request(),req.headers.get("content-type","")))
                        if urlsplit(req.url).path=="/api/login" and req.method=="POST" else None)
                browser_login(page)
                assert len(login_requests)==1 and login_requests[0][0] and login_requests[0][1].startswith("application/x-www-form-urlencoded"), login_requests
                # Verify browser accepted the Production-like Secure session cookie.
                assert any(c["name"]=="shursh_sid" and c["secure"]
                           for c in context.cookies()), "WebKit HTTPS session cookie missing"
                try:
                    expect(page.locator(".dashboard-page")).to_be_visible(timeout=10000)
                except AssertionError:
                    diagnostics=OUTPUT/"webkit"/"diagnostics"
                    diagnostics.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(diagnostics/f"{width}-after-login.png"),
                                    full_page=True,animations="disabled")
                    state=page.evaluate("""() => ({
                        pathname: location.pathname,
                        route: typeof currentPath==='function' ? currentPath():null,
                        hasCurrentUser: typeof currentUser!=='undefined' && !!currentUser,
                        renderedOwnerTab: typeof renderedOwnerTab==='undefined'?null:renderedOwnerTab,
                        renderStarted: typeof renderStarted==='undefined'?null:renderStarted,
                        busy: document.querySelector('#page-view')?.getAttribute('aria-busy'),
                        mainClass: document.querySelector('main')?.className||null,
                        mainHeading: document.querySelector('main h1')?.textContent||null,
                        modalVisible: !!document.querySelector('.modal-backdrop'),
                    })""")
                    raise AssertionError(
                        f"WebKit login rendered no dashboard: width={width}, "
                        f"state={state}, apiStatuses={statuses}, "
                        f"browserErrors={errors}"
                    )
                page.wait_for_function(
                    "() => typeof ownerWarmupReady !== 'undefined' && ownerWarmupReady",
                    timeout=15000,
                )
                page.evaluate("window.__uiHeader=document.querySelector('header')")
                out=OUTPUT/"webkit"/"flows"/str(width)
                out.mkdir(parents=True,exist_ok=True)
                # All six authenticated owner tabs, horizontal navigation and footer.
                for path,heading,selector in ROUTES:
                    (page.evaluate("() => nav('/notifications')") if path=='/notifications' else page.locator(selector).click())
                    expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2"), (
                        width,path,"page overflow"
                    )
                    assert page.evaluate("document.querySelector('header')===window.__uiHeader")
                    page.screenshot(path=str(out/f"route-{path.strip('/') or 'home'}.png"),
                                    full_page=True,animations="disabled")
                # Long profile modal: edge-to-edge bottom sheet.
                page.locator('header .nav [data-nav="/profile"]').click()
                page.locator('[data-social-action="edit-profile"]').click()
                expect(page.locator(".modal")).to_be_visible()
                bbox=page.locator(".modal").bounding_box()
                assert bbox and bbox["y"]>=11 and abs(bbox["y"]+bbox["height"]-844)<=1 and abs(bbox["x"])<=1 and abs(bbox["width"]-width)<=1,bbox
                page.screenshot(path=str(out/"profile-dialog.png"),
                                full_page=False,animations="disabled")
                page.keyboard.press("Escape")
                expect(page.locator(".modal-backdrop")).to_have_count(0)
                # Creation form and saved list page.
                page.locator('header .nav [data-nav="/lists"]').click()
                page.locator('main button[data-open="list"]').first.click()
                title="WebKit список "+uuid4().hex[:6]
                page.locator("#fld-title").fill(title)
                page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
                expect(page).to_have_url(re.compile(r"/list/\d+$"))
                expect(page.locator("main h1")).to_contain_text(title)
                page.screenshot(path=str(out/"wishlist-detail.png"),
                                full_page=True,animations="disabled")
                # Santa game and chat, including initial loading and compact panels.
                page.locator('header .nav [data-nav="/santas"]').click()
                page.locator('main button[data-open="santa"]').first.click()
                game_title="WebKit игра "+uuid4().hex[:6]
                page.locator("#fld-title").fill(game_title)
                page.locator('#modal-form button[type="submit"], .modal-fixed-footer button[type="submit"]').click()
                expect(page).to_have_url(re.compile(r"/santa/\d+$"))
                expect(page.locator("main h1")).to_contain_text(game_title)
                expect(page.locator("#game-chat")).to_be_visible()
                page.screenshot(path=str(out/"santa-detail.png"),
                                full_page=True,animations="disabled")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
                context.close()
        finally:
            browser.close()
    assert not errors, errors


@pytest.mark.browser
def test_ui_component_flat_surface_screenshot_regression():
    """Screenshot stable color interiors of genuine button/card/field primitives.

    We deliberately do NOT pixel-lock typography, SVG, curved edges or shadows.
    Those are browser/OS dependent and still have human-reviewed full screenshots.
    """
    from io import BytesIO
    from PIL import Image, ImageChops

    root=Path(__file__).resolve().parents[1]
    gallery=root/"tools"/"ui-gallery.html"
    reference=Image.open(root/"tests"/"baselines"/"ui-components-flat.png").convert("RGB")
    fixtures=[
        ("button-dark","button","btn btn-dark"),
        ("button-peach","button","btn btn-peach"),
        ("button-lilac","button","btn btn-lilac"),
        ("button-soft","button","btn btn-soft"),
        ("button-danger","button","btn btn-danger"),
        ("card-panel","article","panel"),
        ("card-list","article","list-card"),
        ("card-santa-even","article","santa-list-card"),
        ("card-santa-odd","article","santa-list-card"),
        ("field-input","input","input"),
        ("field-textarea","textarea","input"),
        ("field-select","select","input"),
    ]
    assert reference.size==(96,(len(fixtures)-1)*24)  # Native select is OS-rasterized
    with sync_playwright() as play:
        for engine in ("chromium","webkit"):
            browser=getattr(play,engine).launch(headless=True,
                  args=["--no-sandbox"] if engine=="chromium" else [])
            try:
                for width in (375,390,768,1024,1440):
                    context=browser.new_context(
                        viewport={"width":width,"height":860},
                        reduced_motion="reduce",device_scale_factor=1,
                        is_mobile=(engine=="webkit" and width<=390),
                        has_touch=(engine=="webkit" and width<=390),
                    )
                    page=context.new_page()
                    page.goto(gallery.as_uri(),wait_until="load")
                    page.evaluate("""fixtures => {
                        const host=document.createElement('section');
                        host.id='gallery-regression-fixtures';
                        host.setAttribute('aria-label','Visual regression fixture');
                        host.style.cssText='width:220px;display:grid;gap:16px;margin:24px 0';
                        for(const [id,tag,classes] of fixtures){
                            const el=document.createElement(tag);
                            el.className=classes;
                            el.dataset.visualFixture=id;
                            el.setAttribute('aria-label',id);
                            el.style.cssText='width:200px;height:80px;min-height:80px;margin:0;'+
                                'box-shadow:none;transform:none;transition:none';
                            if(tag==='select')el.innerHTML='<option value=""></option>';
                            host.appendChild(el);
                        }
                        document.body.append(host);
                    }""",fixtures)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),(
                        engine,width,"visual fixture overflow"
                    )
                    actual=Image.new("RGB",reference.size)
                    computed={}
                    for i,(name,tag,classes) in enumerate(fixtures):
                        locator=page.locator(f'[data-visual-fixture="{name}"]')
                        shot=Image.open(BytesIO(locator.screenshot(animations="disabled"))).convert("RGB")
                        assert shot.width>=96 and shot.height>=24, (engine,width,name,shot.size)
                        x=(shot.width-96)//2
                        y=(shot.height-24)//2
                        if name!="field-select":
                            actual.paste(shot.crop((x,y,x+96,y+24)),(0,i*24))
                        computed[name]=locator.evaluate("""el => {
                            const style=getComputedStyle(el);
                            return {
                                background:style.backgroundColor,
                                borderRadius:style.borderRadius,
                                borderWidth:style.borderTopWidth,
                                borderColor:style.borderTopColor,
                            };
                        }""")
                    out=OUTPUT/"component-surfaces"
                    out.mkdir(parents=True,exist_ok=True)
                    actual.save(out/f"{engine}-{width}-surface-atlas.png")
                    delta=ImageChops.difference(actual,reference)
                    assert delta.getbbox() is None, (
                        "Stable button/card/field pixel baseline differs",
                        engine,width,
                        delta.getbbox(),
                        {k:v["background"] for k,v in computed.items()},
                    )
                    assert computed["button-dark"]["borderRadius"]=="100px"
                    assert computed["card-panel"]["borderRadius"]=="24px"
                    assert computed["card-list"]["borderRadius"]=="25px"
                    for variant,border in (
                        ("card-santa-even","rgb(212, 201, 231)"),
                        ("card-santa-odd","rgb(234, 215, 198)")
                    ):
                        assert computed[variant]["borderRadius"]=="26px"
                        assert computed[variant]["borderColor"]==border, (
                            engine,width,variant,computed[variant]
                        )
                    for name in ("field-input","field-textarea","field-select"):
                        assert computed[name]["borderRadius"]=="13px",(
                            engine,width,name,computed[name]
                        )
                        assert computed[name]["borderColor"]=="rgb(230, 223, 214)",(
                            engine,width,name,computed[name]
                        )
                    # Full reference fixture and focus/hover states are visual
                    # artifacts; typography and curved edges are not pixel-gated.
                    page.locator('[data-visual-fixture="button-dark"]').hover()
                    page.locator('[data-visual-fixture="field-input"]').focus()
                    page.screenshot(path=str(out/f"{engine}-{width}-components.png"),
                                    full_page=True,animations="disabled")
                    context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_pr4_p1_mobile_contrast_touch_targets_and_scroll_cue(browser_https):
    """Secondary text WCAG AA, 44px touch areas and unobtrusive overflow cues.

    Runs with disposable CI accounts over local HTTPS. Full screenshots remain
    review artifacts rather than silently accepted full-component pixel goldens.
    """
    import re
    root=Path(__file__).resolve().parents[1]
    gallery=root/"tools"/"ui-gallery.html"
    output=OUTPUT/"p1-mobile"
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        for engine in ("chromium","webkit"):
            browser=getattr(play,engine).launch(
                headless=True,args=["--no-sandbox"] if engine=="chromium" else [])
            try:
                for width in (375,390,768):
                    context=browser.new_context(
                        viewport={"width":width,"height":844},
                        device_scale_factor=1,reduced_motion="reduce",
                        has_touch=True,is_mobile=True,ignore_https_errors=True,
                    )
                    page=context.new_page()
                    page.goto(gallery.as_uri(),wait_until="load")
                    ratios=page.evaluate("""() => {
                        const root=getComputedStyle(document.documentElement);
                        const ink=[root.getPropertyValue('--muted').trim(),
                            getComputedStyle(document.querySelector('.note')).color,
                            getComputedStyle(document.querySelector('.section-label')).color];
                        const surfaces=['#f9f7ef','#fffdf8','#f7e9db',
                                        '#e8e0f4','#f9c6ac','#d9c9f2'];
                        const rgb=s=>s.startsWith('#')
                          ?[0,2,4].map(i=>parseInt(s.slice(1+i,3+i),16))
                          :s.match(/[\\d.]+/g).slice(0,3).map(Number);
                        const light=s=>rgb(s).reduce((a,n,i)=>{
                          n=n/255;return a+(n<=.04045?n/12.92:((n+.055)/1.055)**2.4)
                            *[.2126,.7152,.0722][i];
                        },0);
                        const contrast=(a,b)=>{
                          const x=light(a),y=light(b);
                          return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
                        };
                        return ink.map(color=>({
                           color,ratios:surfaces.map(background=>({
                               background,value:contrast(color,background)
                           }))
                        }));
                    }""")
                    for entry in ratios:
                        for ratio in entry["ratios"]:
                            assert ratio["value"]>=4.5, (
                                "WCAG AA contrast",engine,width,entry["color"],ratio
                            )
                    for selector in (".btn-small",".btn-square",".header-bell"):
                        box=page.locator(selector).first.bounding_box()
                        assert box and box["width"]>=43.9 and box["height"]>=43.9,(
                            engine,width,selector,box
                        )
                    page.locator("#gallery-open-modal").click()
                    close=page.locator("#gallery-modal .modal-close").bounding_box()
                    assert close and close["width"]>=43.9 and close["height"]>=43.9,(
                        engine,width,close
                    )
                    page.screenshot(
                        path=str(output/f"{engine}-{width}-dialog.png"),
                        full_page=False,animations="disabled",
                    )
                    page.keyboard.press("Escape")
                    page.goto(browser_https+"/",wait_until="domcontentloaded")
                    browser_login(page)
                    expect(page.locator(".dashboard-page")).to_be_visible()
                    nav=page.locator("header .nav")
                    expect(nav).to_be_visible()
                    widths=nav.evaluate("""el => ({
                        client:el.clientWidth, scroll:el.scrollWidth,
                        links:[...el.querySelectorAll('a')].map(a=>
                          a.getBoundingClientRect().height)
                    })""")
                    assert min(widths["links"])>=43.9,(engine,width,widths)
                    if width<768:
                        assert widths["scroll"]>widths["client"]+2,(engine,width,widths)
                        expect(nav).to_have_class(re.compile("nav-scroll-more-right"))
                        right=page.evaluate("""() => ({
                            content:getComputedStyle(document.querySelector('.topbar'),'::after').content,
                            pointer:getComputedStyle(document.querySelector('.topbar'),'::after').pointerEvents
                        })""")
                        assert "›" in right["content"] and right["pointer"]=="none",(
                            engine,width,right
                        )
                        nav.evaluate("el => {el.scrollLeft=el.scrollWidth}")
                        expect(nav).not_to_have_class(re.compile("nav-scroll-more-right"))
                        expect(nav).to_have_class(re.compile("nav-scroll-more-left"))
                        left=page.evaluate("""() => ({
                            content:getComputedStyle(document.querySelector('.topbar'),'::before').content,
                            pointer:getComputedStyle(document.querySelector('.topbar'),'::before').pointerEvents
                        })""")
                        assert "‹" in left["content"] and left["pointer"]=="none",(
                            engine,width,left
                        )
                    if width<768:
                        # The hint's entire painted rectangle must live below
                        # every tab, including the active marker, at both scroll
                        # ends; a gradient cannot occlude the active tab.
                        for side,tag in (("right","::after"),("left","::before")):
                            if side=="right":
                                nav.evaluate("el => {el.scrollLeft=0}")
                                expect(nav).to_have_class(re.compile("nav-scroll-more-right"))
                            else:
                                nav.evaluate("el => {el.scrollLeft=el.scrollWidth}")
                                expect(nav).to_have_class(re.compile("nav-scroll-more-left"))
                            geometry=page.evaluate("""pseudo => {
                                const topbar=document.querySelector('.topbar');
                                const nav=topbar.querySelector('.nav');
                                const css=getComputedStyle(topbar,pseudo);
                                const host=topbar.getBoundingClientRect();
                                const bottom=parseFloat(css.bottom);
                                const height=parseFloat(css.height);
                                const links=[...nav.querySelectorAll('a')]
                                    .map(el=>el.getBoundingClientRect().bottom);
                                const maxLinkBottom=Math.max(...links);
                                const cueTop=host.bottom-bottom-height;
                                return {cueTop,maxLinkBottom,
                                    gap:cueTop-maxLinkBottom,
                                    height,background:css.backgroundImage,
                                    pointer:css.pointerEvents,
                                    content:css.content};
                            }""",tag)
                            assert geometry["gap"]>=2, (
                                "navigation hint overlaps tabs",engine,width,side,geometry
                            )
                            assert geometry["height"]<=16.1,geometry
                            assert geometry["pointer"]=="none",geometry
                            assert "gradient" in geometry["background"],geometry
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
                    page.screenshot(
                        path=str(output/f"{engine}-{width}-header.png"),
                        full_page=False,animations="disabled",
                    )
                    context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_pr4_post_release_mobile_controls_chromium_webkit(browser_https):
    """The new compact header, notifications and wishlist tabs work on mobile."""
    output=OUTPUT/"ux-follow-up"
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        for engine in ("chromium","webkit"):
            browser=getattr(play,engine).launch(
                headless=True,args=["--no-sandbox"] if engine=="chromium" else [])
            try:
                for width in (375,390):
                    context=browser.new_context(
                        viewport={"width":width,"height":844},device_scale_factor=1,
                        reduced_motion="reduce",ignore_https_errors=True,
                        is_mobile=engine=="webkit",has_touch=engine=="webkit")
                    page=context.new_page()
                    page.set_default_timeout(15000)
                    page.goto(browser_https+"/",wait_until="domcontentloaded")
                    browser_login(page)
                    expect(page.locator(".dashboard-page")).to_be_visible()
                    page.locator("header .header-bell").click()
                    dialog=page.get_by_role("dialog",name="Уведомления")
                    expect(dialog).to_be_visible()
                    expect(dialog.locator('[data-notification-tab]')).to_have_count(4)
                    expect(dialog.get_by_role("button",name="Прочесть все")).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
                    page.screenshot(path=str(output/f"{engine}-{width}-notifications.png"),
                                    animations="disabled")
                    page.keyboard.press("Escape")
                    expect(dialog).to_have_count(0)
                    page.locator('header .nav [data-nav="/lists"]').click()
                    expect(page.get_by_role("tab",name="Вишлисты друзей")).to_be_visible()
                    page.get_by_role("tab",name="Вишлисты друзей").click()
                    expect(page.get_by_role("tab",name="Вишлисты друзей")).to_have_attribute(
                        "aria-selected","true")
                    expect(page.locator("#wishlist-view-content")).not_to_contain_text(
                        "Загружаем вишлисты друзей…",timeout=15000)
                    page.screenshot(path=str(output/f"{engine}-{width}-friend-wishlists.png"),
                                    animations="disabled")
                    page.get_by_role("tab",name="Мои вишлисты").click()
                    page.locator('main button[data-open="list"]').first.click()
                    expect(page.locator(".modal>.modal-fixed-header")).to_be_visible()
                    expect(page.locator(".modal>.modal-fixed-footer")).to_be_visible()
                    assert page.locator(".modal-fixed-footer button[type=submit]").get_attribute(
                        "form")=="modal-form"
                    page.keyboard.press("Escape")
                    page.locator("header .logo").first.click()
                    page.evaluate("window.scrollTo(0,document.documentElement.scrollHeight)")
                    expect(page.locator("header.site-header")).to_have_class(
                        re.compile("is-condensed"))
                    for selector in ("header .logo","header .header-bell",
                                     "header .header-avatar",'header [data-action="logout"]'):
                        expect(page.locator(selector)).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
                    page.screenshot(path=str(output/f"{engine}-{width}-compact-header.png"),
                                    animations="disabled")
                    context.close()
            finally:
                browser.close()



@pytest.mark.browser
def test_shursh_ux_followup_finish_game_and_sticky_modal(browser_https):
    """Signed-in owner can finish a drawn game without losing secrets."""
    from uuid import uuid4
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            context=browser.new_context(viewport={'width':390,'height':844},
                reduced_motion='reduce',ignore_https_errors=True)
            page=context.new_page()
            page.set_default_timeout(15000)
            page.goto(browser_https+'/',wait_until='domcontentloaded')
            browser_login(page)
            expect(page.locator('header .user-name')).to_have_count(0)
            expect(page.locator('header .header-avatar')).to_be_visible()
            assert page.locator('header .nav a.active').count()==1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            event=page.evaluate("""async title => {
              const response=await fetch('/api/santas',{method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({title})});
              if(!response.ok)throw Error('Could not create event');
              return await response.json();
            }""",'Visual status '+uuid4().hex[:8])
            id=event['id']
            for name in ('Гость один','Гость два'):
                page.evaluate("""async ({id,name}) => {
                  const response=await fetch('/api/santas/'+id+'/participants',{method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({name})});
                  if(!response.ok)throw Error('Could not add participant');
                }""",{'id':id,'name':name})
            page.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id+'/draw',{method:'POST',
                  headers:{'Content-Type':'application/json'},body:'{}'});
                if(!response.ok)throw Error('Could not draw');
            }""",id)
            page.evaluate("id => nav('/santa/'+id,{force:true})",id)
            expect(page.locator('[data-action="finish-santa"]')).to_be_visible()
            expect(page.locator('.santa-game-status')).to_contain_text('Игра началась')
            page.locator('[data-action="finish-santa"]').click()
            dialog=page.get_by_role('dialog',name='Завершить Тайного Санту?')
            expect(dialog).to_be_visible()
            assert page.locator('.modal-backdrop').evaluate(
                "(el) => +getComputedStyle(el).zIndex"
            )>page.locator('header.site-header').evaluate(
                "(el) => +getComputedStyle(el).zIndex")
            import struct,zlib
            def chunk(tag,payload):
                return struct.pack('>I',len(payload))+tag+payload+struct.pack('>I',zlib.crc32(tag+payload)&0xffffffff)
            photo=(b'\x89PNG\r\n\x1a\n'+
                   chunk(b'IHDR',struct.pack('>IIBBBBB',32,32,8,2,0,0,0))+
                   chunk(b'IDAT',zlib.compress(b''.join(b'\x00'+bytes([250,220,200])*32 for _ in range(32))))+
                   chunk(b'IEND',b''))
            page.locator('#finish-santa-photo').set_input_files({
                'name':'group-snapshot.png','mimeType':'image/png','buffer':photo})
            page.locator('.modal-fixed-footer [type="submit"]').click()
            expect(page.locator('.santa-game-status')).to_contain_text('Игра завершена')
            expect(page.locator('[data-action="finish-santa"]')).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            assert page.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id);
                return response.ok&&(await response.json()).event.status==='finished';
            }""",id)
            expect(page.locator('.santa-memory-panel')).to_be_visible()
            expect(page.locator('#santa-memory-input')).to_have_count(1)
            expect(page.locator('.santa-memory-photo')).to_be_visible()
            assert page.locator('.santa-memory-panel').evaluate("el=>el.previousElementSibling.querySelector('h2')?.textContent==='О событии'")
            assert page.locator('.santa-memory-photo').get_attribute('src').startswith('data:image/webp;base64,')
            for width in (390,1280):
                page.set_viewport_size({'width':width,'height':844})
                page.locator('.santa-memory-photo').evaluate("(img)=>img.decode()")
                geometry=page.locator('.santa-memory-photo').evaluate("""img=>{
                    const r=img.getBoundingClientRect(),parent=img.parentElement.getBoundingClientRect();
                    return {w:r.width,h:r.height,parent:parent.width,ratio:img.naturalWidth/img.naturalHeight,maxHeight:getComputedStyle(img).maxHeight};
                }""")
                assert abs(geometry['w']-geometry['parent'])<2,geometry
                assert abs(geometry['w']/geometry['h']-geometry['ratio'])<.02,geometry
                assert geometry['maxHeight']=='none',geometry
            page.set_viewport_size({'width':390,'height':844})
            page.locator('#santa-memory-input').set_input_files({
                'name':'all-together.png','mimeType':'image/png','buffer':photo})
            expect(page.locator('.santa-memory-photo')).to_be_visible(timeout=15000)
            assert page.locator('.santa-memory-photo').get_attribute('src').startswith('data:image/webp;base64,')
            assert page.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id+'/memory');
                return response.ok&&!!(await response.json()).memory?.image_data;
            }""",id)
            # The switcher is client-only: moving an event into completed
            # does not trigger a new API request for every filter click.
            page.evaluate("nav('/santas',{force:true})")
            expect(page.locator('.santa-state-tabs [data-santa-state]')).to_have_count(2)
            page.locator('[data-santa-state="finished"]').click()
            expect(page.locator('[data-santa-card-state="finished"]:not([hidden]) a[href="/santa/'+str(id)+'"]')).to_have_count(1)
            expect(page.locator('[data-santa-card-state="current"]:not([hidden])')).to_have_count(0)
            page.locator('[data-santa-state="current"]').click()
            expect(page.locator('[data-santa-card-state="finished"][hidden] a[href="/santa/'+str(id)+'"]')).to_have_count(1)
            # Header collapse must not alter document flow or scroll position.
            page.evaluate("""() => {
                // Disable only the test's smooth scrolling, not the product.
                document.documentElement.style.scrollBehavior='auto';
                document.body.style.minHeight='3000px';
                window.scrollTo({top:300,behavior:'instant'});
            }""")
            expect(page.locator('.site-header')).to_have_class(re.compile(r'is-condensed'))
            stable=page.evaluate("({scrollY,padding:getComputedStyle(document.querySelector('#app')).paddingTop,top:document.querySelector('.site-header').getBoundingClientRect().top})")
            page.wait_for_timeout(160)
            again=page.evaluate("({scrollY,padding:getComputedStyle(document.querySelector('#app')).paddingTop,top:document.querySelector('.site-header').getBoundingClientRect().top})")
            assert abs(stable['scrollY']-again['scrollY'])<2,(stable,again)
            assert stable['padding']==again['padding'] and abs(again['top'])<2
            page.set_viewport_size({'width':1280,'height':900})
            page.evaluate("window.scrollTo(0,0)")
            page.locator('header .header-bell').click()
            expect(page.get_by_role('dialog',name='Уведомления')).to_be_visible()
            bell=page.locator('header .header-bell').bounding_box()
            pop=page.locator('.notification-popover .modal').bounding_box()
            assert bell and pop and pop['y']>=bell['y']+bell['height']-2,(bell,pop)
            assert pop['x']>=0 and pop['x']+pop['width']<=1280,(bell,pop)
            assert abs((pop['x']+pop['width'])-(bell['x']+bell['width']))<=16,(bell,pop)
        finally:
            browser.close()



@pytest.mark.browser
def test_cookie_notice_responsive_alignment_chromium_and_webkit(browser_https):
    """Real app/CSS, no hosted credentials: visual alignment at breakpoint edges."""
    from playwright.sync_api import sync_playwright, expect

    widths=(320,360,375,390,400,401,430,600,767,768,1024,1440)
    output=OUTPUT/"cookie-responsive"
    output.mkdir(parents=True,exist_ok=True)
    observations=[]
    with sync_playwright() as play:
        for engine in ("chromium","webkit"):
            browser=getattr(play,engine).launch(headless=True)
            try:
                for width in widths:
                    context=browser.new_context(
                        viewport={"width":width,"height":780},
                        device_scale_factor=1,
                        reduced_motion="reduce",
                        ignore_https_errors=True,
                    )
                    page=context.new_page()
                    try:
                        page.goto(browser_https+"/",wait_until="domcontentloaded")
                        notice=page.locator(".cookie-notice")
                        expect(notice).to_be_visible(timeout=12000)
                        expect(notice.locator(".cookie-message > span")).to_have_count(2)
                        expect(notice.locator("button")).to_have_text("Понятно")
                        metrics=notice.evaluate("""(el) => {
                            const r=el.getBoundingClientRect(), s=getComputedStyle(el);
                            const msg=el.querySelector('.cookie-message');
                            const m=msg.getBoundingClientRect();
                            const btn=el.querySelector('button');
                            const b=btn.getBoundingClientRect();
                            const lines=[...msg.children].map(x=>{
                                const rect=x.getBoundingClientRect(), css=getComputedStyle(x);
                                return {width:rect.width,height:rect.height,left:rect.left,
                                  centerX:rect.x+rect.width/2,overflow:x.scrollWidth>x.clientWidth+1,
                                  lineHeight:parseFloat(css.lineHeight)};
                            });
                            return {
                              width:r.width,left:r.left,right:r.right,centerX:r.x+r.width/2,
                              viewportWidth:innerWidth,docWidth:document.documentElement.scrollWidth,
                              flexDirection:s.flexDirection,
                              gap:parseFloat(s.gap)||0,
                              contentWidth:r.width-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)-
                                parseFloat(s.borderLeftWidth)-parseFloat(s.borderRightWidth),
                              textWidth:m.width,textLeft:m.left,textCenterX:m.x+m.width/2,
                              textAlign:getComputedStyle(msg).textAlign,
                              justifyItems:getComputedStyle(msg).justifyItems,
                              textCenterY:m.y+m.height/2,
                              buttonWidth:b.width,buttonHeight:b.height,
                              buttonCenterX:b.x+b.width/2,buttonCenterY:b.y+b.height/2,
                              buttonLeft:b.left,buttonRight:b.right,
                              lines
                            };
                        }""")
                        assert abs(metrics["centerX"]-width/2)<=1,(engine,width,metrics)
                        assert metrics["left"]>=-1 and metrics["right"]<=width+1,(engine,width,metrics)
                        assert metrics["docWidth"]<=width+2,("horizontal overflow",engine,width,metrics)
                        assert metrics["buttonHeight"]>=44,("touch target",engine,width,metrics)
                        assert all(not line["overflow"] for line in metrics["lines"]),(engine,width,metrics)
                        assert all(line["height"]>=line["lineHeight"]-2 for line in metrics["lines"]),(engine,width,metrics)
                        assert metrics["textAlign"]=="left" and metrics["justifyItems"]=="start",(engine,width,metrics)
                        assert all(abs(line["left"]-metrics["textLeft"])<=1
                                   for line in metrics["lines"]),(engine,width,metrics)
                        assert metrics["flexDirection"]=="row",(engine,width,metrics)
                        if width<=760:
                            assert notice.evaluate("(el)=>getComputedStyle(el).position")=="relative"
                            assert notice.evaluate("(el)=>el.parentElement.id")=="app"
                            assert notice.evaluate("""el=>{
                                const view=document.querySelector('#page-view');
                                return el.getBoundingClientRect().bottom<=view.getBoundingClientRect().top+1;
                            }"""),(engine,width,"cookie overlaps page")
                        else:
                            assert notice.evaluate("(el)=>getComputedStyle(el).position")=="fixed"

                        assert abs(metrics["textCenterY"]-metrics["buttonCenterY"])<=1,(engine,width,metrics)
                        assert metrics["buttonLeft"]>=metrics["textLeft"]+metrics["textWidth"]-1,(engine,width,metrics)
                        expected=metrics["textWidth"]+metrics["buttonWidth"]+metrics["gap"]
                        assert abs(metrics["contentWidth"]-expected)<=2,(engine,width,metrics)
                        notice.screenshot(path=str(output/f"{engine}-{width}-banner.png"),
                                          animations="disabled")
                        if width in (320,390,401,430,768):
                            page.screenshot(path=str(output/f"{engine}-{width}-viewport.png"),
                                            animations="disabled")
                        observations.append({"engine":engine,"width":width,
                                             "noticeWidth":round(metrics["width"],1),
                                             "buttonHeight":round(metrics["buttonHeight"],1),
                                             "direction":metrics["flexDirection"],
                                             "offsetFromCenter":round(metrics["centerX"]-width/2,1)})
                    finally:
                        context.close()
            finally:
                browser.close()
    (output/"metrics.json").write_text(
        json.dumps(observations,ensure_ascii=False,indent=2),encoding="utf-8"
    )


@pytest.mark.browser
def test_guest_bootstrap_resilience_on_mobile_chromium_and_webkit(browser_https):
    """No empty guest list; a blocked optional script or API must not leave only the logo."""
    with sync_playwright() as play:
        for browser_type in (play.chromium, play.webkit):
            browser = browser_type.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={'width':390,'height':844}, is_mobile=True,
                    ignore_https_errors=True)
                page=context.new_page()
                try:
                    page.route('**/santa-ui.js*',lambda route:route.abort())
                    page.route('**/social-ui.js*',lambda route:route.abort())
                    page.goto(browser_https+'/',wait_until='domcontentloaded')
                    expect(page.locator('.hero-copy h1')).to_contain_text(
                        'Подарки, о которых',timeout=10000)
                    assert page.locator('.loading-screen').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                finally:
                    context.close()

                context=browser.new_context(viewport={'width':390,'height':844},
                                            is_mobile=True,ignore_https_errors=True)
                page=context.new_page()
                try:
                    page.route('**/api/dashboard',lambda route:route.abort())
                    page.goto(browser_https+'/',wait_until='domcontentloaded')
                    expect(page.locator('.error-page h1')).to_have_text(
                        'Не получилось загрузить Шурш',timeout=10000)
                    expect(page.locator('.error-page [data-nav="/"]')).to_be_visible()
                    expect(page.get_by_role('button',name='Попробовать снова')).to_be_visible()
                    expect(page.get_by_role('button',name='Сообщить об ошибке')).to_be_visible()
                finally:
                    context.close()

                context=browser.new_context(viewport={'width':390,'height':844},
                                            is_mobile=True,ignore_https_errors=True)
                page=context.new_page()
                try:
                    page.goto(browser_https+'/lists',wait_until='domcontentloaded')
                    expect(page.locator('.hero-copy h1')).to_contain_text(
                        'Подарки, о которых',timeout=10000)
                    assert page.url.rstrip('/')==browser_https
                    assert page.locator('.cookie-notice button').count()==1
                    assert page.locator('.loading-help').count()==0
                finally:
                    context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_mobile_webkit_signup_inline_validation(browser_https):
    """WebKit/iPhone: invalid signup stays local, corrected form can register."""
    with sync_playwright() as play:
        browser=play.webkit.launch(headless=True)
        try:
            context=browser.new_context(
                viewport={"width":390,"height":844},
                is_mobile=True,ignore_https_errors=True
            )
            page=context.new_page()
            requests=[]
            page.on('request',lambda req: requests.append('signup')
                    if req.url.endswith('/api/register') and req.method=='POST' else None)
            page.goto(browser_https+'/',wait_until='domcontentloaded')
            page.locator('header [data-open="login"]').click()
            page.locator('#fld-password').fill('valid-password')
            assert page.evaluate('strengthWorker===null'), 'Ordinary login must not load estimator'
            page.locator('.modal-foot [data-open="register"]').click()
            expect(page.locator('#fld-confirm_password')).to_be_visible()
            assert page.evaluate('strengthWorker===null'), 'Opening registration must not load estimator before input'
            email=page.locator('#fld-email')
            email.fill('h@h.ю')
            expect(email).to_have_value('h@h.ю')
            expect(email).to_be_focused()
            expect(email).to_have_attribute('aria-invalid','true')
            expect(page.locator('#auth-error-email')).to_have_text('Используй латинские буквы после @')
            overlay=page.locator('.auth-character-input-row .auth-character-overlay')
            expect(overlay).to_be_visible()
            assert overlay.evaluate("(c)=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).some((v,i)=>i%4===3&&v>0)")
            email.fill('user@example.test')
            expect(page.locator('#auth-error-email')).to_be_hidden()
            expect(overlay).to_be_hidden()
            email.fill('')
            page.locator('.modal-fixed-footer [type=submit]').click()
            expect(page.locator('#auth-error-email')).to_have_text('Укажи почту')
            expect(page.locator('#auth-error-confirm_password')).to_have_text('Повтори пароль')
            assert requests==[]
            page.locator('#fld-name').fill('Аня')
            page.locator('#fld-email').fill('owner@example.test')
            page.locator('[data-password-generate]').click()
            password=page.locator('#fld-password').input_value()
            assert password and page.locator('#fld-confirm_password').input_value()==password
            expect(page.locator('[data-password-strength-label]')).to_have_text('Надёжный')
            assert page.evaluate('strengthWorker instanceof Worker')
            label=page.locator('[data-password-strength-label]')
            bars=page.locator('.password-strength-bars')
            # Measure both boxes in the same animation frame. The auth modal
            # can still be moving when the password estimator publishes its score.
            page.wait_for_function("""() => {
                const a=document.querySelector('[data-password-strength-label]').getBoundingClientRect();
                const b=document.querySelector('.password-strength-bars').getBoundingClientRect();
                return a.x<b.x && Math.abs(a.y+a.height/2-b.y-b.height/2)<2;
            }""")
            # The maintained estimator, not fixed length bands, owns the score.
            password_input=page.locator('#fld-password')
            toggle=page.locator('.password-field:has(#fld-password) [data-password-visibility]')
            overlay=page.locator('.password-field:has(#fld-password) .auth-character-overlay')
            password_input.fill('abЁcd123')
            expect(page.locator('#auth-error-password')).to_have_text('Убери русские буквы из пароля')
            expect(overlay).to_be_visible()
            toggle.click()
            expect(overlay).to_be_hidden()
            assert overlay.evaluate('(c)=>c.width===0 && c.height===0')
            toggle.click()
            expect(overlay).to_be_visible()
            password_input.fill('abcd1234')
            expect(overlay).to_be_hidden()
            page.locator('#fld-password').fill('Password1')
            expect(label).to_have_text('Слабый')
            page.locator('#fld-password').fill('Vq!7tZ#9mK2pF@8rYw4N')
            expect(label).to_have_text('Надёжный')
            # Rapid changes must not allow an obsolete strong result to win.
            page.locator('#fld-password').fill('Vq!7tZ#9mK2pF@8rYw4N')
            page.locator('#fld-password').fill('Password1')
            expect(label).to_have_text('Слабый')
            expect(page.locator('[data-password-strength]')).to_have_attribute('data-target-level','1')
            page.locator('#fld-password').fill('qvR!NtMkY@pLW')
            expect(label).to_have_text(__import__('re').compile('^(Хороший|Надёжный)$'))
            expect(page.locator('#auth-error-password')).to_be_hidden()
            page.locator('#fld-email').fill('почта@78.yy')
            expect(page.locator('#auth-error-email')).to_have_text('Перед @ используй латинские буквы, цифры и допустимые знаки')
            page.locator('#fld-email').fill('user,name@example.test')
            expect(page.locator('#auth-error-email')).to_contain_text('Убери запятую из адреса')
            page.locator('#fld-email').fill('not-email')
            expect(page.locator('#auth-error-email')).to_have_text('Добавь знак @')
            page.locator('#fld-email').fill('owner@example.test')
            # Check the actual interpolated fills, not integer DOM updates.
            meter=page.locator('[data-password-strength]')
            page.locator('#fld-password').fill('')
            expect(meter).to_be_hidden(timeout=3000)
            page.locator('[data-password-generate]').click()
            expect(label).to_have_text('Надёжный')
            expect(meter).to_have_attribute('data-level','4',timeout=3000)
            page.locator('#fld-password').fill('Password1')
            expect(label).to_have_text('Слабый')
            expect(meter).to_have_attribute('data-level','1',timeout=3000)
            page.locator('[data-password-generate]').click()
            expect(label).to_have_text('Надёжный')
            page.locator('.password-field:has(#fld-confirm_password) [data-password-visibility]').click()
            expect(page.locator('#fld-confirm_password')).to_have_attribute('type','text')
            page.locator('.password-field:has(#fld-confirm_password) [data-password-visibility]').click()
            expect(page.locator('#fld-confirm_password')).to_have_attribute('type','password')
            page.locator('.modal-fixed-footer [type=submit]').click()
            expect(page.get_by_role('dialog')).to_contain_text('Проверь почту',timeout=10000)
            assert requests==['signup']
            dialog=page.get_by_role('dialog')
            expect(dialog).to_contain_text('Если аккаунт уже есть')
            expect(dialog).not_to_contain_text('Письмо с подтверждением отправлено!')
            dialog.locator('[data-open="login"]').click()
            expect(page.locator('#fld-email')).to_have_value('owner@example.test')
            page.locator('#fld-password').fill('valid-password')
            page.route('**/api/login', lambda route: route.fulfill(
                status=429, json={'error':'Rate limit'}))
            page.locator('.modal-fixed-footer [type=submit]').click()
            expect(dialog.locator('.auth-form-warning')).to_have_text('Слишком много попыток. Попробуй позже')
            expect(dialog).to_be_visible()
            assert page.locator('.toast').count()==0
            page.unroute('**/api/login')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        finally:
            browser.close()

@pytest.mark.browser
def test_auth_character_highlight_responsive(browser_https):
    """Synthetic inputs only; check overlay pixels, scrolling and privacy in both engines."""
    output=OUTPUT/"auth-character-highlights"
    output.mkdir(parents=True,exist_ok=True)
    pixel_test="""i=>{
      const c=i.parentElement.querySelector('canvas');
      if(!c||c.hidden||!c.width)return false;
      const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      for(let k=3;k<d.length;k+=4)if(d[k])return true;
      return false;
    }"""
    with sync_playwright() as play:
        for engine in (play.chromium,play.webkit):
            browser=engine.launch(headless=True)
            try:
                for width in (375,390,1440):
                    context=browser.new_context(viewport={"width":width,"height":844},
                        device_scale_factor=2 if width<500 else 1,
                        is_mobile=width<500,has_touch=width<500,ignore_https_errors=True)
                    try:
                        page=context.new_page()
                        posts=[]
                        page.on('request',lambda req: posts.append(req.method)
                                if req.method=='POST' and '/api/' in req.url else None)
                        page.goto(browser_https+'/',wait_until='domcontentloaded')
                        page.locator('header [data-open="login"]').click()
                        page.locator('.modal-foot [data-open="register"]').click()
                        email=page.locator('#fld-email')
                        password=page.locator('#fld-password')
                        toggle=page.locator('.password-field:has(#fld-password) [data-password-visibility]')
                        # Incomplete syntax must not be painted as an invalid character.
                        for address,message,marked in (
                            ('почта','Перед @ используй латинские буквы, цифры и допустимые знаки','почта'),
                            ('почта@','Перед @ используй латинские буквы, цифры и допустимые знаки','почта'),
                            ('a..b','Исправь точки в части почты перед @','.'),
                            ('a.@','Исправь точки в части почты перед @','.'),
                            ('12@mail.','Допиши окончание домена, например ru или com',''),
                            ('12@#mail','Убери символ # из домена','#'),
                            ('#username@gmail.com','Убери символ # из имени почты Gmail','#'),
                            ('a@mail..','Убери лишние точки в домене','.')):
                            email.fill(address)
                            expect(page.locator('#auth-error-email')).to_have_text(message)
                            expect(email).to_have_attribute('aria-invalid','true')
                            assert email.evaluate("""(input,message)=>{
                              const ranges=authInvalidCharRanges(input,true,message);
                              return [...new Set(ranges.flatMap(([a,b])=>[...input.value.slice(a,b)]))].join('');
                            }""",message)==marked
                            assert email.evaluate(pixel_test)==bool(marked)
                        for valid in ('name+tag@gmail.com','first.last+tag@gmail.com','#user@example.com','12@mail.ru'):
                            email.fill(valid)
                            expect(page.locator('#auth-error-email')).to_be_hidden()
                            assert not email.evaluate(pixel_test)
                        for value in ('почта','user@example.123','user@example,com','h@h.ю'):
                            email.fill(value)
                            expect(email).to_have_attribute('aria-invalid','true')
                            assert email.evaluate(pixel_test)
                        # insert_text follows the non-keyboard input path used by paste/IME.
                        email.fill('')
                        email.focus()
                        page.keyboard.insert_text('x'*55+'я@example.com')
                        expect(email).to_have_value('x'*55+'я@example.com')
                        expect(email).to_have_attribute('aria-invalid','true')
                        if width<500:
                            email.evaluate("i=>{i.setSelectionRange(i.value.length,i.value.length);i.scrollLeft=i.scrollWidth;i.dispatchEvent(new Event('scroll'));}")
                            page.wait_for_function("i=>i.scrollLeft>0",arg=email.element_handle())
                            page.wait_for_function(pixel_test,arg=email.element_handle())
                            email.evaluate("i=>{i.setSelectionRange(0,0);i.scrollLeft=0;i.dispatchEvent(new Event('scroll'));}")
                            page.wait_for_function("i=>i.scrollLeft===0",arg=email.element_handle())
                            page.wait_for_function("i=>!("+pixel_test+")(i)",arg=email.element_handle())
                        email.fill('user@example,com')
                        expect(email).to_have_attribute('aria-describedby','auth-error-email')
                        email.locator('..').screenshot(path=str(output/f'{engine.name}-{width}-email.png'))
                        hint=page.locator('#password-hint')
                        field=password.locator('../..')
                        assert hint.evaluate("h=>h.hidden")
                        for count,word in ((7,'символов'),(6,'символов'),(5,'символов'),(4,'символа'),(3,'символа'),(2,'символа'),(1,'символ')):
                            password.fill('a'*(8-count))
                            expect(page.locator('#auth-error-password')).to_have_text(f'Добавь ещё {count} {word}')
                            expect(hint).to_have_text('Подходящие варианты от 8 символов, например:')
                            expect(page.locator('[data-password-suggestions] button:visible').first).to_be_visible()
                            expect(page.locator('[data-password-strength-label]')).to_have_text('Не подходит')
                        # Reproduce a six-character mixed password (synthetic fixture).
                        password.fill('7u#nQZ')
                        expect(page.locator('#auth-error-password')).to_have_text('Добавь ещё 2 символа')
                        expect(hint).to_have_text('Подходящие варианты от 8 символов, например:')
                        short_panel=page.locator('[data-password-suggestions]')
                        toggle.click()
                        short_option=short_panel.locator('button:visible').first
                        candidate=short_option.inner_text()
                        assert len(candidate)>=8 and candidate!='7u#nQZ'
                        assert short_panel.evaluate('p=>p.scrollWidth<=p.clientWidth+1')
                        field.screenshot(path=str(output/f'{engine.name}-{width}-length.png'))
                        short_option.click()
                        expect(password).to_have_value(candidate)
                        expect(page.locator('#fld-confirm_password')).to_have_value(candidate)
                        expect(page.locator('#auth-error-password')).to_be_hidden()
                        expect(short_panel).to_be_hidden()
                        toggle.click()
                        password.fill('')
                        expect(short_panel).to_be_hidden()
                        expect(hint).to_be_hidden()
                        for value,message in (
                            ('qvR!NtMkY@pLW','Добавь хотя бы 1 цифру, чтобы усилить пароль'),
                            ('qvr!ntmk9@plw','Добавь хотя бы 1 заглавную латинскую букву, чтобы усилить пароль'),
                            ('QVR!NTMK9@PLW','Добавь хотя бы 1 строчную латинскую букву, чтобы усилить пароль'),
                            ('qvR7NtMkY9pLW','Добавь хотя бы 1 спецсимвол, чтобы усилить пароль')):
                            password.fill(value)
                            expect(hint).to_contain_text(message)
                            expect(hint).to_be_visible()
                            expect(hint).to_contain_text(', например:')
                            expect(page.locator('[data-password-suggestions] button:visible').first).to_be_visible()
                            expect(page.locator('#auth-error-password')).to_be_hidden()
                            assert hint.evaluate("h=>h.scrollWidth<=h.clientWidth+1")
                        password.fill('abcdefgh1')
                        expect(hint).to_contain_text('Добавь хотя бы 1 заглавную латинскую букву и 1 спецсимвол, чтобы усилить пароль')
                        expect(hint).to_be_visible()
                        expect(page.locator('[data-password-strength-label]')).to_have_text('Слабый')
                        field.screenshot(path=str(output/f'{engine.name}-{width}-advice.png'))
                        password.fill('12345678!aB')
                        expect(page.locator('[data-password-strength-label]')).to_have_text('Слабый')
                        expect(hint).to_contain_text('последовательности')
                        panel=page.locator('[data-password-suggestions]')
                        options=panel.locator('button:visible')
                        expect(panel).to_be_visible()
                        expect(hint).to_contain_text(', например:')
                        expect(panel).to_have_attribute('aria-label','Более надёжные варианты пароля')
                        assert panel.evaluate("p=>getComputedStyle(p).display==='flex' && getComputedStyle(p).flexWrap==='nowrap'")
                        assert options.count()>=1
                        assert panel.evaluate("p=>{const r=p.getBoundingClientRect(),buttons=[...p.querySelectorAll('button:not([hidden])')];return buttons.every(b=>{const x=b.getBoundingClientRect();return Math.abs(x.top-buttons[0].getBoundingClientRect().top)<1&&x.height>=30&&x.height<=34&&x.right<=r.right+.5;});}")
                        expect(options.first).to_contain_text('Вариант')
                        toggle.click()
                        expect(password).to_have_attribute('type','text')
                        candidate=options.first.inner_text()
                        candidate_index=options.first.get_attribute('data-password-suggestion')
                        assert 12<=len(candidate)<=32 and '12345678' not in candidate
                        assert re.search('[a-z]',candidate) and re.search('[A-Z]',candidate) and re.search('[0-9]',candidate) and re.search('[!@#$%&*]',candidate)
                        assert panel.evaluate("p=>p.scrollWidth<=p.clientWidth+1")
                        # Compare the actual visible count against the optimal packing
                        # of measured widths, not merely absence of overflow.
                        assert panel.evaluate("""p=>{
                          const buttons=[...p.querySelectorAll('button')],count=buttons.filter(b=>!b.hidden).length;
                          const hidden=buttons.map(b=>b.hidden);
                          buttons.forEach(b=>b.hidden=false);
                          const sizes=buttons.map(b=>b.getBoundingClientRect().width).sort((a,b)=>a-b);
                          buttons.forEach((b,i)=>b.hidden=hidden[i]);
                          const gap=parseFloat(getComputedStyle(p).columnGap)||0;
                          let sum=0,n=0;
                          for(const width of sizes){const next=width+(n?gap:0);if(sum+next<=p.clientWidth+.1){sum+=next;n++;}else break;}
                          return n===count;
                        }""")
                        field.screenshot(path=str(output/f'{engine.name}-{width}-suggestions.png'))
                        toggle.click()
                        expect(options.first).to_contain_text('Вариант')
                        assert candidate not in panel.inner_text()
                        option=panel.locator('button[data-password-suggestion="'+candidate_index+'"]')
                        # Masked labels may pack differently; reveal if the selected
                        # option is not currently in the masked row.
                        if not option.is_visible():
                            toggle.click()
                            option.click()
                            toggle.click()
                        else:
                            option.click()
                        expect(password).to_have_value(candidate)
                        expect(password).to_have_attribute('type','password')
                        expect(page.locator('#fld-confirm_password')).to_have_value(candidate)
                        expect(panel).to_be_hidden()
                        password.fill('Vq!7tZ#9mK2pF@8rYw4N')
                        expect(page.locator('[data-password-strength-label]')).to_have_text('Надёжный')
                        expect(hint).to_be_hidden()
                        field.screenshot(path=str(output/f'{engine.name}-{width}-strong.png'))
                        password.fill('abЁcd123')
                        expect(hint).to_have_text('Варианты без русских букв, например:')
                        expect(page.locator('[data-password-suggestions] button:visible').first).to_be_visible()
                        expect(password).to_have_attribute('type','password')
                        expect(password).to_have_attribute('aria-invalid','true')
                        assert not password.evaluate(pixel_test)
                        toggle.click()
                        expect(password).to_have_attribute('type','text')
                        assert password.evaluate(pixel_test)
                        password.locator('..').screenshot(path=str(output/f'{engine.name}-{width}-password.png'))
                        toggle.click()
                        expect(password).to_have_attribute('type','password')
                        assert not password.evaluate(pixel_test)
                        canvas=password.locator('..').locator('canvas')
                        expect(canvas).to_be_hidden()
                        assert canvas.evaluate('c=>c.width===0&&c.height===0')
                        toggle.click()
                        password.fill('abcd1234')
                        expect(page.locator('#auth-error-password')).to_be_hidden()
                        assert not password.evaluate(pixel_test)
                        page.locator('[data-password-generate]').click()
                        expect(hint).to_contain_text('Пароль создан и повторён')
                        page.locator('#fld-confirm_password').fill('different-synthetic-value')
                        expect(hint).to_be_hidden()
                        email.fill('user@example.com')
                        expect(page.locator('#auth-error-email')).to_be_hidden()
                        assert not email.evaluate(pixel_test)
                        assert not posts
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_password_meter_continuous_motion(browser_https):
    """Sample real computed transforms on each animation frame in both engines."""
    with sync_playwright() as play:
        for engine in (play.chromium,play.webkit):
            browser=engine.launch(headless=True)
            try:
                for width in (375,1440):
                    context=browser.new_context(viewport={"width":width,"height":844},
                        reduced_motion="no-preference",ignore_https_errors=True)
                    try:
                        page=context.new_page()
                        page.goto(browser_https+'/',wait_until='domcontentloaded')
                        page.locator('header [data-open="login"]').click()
                        page.locator('.modal-foot [data-open="register"]').click()
                        samples=page.evaluate("""async () => {
                          const input=document.querySelector('#fld-password');
                          const meter=document.querySelector('[data-password-strength]');
                          const bars=[...meter.querySelectorAll('i')];
                          const values=()=>bars.map(b=>new DOMMatrixReadOnly(getComputedStyle(b,'::after').transform).a);
                          const frame=()=>new Promise(requestAnimationFrame);
                          // Keep the configured animation budget strict; allow delayed CI frames.
                          const durationMs=parseFloat(getComputedStyle(meter).transitionDuration)*1000;
                          const read=async (target,duration=900)=>{
                            if(target!==null)renderPasswordStrength(input,target);
                            const result=[], start=performance.now();
                            do{await frame();result.push(values());}while(performance.now()-start<duration);
                            return result;
                          };
                          const up=await read(4);
                          const down=await read(1);
                          // Reverse direction mid-flight without jumping to a boundary.
                          renderPasswordStrength(input,4);
                          const start=performance.now();
                          while(performance.now()-start<120)await frame();
                          const before=values();
                          renderPasswordStrength(input,0,'Не подходит');
                          const immediate=values();
                          const reversed=await read(null);
                          return {up,down,before,immediate,reversed,durationMs};
                        }""")
                        assert abs(samples['durationMs']-420)<1
                        def total(frame): return sum(frame)
                        for key,direction,target in (('up',1,4),('down',-1,1),('reversed',-1,0)):
                            frames=samples[key]
                            assert len(frames)>=5
                            assert abs(total(frames[-1])-target)<.03
                            for frame in frames:
                                assert all(-.01<=v<=1.01 for v in frame)
                                assert sum(.02<v<.98 for v in frame)<=1
                                assert all(a+.02>=b for a,b in zip(frame,frame[1:]))
                            sums=[total(f) for f in frames]
                            assert all(direction*(b-a)>=-.03 for a,b in zip(sums,sums[1:]))
                            assert any(.02<v<.98 for f in frames for v in f)
                        assert abs(total(samples['before'])-total(samples['immediate']))<.25
                        page.emulate_media(reduced_motion='reduce')
                        page.wait_for_function("()=>matchMedia('(prefers-reduced-motion: reduce)').matches")
                        assert page.evaluate("""async () => {
                          const i=document.querySelector('#fld-password');
                          renderPasswordStrength(i,4);
                          await new Promise(requestAnimationFrame);
                          return [...document.querySelectorAll('.password-strength-bars i')].every(b=>new DOMMatrixReadOnly(getComputedStyle(b,'::after').transform).a===1);
                        }""")
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_auth_modal_shared_shell(browser_https):
    """The backdrop and dialog survive mode changes; only one height animation."""
    with sync_playwright() as play:
        for engine in (play.chromium,play.webkit):
            browser=engine.launch(headless=True)
            try:
                for width in (375,390,1440):
                    context=browser.new_context(viewport={'width':width,'height':844},ignore_https_errors=True)
                    try:
                        page=context.new_page()
                        page.goto(browser_https+'/',wait_until='domcontentloaded')
                        page.locator('header [data-open="login"]').click()
                        page.locator('#fld-email').fill('owner@example.test')
                        page.locator('#fld-password').fill('synthetic-secret')
                        page.evaluate("""()=>{window.authShell=document.querySelector('.modal');window.authBackdrop=document.querySelector('[data-backdrop]');}""")
                        for mode in ('register','login','register','login'):
                            page.locator('.modal-foot [data-open="'+mode+'"]').click()
                            expect(page.locator('.modal')).to_have_attribute('data-auth-screen',mode)
                            expect(page.locator('#fld-email')).to_have_value('owner@example.test')
                            expect(page.locator('#fld-password')).to_have_value('')
                            assert page.evaluate("document.querySelector('.modal')===window.authShell && document.querySelector('[data-backdrop]')===window.authBackdrop")
                            assert page.evaluate("window.authShell.getAnimations().length<=1")
                        page.wait_for_function("()=>!document.querySelector('.modal').classList.contains('auth-height-motion')",timeout=3000)
                        # Retarget while the previous transition is still running.
                        motion=page.evaluate("""async ()=>{
                          const shell=window.authShell,frame=()=>new Promise(requestAnimationFrame);
                          const height=()=>shell.getBoundingClientRect().height;
                          const initial=height();
                          shell.querySelector('[data-open="register"]').click();
                          const start=performance.now(),samples=[];
                          while(performance.now()-start<110){await frame();samples.push(height());}
                          const before=height();
                          shell.querySelector('[data-open="login"]').click();
                          const after=height(),reverse=[],end=performance.now();
                          while(performance.now()-end<400){await frame();reverse.push(height());}
                          return {initial,before,after,samples,reverse,final:height()};
                        }""")
                        assert abs(motion['before']-motion['after'])<3, motion
                        assert abs(motion['initial']-motion['final'])<3, motion
                        assert max(motion['samples'])>motion['initial']+2, motion
                        assert all(b<=a+3 for a,b in zip(motion['reverse'],motion['reverse'][1:])), motion
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                        page.emulate_media(reduced_motion='reduce')
                        page.wait_for_function("()=>matchMedia('(prefers-reduced-motion: reduce)').matches")
                        page.locator('.modal-foot [data-open="register"]').click()
                        assert page.evaluate("!document.querySelector('.modal').classList.contains('auth-height-motion')")
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_auth_mobile_bottom_sheet_and_compact_controls(browser_https):
    """Auth-only edge-to-edge geometry and compact controls, including short viewports."""
    out=OUTPUT/"auth-mobile-sheet"
    out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        for engine in (play.chromium,play.webkit):
            browser=engine.launch(headless=True)
            try:
                for width,height in ((320,568),(375,667),(390,844),(760,844),(768,844),(1440,900)):
                    context=browser.new_context(viewport={"width":width,"height":height},
                        is_mobile=width<=760,has_touch=width<=760,
                        device_scale_factor=2 if width<=760 else 1,
                        ignore_https_errors=True,reduced_motion="reduce")
                    try:
                        page=context.new_page()
                        page.goto(browser_https+'/',wait_until='domcontentloaded')
                        page.locator('header [data-open="login"]').click()
                        modal=page.locator('.modal[data-auth-screen]')
                        for index,mode in enumerate(('login','register','login')):
                            expect(modal).to_have_attribute('data-auth-screen',mode)
                            geometry=modal.evaluate("""m=>{
                              const r=m.getBoundingClientRect(),s=getComputedStyle(m);
                              const footer=m.querySelector('.modal-fixed-footer');
                              const f=footer.getBoundingClientRect();
                              const buttons=[...footer.querySelectorAll('.form-actions .btn')].map(b=>{
                                const r=b.getBoundingClientRect(),s=getComputedStyle(b);
                                return {height:r.height,width:r.width,padding:parseFloat(s.paddingTop),bottom:r.bottom};
                              });
                              return {x:r.x,right:r.right,bottom:r.bottom,top:r.top,
                                width:innerWidth,height:innerHeight,
                                radius:parseFloat(s.borderBottomLeftRadius),footerBottom:f.bottom,buttons};
                            }""")
                            if width<=760:
                                assert abs(geometry['x'])<=1 and abs(geometry['right']-width)<=1,geometry
                                assert abs(geometry['bottom']-height)<=1 and geometry['top']>=-1,geometry
                                assert geometry['radius']==0,geometry
                                assert abs(geometry['footerBottom']-height)<=1,geometry
                                for button in geometry['buttons']:
                                    assert 44<=button['height']<=64 and button['width']>=44 and button['padding']<=10,geometry
                                    assert button['bottom']<=height,geometry
                            else:
                                assert geometry['x']>0 and geometry['right']<width and geometry['radius']>0,geometry
                            if mode=='register':
                                password=page.locator('#fld-password')
                                password.fill('7u#nQZ')
                                expect(page.locator('#auth-error-password')).to_have_text('Добавь ещё 2 символа')
                                panel=page.locator('[data-password-suggestions]')
                                expect(panel).to_be_visible()
                                page.locator('.password-field:has(#fld-password) [data-password-visibility]').click()
                                assert panel.evaluate("""p=>{
                                  const r=p.getBoundingClientRect(),b=[...p.querySelectorAll('button:not([hidden])')];
                                  return b.length>0&&b.every(x=>{
                                    const q=x.getBoundingClientRect();
                                    return q.height>=30&&q.height<=34&&q.right<=r.right+.5&&Math.abs(q.top-b[0].getBoundingClientRect().top)<1;
                                  })&&p.scrollWidth<=p.clientWidth+1;
                                }""")
                                page.locator('#fld-confirm_password').scroll_into_view_if_needed()
                                assert page.locator('#fld-confirm_password').evaluate("""e=>{
                                  const r=e.getBoundingClientRect(),s=e.closest('.modal-scroll-area').getBoundingClientRect();
                                  return r.top>=s.top-1&&r.bottom<=s.bottom+1;
                                }""")
                                page.screenshot(path=str(out/f'{engine.name}-{width}-register.png'),animations='disabled')
                            else:
                                page.screenshot(path=str(out/f'{engine.name}-{width}-login.png'),animations='disabled')
                            if index<2:
                                next_mode='register' if mode=='login' else 'login'
                                page.locator('.modal-foot [data-open="'+next_mode+'"]').click()
                        page.locator('.modal-close').click()
                        expect(modal).to_have_count(0)
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_auth_email_incomplete_feedback_waits_for_idle(browser_https):
    """Typing, correcting, submitting and changing screens use the same deadline."""
    with sync_playwright() as play:
        for engine in (play.chromium,play.webkit):
            browser=engine.launch(headless=True)
            try:
                for width in (375,1440):
                    context=browser.new_context(viewport={"width":width,"height":844},
                        ignore_https_errors=True,reduced_motion="reduce")
                    try:
                        page=context.new_page()
                        page.goto(browser_https+'/',wait_until='domcontentloaded')
                        page.locator('header [data-open="login"]').click()
                        email=page.locator('#fld-email')
                        error=page.locator('#auth-error-email')
                        email.fill('12@mail')
                        page.wait_for_timeout(1100)
                        expect(error).to_be_hidden()
                        email.fill('12@mail.')
                        page.wait_for_timeout(1100)
                        expect(error).to_be_hidden()
                        assert email.get_attribute('aria-invalid') is None
                        expect(error).to_have_text('Допиши окончание домена, например ru или com',timeout=2500)
                        email.fill('12@mail.r')
                        expect(error).to_be_hidden()
                        email.fill('12@mail.ru')
                        page.wait_for_timeout(2100)
                        expect(error).to_be_hidden()
                        assert email.get_attribute('aria-invalid') is None
                        email.fill('12@#mail')
                        expect(error).to_have_text('Убери символ # из домена',timeout=500)
                        email.fill('12@mail.')
                        expect(error).to_be_hidden()
                        page.locator('#modal-form').evaluate('form=>form.requestSubmit()')
                        expect(error).to_have_text('Допиши окончание домена, например ru или com',timeout=500)
                        email.fill('12@mail')
                        expect(error).to_be_hidden()
                        page.locator('.modal-foot [data-open="register"]').click()
                        page.locator('#fld-email').fill('valid@example.com')
                        page.wait_for_timeout(2100)
                        expect(page.locator('#auth-error-email')).to_be_hidden()
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_chat_marker_exclusive_across_resolutions_and_pointer_types(browser_https,application):
    """Actual game + computed marker visibility, not merely aria attributes."""
    from uuid import uuid4
    from test_cloud import login, call
    owner=login(application)
    guest=application.test_client()
    eid=call(owner,'POST','/api/santas',{'title':'Chat marker '+uuid4().hex[:8]},201).json['id']
    token=call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Marker guest'},201).json['participant_token']
    call(owner,'POST',f'/api/santas/{eid}/participants',{'name':'Marker second guest'},201)
    endpoint=f'/api/participant/{token}/messages/'
    route=browser_https+'/p/'+token
    rooms=('general','to-recipient','from-santa')
    out=OUTPUT/'chat-marker'
    out.mkdir(parents=True,exist_ok=True)
    marker_visible="""room=>{
      const buttons=[...document.querySelectorAll('#game-chat button[data-chat-room]')];
      const selected=buttons.filter(b=>b.getAttribute('aria-pressed')==='true');
      return selected.length===1&&selected[0].dataset.chatRoom===room&&
       buttons.every(b=>{
         const s=getComputedStyle(b,'::before');
         return b.dataset.chatRoom===room?s.content!=='none'&&Number(s.opacity)>=.9:
           s.content==='none'&&Number(s.opacity)===0&&s.animationName==='none';
       });
    }"""
    with sync_playwright() as play:
        # Before drawing, the one available chat is selected, even on touch.
        browser=play.webkit.launch(headless=True)
        try:
            context=browser.new_context(viewport={'width':375,'height':812},
                is_mobile=True,has_touch=True,ignore_https_errors=True)
            page=context.new_page()
            page.goto(route)
            expect(page.locator('#game-chat [data-chat-room]')).to_have_count(1)
            page.wait_for_function(marker_visible,arg='general')
            context.close()
        finally:
            browser.close()
        call(owner,'POST',f'/api/santas/{eid}/draw',{})
        for room in rooms:
            call(guest,'POST',endpoint+room,{'message':'Marker '+room},201)
        for engine in ('chromium','webkit'):
            browser=getattr(play,engine).launch(headless=True)
            try:
                for touch in (False,True):
                    context=browser.new_context(viewport={'width':390,'height':844},
                        is_mobile=touch,has_touch=touch,ignore_https_errors=True)
                    try:
                        page=context.new_page()
                        page.goto(route)
                        tabs=page.locator('#game-chat [data-chat-room]')
                        expect(tabs).to_have_count(3)
                        page.wait_for_function(marker_visible,arg='general')
                        for width in (320,375,390,430,760,761,768,1024,1440):
                            page.set_viewport_size({'width':width,'height':844})
                            chat=page.locator('.game-chat-messages')
                            initial_height=chat.bounding_box()['height']
                            for room in ('to-recipient','from-santa','general'):
                                tab=page.locator(f'#game-chat [data-chat-room="{room}"]')
                                if not touch:
                                    tab.hover()
                                    # Hover must not create a second marker.
                                    assert tab.evaluate("""b=>{
                                      const s=getComputedStyle(b,'::before');
                                      return b.getAttribute('aria-pressed')==='true'||
                                        (s.content==='none'&&Number(s.opacity)===0);
                                    }""")
                                if touch:
                                    tab.tap()
                                else:
                                    tab.click()
                                # Inactive brushes disappear immediately, even
                                # before the new selected brush finishes drawing.
                                expect(page.locator('#game-chat [aria-pressed="true"]')).to_have_count(1)
                                assert tabs.evaluate_all("""bs=>bs.filter(b=>b.getAttribute('aria-pressed')!=='true').every(b=>getComputedStyle(b,'::before').content==='none')""")
                                page.wait_for_function(marker_visible,arg=room)
                                expect(page.locator('.game-chat-messages')).to_contain_text('Marker '+room)
                                assert abs(chat.bounding_box()['height']-initial_height)<=1
                                assert chat.evaluate("el=>getComputedStyle(el).scrollbarWidth==='none'||getComputedStyle(el,'::-webkit-scrollbar').display==='none'")
                                for other in rooms:
                                    if other!=room:
                                        expect(page.locator('.game-chat-messages')).not_to_contain_text('Marker '+other)
                            assert page.locator('#game-chat').evaluate('e=>e.getBoundingClientRect().width<=innerWidth+1')
                            if width in (375,1440):
                                page.locator('#game-chat').screenshot(path=str(out/f'{engine}-{width}-{"touch" if touch else "mouse"}.png'),animations='disabled')
                        # Reduced motion, keyboard, and sending to the selected room.
                        page.emulate_media(reduced_motion='reduce')
                        tab=page.locator('#game-chat [data-chat-room="from-santa"]')
                        tab.focus()
                        tab.press('Enter')
                        page.wait_for_function(marker_visible,arg='from-santa')
                        message='Selected room '+engine+str(touch)
                        page.locator('#game-chat-input').fill(message)
                        page.locator('#game-chat-form button[type="submit"]').click()
                        expect(page.locator('.game-chat-messages')).to_contain_text(message)
                        page.wait_for_function(marker_visible,arg='from-santa')
                        tab=page.locator('#game-chat [data-chat-room="general"]')
                        tab.press('Enter')
                        expect(page.locator('.game-chat-messages')).not_to_contain_text(message)
                        page.wait_for_function(marker_visible,arg='general')
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
def test_navigation_filter_markers_focus_and_noop_mutations(browser_https,application):
    """Real local UI, computed brushes, responsive geometry and DOM no-op."""
    from uuid import uuid4
    from test_cloud import login, call
    owner=login(application)
    suffix=uuid4().hex[:8]
    for category in ('День рождения','Новый год'):
        call(owner,'POST','/api/lists',{'title':'Audit '+category+' '+suffix,
             'occasion':category,'visibility':'private'},201)
    eid=call(owner,'POST','/api/santas',{'title':'Navigation audit '+suffix},201).json['id']
    widths=(320,375,390,430,760,761,768,1024,1440)
    results=[]
    out=OUTPUT/'navigation-selection'
    out.mkdir(parents=True,exist_ok=True)
    visible="""({selector,attribute})=>{
      const elements=[...document.querySelectorAll(selector)];
      const selected=elements.filter(e=>attribute==='aria-current'?e.hasAttribute(attribute):e.getAttribute(attribute)==='true');
      return elements.length>0&&selected.length===1&&elements.every(e=>{
        const style=getComputedStyle(e,'::before');
        return selected.includes(e)?style.content!=='none'&&Number(style.opacity)>=.9:
          style.content==='none'&&Number(style.opacity)===0&&style.animationName==='none';
      });
    }"""
    noop="""el=>{
      const root=el.closest('main,.notification-dialog');
      const observer=new MutationObserver(()=>{});
      observer.observe(root,{subtree:true,attributes:true,childList:true,characterData:true});
      el.click();
      const records=observer.takeRecords();observer.disconnect();
      return records.length;
    }"""
    with sync_playwright() as play:
        for engine in ('chromium','webkit'):
            browser=getattr(play,engine).launch(headless=True)
            try:
                for touch in (False,True):
                    ctx=browser.new_context(viewport={'width':390,'height':844},
                        is_mobile=touch,has_touch=touch,ignore_https_errors=True,
                        reduced_motion='no-preference')
                    try:
                        page=ctx.new_page()
                        page.goto(browser_https+'/')
                        browser_login(page)
                        page.wait_for_function("() => typeof ownerWarmupReady !== 'undefined' && ownerWarmupReady && !socialUnreadBusy",timeout=15000)
                        traffic=[]
                        page.on('request',lambda req: traffic.append((req.method,urlsplit(req.url).path)) if req.url.startswith(browser_https+'/api/') else None)
                        def assert_group(selector,attribute):
                            page.wait_for_function(visible,arg={'selector':selector,'attribute':attribute})
                        def exercise(selector,attribute,indices=None):
                            buttons=page.locator(selector)
                            count=buttons.count()
                            assert count>=2
                            for i in (indices if indices is not None else range(count)):
                                b=buttons.nth(i)
                                if not touch:
                                    b.hover()
                                    assert_group(selector,attribute)
                                if touch:b.tap()
                                else:b.click()
                                expect(b).to_have_attribute(attribute,'true')
                                assert buttons.evaluate_all("""(bs,attr)=>bs.filter(e=>e.getAttribute(attr)!=='true').every(e=>getComputedStyle(e,'::before').content==='none')""",attribute), (engine,touch,selector,i)
                                if selector=='.wishlist-view-tabs button':
                                    expect(page.locator('#wishlist-view-content')).not_to_contain_text('Загружаем вишлисты друзей…')
                                assert_group(selector,attribute)
                                before=len(traffic)
                                assert b.evaluate(noop)==0, (engine,touch,selector,i)
                                page.evaluate('() => new Promise(requestAnimationFrame)')
                                assert not [r for r in traffic[before:] if r[1] != '/api/notifications/unread-count'], (engine,touch,selector,i,traffic[before:])
                            if attribute=='aria-selected':
                                selected=page.locator(selector+'[aria-selected="true"]')
                                assert selected.get_attribute('tabindex')=='0'
                                def assert_focus(button):
                                    expect(button).to_be_focused()
                                    expect(button).to_have_attribute('aria-selected','true')
                                    assert button.evaluate("""e=>{
                                      const s=getComputedStyle(e);
                                      return s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>=2;
                                    }"""), (engine,touch,selector)
                                selected.focus()
                                for key, target in (('Home',buttons.first),('End',buttons.last),
                                                    ('ArrowRight',buttons.first),('ArrowLeft',buttons.last)):
                                    page.keyboard.press(key)
                                    assert_focus(target)
                                page.keyboard.press('Tab')
                                assert not buttons.evaluate_all('bs=>bs.includes(document.activeElement)')
                                page.keyboard.press('Shift+Tab')
                                assert_focus(buttons.last)
                                page.keyboard.press('Home')
                                assert_focus(buttons.first)
                                assert_group(selector,attribute)
                        # Warm navigation must retain the existing header and
                        # previously rendered owner views. No new page request.
                        page.evaluate("nav('/lists')")
                        expect(page.locator('.wishlists-page')).to_be_visible()
                        page.evaluate("window.__auditHeader=document.querySelector('header');window.__auditLists=document.querySelector('main')")
                        page.evaluate("nav('/santas')")
                        expect(page.locator('.santa-state-tabs')).to_be_visible()
                        page.evaluate("nav('/lists')")
                        assert page.evaluate("window.__auditHeader===document.querySelector('header')&&window.__auditLists===document.querySelector('main')")
                        for width in widths:
                            page.set_viewport_size({'width':width,'height':844})
                            page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                            expect(page.locator('header .nav')).to_be_visible()
                            assert_group('header .nav a','aria-current')
                            inactive=page.locator('header .nav a:not([aria-current])').first
                            inactive.focus()
                            assert_group('header .nav a','aria-current')
                            if not touch:inactive.hover()
                            assert_group('header .nav a','aria-current')
                            expect(page.locator('header .nav a[data-nav="/lists"]')).to_have_attribute('aria-current','page')
                            # Switch local filters: existing cards remain mounted.
                            filters='.wishlist-filters button'
                            all_filter=page.locator(filters).filter(has_text=re.compile('^Все$'))
                            all_filter.click()
                            page.evaluate("window.__auditCards=[...document.querySelectorAll('[data-occasion]')]")
                            exercise(filters,'aria-pressed',[1,0])
                            assert page.evaluate("window.__auditCards.every((node,i)=>node===document.querySelectorAll('[data-occasion]')[i])")
                            assert page.locator('[data-occasion][hidden]').count()==0
                            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
                            page.locator('.wishlist-filters').screenshot(path=str(out/f'{engine}-{touch}-{width}-filters.png'),animations='disabled')
                            exercise('.wishlist-view-tabs button','aria-selected',[1,0])
                            expect(page.locator('#wishlist-view-content')).to_have_attribute('aria-labelledby','wishlist-tab-mine')
                            before=len(traffic)
                            page.evaluate("nav('/santas')")
                            expect(page.locator('.santa-state-tabs')).to_be_visible()
                            assert not [r for r in traffic[before:] if r[1] == '/api/santas'], (engine,touch,width,traffic[before:])
                            exercise('.santa-state-tabs button','aria-selected',[1,0])
                            expect(page.locator('#santa-state-panel')).to_have_attribute('aria-labelledby','santa-tab-current')
                            expect(page.locator('[data-santa-card-state="finished"]:not([hidden])')).to_have_count(0)
                            before=len(traffic)
                            page.evaluate("nav('/lists')")
                            expect(page.locator('.wishlist-view-tabs')).to_be_visible()
                            assert not [r for r in traffic[before:] if r[1] == '/api/lists'], (engine,touch,width,traffic[before:])
                            results.append({'engine':engine,'touch':touch,'width':width,'navigation':'passed'})
                        page.evaluate("id=>nav('/santa/'+id)",eid)
                        expect(page.locator('#game-chat')).to_be_visible()
                        expect(page.locator('header .nav a[data-nav="/santas"]')).to_have_attribute('aria-current','location')
                        page.go_back()
                        expect(page.locator('.wishlist-view-tabs')).to_be_visible()
                        expect(page.locator('header .nav a[data-nav="/lists"]')).to_have_attribute('aria-current','page')
                        bell=page.locator('header .header-bell')
                        bell.click()
                        expect(page.locator('.notification-dialog')).to_be_visible()
                        expect(bell).to_have_attribute('aria-expanded','true')
                        for width in widths:
                            page.set_viewport_size({'width':width,'height':844})
                            exercise('.notification-tabs button','aria-selected',[1,2,3,0])
                            assert page.locator('.notification-tabs').evaluate('e=>e.getBoundingClientRect().width<=innerWidth+1')
                            page.locator('.notification-tabs').screenshot(path=str(out/f'{engine}-{touch}-{width}-notifications.png'),animations='disabled')
                            next(r for r in results if r['engine']==engine and r['touch']==touch and r['width']==width)['notifications']='passed'
                        page.keyboard.press('Escape')
                        expect(bell).to_have_attribute('aria-expanded','false')
                        expect(bell).to_be_focused()
                    finally:
                        ctx.close()
            finally:
                browser.close()

    assert len(results)==36 and all(r.get('notifications')=='passed' for r in results)
    (out/'matrix.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["chromium","webkit"])
def test_owner_cache_revalidation_lru_session_and_dom(browser_https,application,engine):
    from test_cloud import login, call
    from uuid import uuid4
    owner=login(application)
    first='Cache first '+uuid4().hex[:8]
    second='Cache second '+uuid4().hex[:8]
    lid=call(owner,'POST','/api/lists',{'title':first,'occasion':'День рождения'},201).json['id']
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            context=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
            page=context.new_page()
            page.goto(browser_https+'/')
            browser_login(page)
            page.wait_for_function("() => ownerWarmupReady && !socialUnreadBusy",timeout=15000)
            page.evaluate("nav('/lists')")
            expect(page.get_by_text(first,exact=True)).to_be_visible()
            page.evaluate("""id=>{
              window.cacheMain=document.querySelector('#page-view main');
              window.cacheHeader=document.querySelector('header');
              window.cacheCard=document.querySelector('a[data-nav="/list/'+id+'"]').closest('article');
            }""",lid)
            page.locator('[data-wishlist-filter="День рождения"]').click()
            page.locator('[data-wishlist-filter="День рождения"]').focus()
            traffic=[]
            page.on('request',lambda r: traffic.append(urlsplit(r.url).path) if '/api/' in r.url else None)
            call(owner,'POST','/api/lists',{'title':second,'occasion':'День рождения'},201)
            page.evaluate("""async()=>{
              const entry=ownerDataCache.get('/api/lists');entry.expires=0;
              await Promise.all([revalidateOwnerRead('/api/lists',entry),revalidateOwnerRead('/api/lists',entry)]);
            }""")
            expect(page.get_by_text(second,exact=True)).to_be_visible()
            assert traffic.count('/api/lists')==1
            assert page.evaluate("""id=>cacheMain===document.querySelector('#page-view main') &&
              cacheHeader===document.querySelector('header') &&
              cacheCard===document.querySelector('a[data-nav="/list/'+id+'"]').closest('article') &&
              document.activeElement?.dataset.wishlistFilter==='День рождения' &&
              document.activeElement?.getAttribute('aria-pressed')==='true'""",lid)
            assert page.evaluate("""async()=>{
              const observer=new MutationObserver(()=>{});
              observer.observe(cacheMain,{subtree:true,childList:true,attributes:true,characterData:true});
              await revalidateOwnerRead('/api/lists',ownerDataCache.get('/api/lists'));
              const count=observer.takeRecords().length;observer.disconnect();return count;
            }""")==0
            # Check the actual cache implementation, without issuing synthetic HTTP requests.
            result=page.evaluate("""()=>{
              for(let i=1;i<=100;i++)seedOwnerCache('/api/lists/'+(90000+i),{id:i});
              const size=ownerDataCache.size;
              const firstGone=!ownerDataCache.has('/api/lists/90001');
              ownerEntry('/api/lists/90100');
              for(let i=101;i<=110;i++)seedOwnerCache('/api/lists/'+(90000+i),{id:i});
              const recentKept=ownerDataCache.has('/api/lists/90100');
              const original=Date.now;Date.now=()=>original()+11*60*1000;
              try{pruneOwnerData();return {size,firstGone,recentKept,remaining:[...ownerDataCache.keys()].filter(k=>!ownerPinned(k)).length,pinned:ownerDataCache.has('/api/lists')};}
              finally{Date.now=original;}
            }""")
            assert result['size']<=32 and result['firstGone'] and result['recentKept']
            assert result['remaining']==0 and result['pinned']
            assert page.evaluate("""()=>{
              seedOwnerCache('/api/lists/99998',{large:'x'.repeat(5*1024*1024)});
              return !ownerDataCache.has('/api/lists/99998');
            }""")
            # A GET started before a write cannot overwrite the newer result.
            assert page.evaluate("""async()=>{
              const original=window.fetch;const callbacks=[];
              window.fetch=()=>new Promise(resolve=>callbacks.push(resolve));
              try{
               const old=api('/api/lists/99997');
               invalidateOwnerDataForMutation('/api/lists/99997');
               const fresh=api('/api/lists/99997');
               callbacks[1](new Response(JSON.stringify({value:'fresh'}),{status:200}));
               await fresh;
               callbacks[0](new Response(JSON.stringify({value:'old'}),{status:200}));
               return (await old).value==='fresh'&&ownerDataCache.get('/api/lists/99997').value.value==='fresh'&&callbacks.length===2;
              }finally{window.fetch=original;}
            }""")
            # Stale network response may not cross even a same-user session epoch.
            assert page.evaluate("""async()=>{
              const original=window.fetch;let resolve;
              window.fetch=()=>new Promise(r=>resolve=r);
              try{
               const pending=api('/api/lists/99999').then(()=>false,e=>e.name==='AbortError');
               clearOwnerDataCache();
               resolve(new Response(JSON.stringify({private:'old-session'}),{status:200}));
               return await pending && !ownerDataCache.has('/api/lists/99999');
              }finally{window.fetch=original;}
            }""")
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["chromium","webkit"])
def test_chat_incremental_history_and_cleanup(browser_https,application,engine):
    from test_cloud import login,call
    from cloud import db
    owner=login(application)
    eid=call(owner,'POST','/api/santas',{'title':'Chat performance regression'},201).json['id']
    with db.transaction(write=True) as con:
        pid=con.execute('SELECT id FROM participants WHERE event_id=?',(eid,)).fetchone()['id']
        for i in range(65):
            con.execute("INSERT INTO santa_messages(event_id,sender_id,room,message,created_at) VALUES(?,?,'general',?,now())",(eid,pid,f'perf-message-{i}'))
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            page=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844}).new_page()
            page.goto(browser_https+'/')
            browser_login(page)
            page.evaluate("id=>nav('/santa/'+id)",eid)
            expect(page.locator('.chat-message')).to_have_count(60)
            page.evaluate("window.chatLast=document.querySelector('.chat-message:last-child')")
            # Hold a real delta GET while a user asks for older history.
            # Two rapid clicks must deduplicate only the older-page request.
            held=[]
            older_requests=[]
            delta_pattern=re.compile(r'/messages/general\?after=\d+$')
            page.route(delta_pattern,lambda route:held.append(route))
            page.on('request',lambda r:older_requests.append(r.url) if '/messages/general?before=' in r.url else None)
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            for _ in range(100):
                if held:break
                page.wait_for_timeout(50)
            assert len(held)==1
            page.evaluate("""()=>{const button=document.querySelector('[data-chat-older]');button.click();button.click();}""")
            expect(page.locator('.chat-message')).to_have_count(65)
            assert len(older_requests)==1
            # Visibility refresh reschedules the timer only after the delta
            # response is consumed and merged. Wait for that observable
            # completion rather than assuming 150ms is sufficient.
            previous_timer=page.evaluate('gameChatTimer')
            with page.expect_response(lambda r:delta_pattern.search(r.url) is not None):
                held[0].continue_()
            page.unroute(delta_pattern)
            page.wait_for_function('(previous)=>gameChatTimer!==null&&gameChatTimer!==previous',
                                   arg=previous_timer,timeout=5000)
            assert page.evaluate("chatLast===document.querySelector('.chat-message:last-child')")
            with db.transaction(write=True) as con:
                con.execute("INSERT INTO santa_messages(event_id,sender_id,room,message,created_at) VALUES(?,?,'general',?,now())",(eid,pid,'perf-live-new'))
            requests=[]
            page.on('request',lambda r: requests.append(r.url) if '/messages/' in r.url else None)
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            expect(page.get_by_text('perf-live-new',exact=True)).to_be_visible()
            assert any('?after=' in r for r in requests)
            assert page.evaluate("chatLast.isConnected")
            page.evaluate("nav('/lists')")
            expect(page.locator('.wishlists-page')).to_be_visible()
            assert page.evaluate("gameChatTimer===null && gameRosterTimer===null && gameLifecycleCleanup.length===0 && gameGiftDisposers.size===0")
            # Repeated route lifecycle, not a heap-size claim: every exit
            # must release timers, listeners and observers.
            for _ in range(3):
                page.evaluate("id=>nav('/santa/'+id)",eid)
                expect(page.locator('#game-chat')).to_be_visible()
                page.evaluate("nav('/lists')")
                expect(page.locator('.wishlists-page')).to_be_visible()
                assert page.evaluate("gameChatTimer===null && gameRosterTimer===null && gameLifecycleCleanup.length===0 && gameGiftDisposers.size===0")
            from test_cloud import IDS
            with db.transaction(write=True) as con:
                for i in range(65):
                    con.execute("INSERT INTO social_notifications(recipient_id,kind,message,target_path) VALUES(?,'wishlist_new',?,'/')",
                                (IDS['owner@example.test'],f'perf-{engine}-notice-{i}'))
            page.evaluate("dropOwnerRead('/api/notifications');nav('/notifications',{force:true})")
            expect(page.get_by_text(f'perf-{engine}-notice-64',exact=True)).to_be_visible()
            page.evaluate("window.noticeFirst=document.querySelector('[data-notification-id]')")
            page.locator('[data-notification-pagination] [data-social-action="notification-older"]').click()
            expect(page.get_by_text(f'perf-{engine}-notice-0',exact=True)).to_be_visible()
            assert page.evaluate("noticeFirst===document.querySelector('[data-notification-id]')")
            page.locator('header .header-bell').click()
            expect(page.locator('.notification-dialog')).to_be_visible()
            page.locator('.notification-dialog [data-social-action="notification-older"]').click()
            expect(page.locator('.notification-dialog').get_by_text(f'perf-{engine}-notice-0',exact=True)).to_be_visible()
            page.locator('.modal-close').click()
            assert page.evaluate("notificationModalItems.length===0")
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_performance_soak_real_polling_session_and_retention(browser_https, application, engine):
    """Real timers/HTTP and two authenticated fixture users. No hosted DB.
    Chromium CDP snapshots are analyzed in RAM; never upload raw heap contents.
    """
    import gc
    import time
    from uuid import uuid4
    from test_cloud import login, call
    from cloud import db

    owner=login(application)
    other=login(application,'other@example.test')
    suffix=uuid4().hex[:8]
    own_title='Soak private A '+suffix
    other_title='Soak private B '+suffix
    call(owner,'POST','/api/lists',{'title':own_title,'visibility':'private'},201)
    call(other,'POST','/api/lists',{'title':other_title,'visibility':'private'},201)
    eid=call(owner,'POST','/api/santas',{'title':'Soak game '+suffix},201).json['id']
    with db.transaction(write=True) as con:
        pid=con.execute('SELECT id FROM participants WHERE event_id=?',(eid,)).fetchone()['id']
        con.execute("INSERT INTO santa_messages(event_id,sender_id,room,message,created_at) VALUES(?,?,'general','soak seed',now())",(eid,pid))
    for n in range(2):
        call(owner,'POST',f'/api/santas/{eid}/my-wishes',{'title':f'Soak gift {n}'},201)

    output=OUTPUT/'performance-soak'
    output.mkdir(parents=True,exist_ok=True)
    report={'engine':engine,'scope':'CI localhost PostgreSQL; mock external Auth; real browser HTTP and wall time'}
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            context=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda e: errors.append(str(e)))
            page.goto(browser_https+'/')
            browser_login(page)
            page.wait_for_function("()=>ownerWarmupReady&&!socialUnreadBusy",timeout=15000)
            page.evaluate("nav('/lists')")
            expect(page.get_by_text(own_title,exact=True)).to_be_visible()
            page.evaluate("window.soakRoots=[]")
            cdp=context.new_cdp_session(page) if engine=='chromium' else None

            def sample_heap():
                if cdp is None:
                    return None
                cdp.send('HeapProfiler.collectGarbage')
                cdp.send('HeapProfiler.collectGarbage')
                chunks=[]
                def add_chunk(event):
                    chunks.append(event['chunk'])
                cdp.on('HeapProfiler.addHeapSnapshotChunk',add_chunk)
                try:
                    cdp.send('HeapProfiler.takeHeapSnapshot',{'reportProgress':False})
                finally:
                    cdp.remove_listener('HeapProfiler.addHeapSnapshotChunk',add_chunk)
                raw=json.loads(''.join(chunks))
                fields=raw['snapshot']['meta']['node_fields']
                width=len(fields)
                nodes=raw['nodes']
                types=raw['snapshot']['meta']['node_types'][0]
                strings=raw['strings']
                detached=0
                if 'detachedness' in fields:
                    offset=fields.index('detachedness')
                    detached=sum(nodes[i+offset]==2 for i in range(0,len(nodes),width))
                native_detached=sum(types[nodes[i]]=='native' and strings[nodes[i+fields.index('name')]].startswith('Detached ')
                                    for i in range(0,len(nodes),width))
                result={'snapshot_nodes':len(nodes)//width,
                        'snapshot_detached':detached,'snapshot_native_detached':native_detached,
                        **cdp.send('Runtime.getHeapUsage'),**cdp.send('Memory.getDOMCounters')}
                del raw,nodes,strings,chunks
                gc.collect()
                return result

            def cycle():
                # Playwright locator waits can retain their matched DOM in the
                # injected automation world. Use an in-page readiness probe
                # returning primitives only; do not export handles to CDP.
                assert page.evaluate("""async({id,title})=>{
                  const until=async predicate=>{
                    const start=performance.now();
                    while(!predicate()){
                      if(performance.now()-start>15000)throw Error('soak route not ready');
                      await new Promise(resolve=>setTimeout(resolve,20));
                    }
                  };
                  nav('/santa/'+id);
                  await until(()=>[...document.querySelectorAll('.chat-message p')].some(n=>n.textContent==='soak seed'));
                  if(typeof WeakRef==='function')soakRoots.push(new WeakRef(document.querySelector('#game-chat')));
                  nav('/lists');
                  await until(()=>document.querySelector('.wishlists-page')?.textContent.includes(title));
                  return gameChatTimer===null&&gameRosterTimer===null&&gameLifecycleCleanup.length===0&&gameGiftDisposers.size===0;
                }""",{'id':eid,'title':own_title})
            for _ in range(3):cycle()
            page.wait_for_timeout(400)
            report['heap_before']=sample_heap()
            for _ in range(20):cycle()
            page.wait_for_timeout(400)
            report['heap_after']=sample_heap()
            if cdp:
                cdp.send('HeapProfiler.collectGarbage')
                report['old_chat_roots_retained']=page.evaluate("soakRoots.filter(r=>r.deref()).length")
                assert report['old_chat_roots_retained']<=2, report
                before,after=report['heap_before'],report['heap_after']
                # Bounded cache and unavoidable browser/automation noise, not a
                # universal proof of zero leaks. Allow warm JIT/DOM variation.
                assert after['usedSize']-before['usedSize']<4*1024*1024,report
                assert after['nodes']-before['nodes']<500,report
                assert after['jsEventListeners']-before['jsEventListeners']<80,report
            report['cycles']=23
            report['cache']=page.evaluate("""()=>({data:ownerDataCache.size,views:ownerTabViews.size,
                 detailBytes:[...ownerDataCache].filter(([k])=>!ownerPinned(k)).reduce((n,[k,v])=>n+(v.bytes||0),0)})""")
            assert report['cache']['data']<=32 and report['cache']['views']<=6
            assert report['cache']['detailBytes']<=8*1024*1024

            # Real wall-time polling: do not accelerate or replace application timers.
            events=[]
            finished=[]
            all_api=[]
            origin=browser_https
            def record_request(r):
                p=urlsplit(r.url).path
                if r.url.startswith(origin+'/api/'):all_api.append(r)
                if r.url.startswith(origin+'/api/') and (p.endswith('/roster') or '/messages/' in p):
                    events.append({'kind':'roster' if p.endswith('/roster') else 'chat',
                                   't':time.monotonic(),'delta':bool(urlsplit(r.url).query)})
            page.on('request',record_request)
            page.on('requestfinished',lambda r:finished.append(r) if r.url.startswith(origin+'/api/') else None)
            page.bring_to_front()
            page.evaluate("id=>nav('/santa/'+id)",eid)
            expect(page.get_by_text('soak seed',exact=True)).to_be_visible()
            page.wait_for_timeout(113000)
            chat=[x for x in events if x['kind']=='chat']
            roster=[x for x in events if x['kind']=='roster']
            report['polling']={'wall_seconds':113,'chat_count':len(chat),'roster_count':len(roster),
                'chat_intervals':[round(b['t']-a['t'],2) for a,b in zip(chat,chat[1:])],
                'roster_intervals':[round(b['t']-a['t'],2) for a,b in zip(roster,roster[1:])],
                'delta_requests':sum(x['delta'] for x in chat)}
            sizes=[]
            for req in finished:
                try:sizes.append(req.sizes())
                except Exception:pass
            report['polling']['api_requests']=len(all_api)
            report['polling']['sized_responses']=len(sizes)
            report['polling']['response_body_bytes']=sum(v['responseBodySize'] for v in sizes)
            report['polling']['response_header_bytes']=sum(v['responseHeadersSize'] for v in sizes)
            assert len(chat)==4 and len(roster)==3,report
            for actual,expected in zip(report['polling']['chat_intervals'],[15,30,60]):
                assert abs(actual-expected)<5,report
            for actual,expected in zip(report['polling']['roster_intervals'],[30,60]):
                assert abs(actual-expected)<5,report
            assert report['polling']['delta_requests']==3,report
            page.evaluate("nav('/lists')")
            expect(page.get_by_text(own_title,exact=True)).to_be_visible()
            count=len(events)
            page.wait_for_timeout(16000)
            assert len(events)==count,report
            report['requests_after_exit_16s']=len(events)-count

            # Real application logout/login in same browser context plus another
            # tab sharing cookies: previous private DOM must disappear.
            page.evaluate("nav('/')")
            expect(page.locator('.dashboard-page')).to_be_visible()
            second=context.new_page()
            second.goto(browser_https+'/')
            expect(second.locator('.dashboard-page')).to_be_visible()
            second.evaluate("nav('/lists')")
            expect(second.get_by_text(own_title,exact=True)).to_be_visible()
            page.bring_to_front()
            page.locator('header [data-action="logout"]').click()
            expect(page.locator('header [data-open="login"]')).to_be_visible()
            expect(second.locator('header [data-open="login"]')).to_be_visible()
            assert second.evaluate("ownerDataCache.size===0&&ownerTabViews.size===0&&gameLifecycleCleanup.length===0")
            expect(second.get_by_text(own_title,exact=True)).to_have_count(0)
            browser_login(page,'other@example.test')
            page.evaluate("nav('/lists')")
            expect(page.get_by_text(other_title,exact=True)).to_be_visible()
            expect(page.get_by_text(own_title,exact=True)).to_have_count(0)
            second.evaluate("nav('/lists',{force:true})")
            expect(second.get_by_text(other_title,exact=True)).to_be_visible()
            expect(second.get_by_text(own_title,exact=True)).to_have_count(0)
            report['account_switch']='passed'
            report['page_errors']=len(errors)
            assert not errors,errors
        finally:
            (output/f'{engine}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_friends_exact_search_and_qr_invite(browser_https,application,engine):
    from test_cloud import login,call,IDS
    from cloud import db
    owner=login(application);other=login(application,'other@example.test')
    aid,bid=map(str,IDS.values())
    with db.transaction(write=True) as con:
        con.execute('DELETE FROM friendships WHERE user_low=? AND user_high=?',(aid,bid))
    call(owner,'PATCH','/api/profile/me',{'name':'Александр','handle':'qrowner','last_name':'Иванов','patronymic':'Петрович','show_full_name':True,'discoverable':True})
    call(other,'PATCH','/api/profile/me',{'name':'Александр','handle':'qrother','discoverable':True})
    try:
        with sync_playwright() as play:
            browser=getattr(play,engine).launch(headless=True)
            try:
                ctx=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
                page=ctx.new_page();page.goto(browser_https+'/');browser_login(page,landing='identity')
                page.evaluate("nav('/friends')")
                search=page.locator('#social-search-form input[name=q]')
                search.fill('@qrother');page.locator('#social-search-form button').click()
                result=page.locator('#social-search-results')
                expect(result.get_by_text('@qrother',exact=True)).to_be_visible()
                page.evaluate("window.friendInput=document.querySelector('#social-search-form input')")
                result.get_by_role('button',name='В друзья',exact=True).click()
                expect(result.get_by_text('Заявка отправлена',exact=True)).to_be_visible()
                assert page.evaluate("friendInput===document.querySelector('#social-search-form input')")
                expect(search).to_have_value('@qrother')
                with page.expect_response(lambda res: res.url.endswith('/api/friend-invites/me') and res.request.method=='POST') as invite_response:
                    page.get_by_role('button',name='Пригласить друга').click()
                rows=invite_response.value.json()['qr']
                link=page.locator('#personal-invite-link')
                expect(link).to_be_visible()
                url=link.get_attribute('data-invite-url');assert url.startswith(browser_https+'/i/')
                expect(page.locator('.personal-invite-modal input')).to_have_count(0)
                expect(page.locator('.personal-invite-modal [data-referral-count]')).to_have_count(0)
                expect(page.get_by_role('button',name='Поделиться ссылкой',exact=True)).to_have_count(0)
                page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedInvite=text;}}})")
                link.click()
                page.wait_for_function('(url)=>window.copiedInvite===url',arg=url)
                assert page.locator('.personal-invite-social').evaluate("el=>{const r=[...el.children].map(c=>c.getBoundingClientRect());return r.length===5&&r.every(x=>Math.abs(x.top-r[0].top)<1)&&r.every(x=>x.width>0&&x.height>=44)}")
                expect(page.locator('#personal-invite-qr')).to_be_visible()
                page.wait_for_function("()=>document.querySelector('#personal-invite-qr')?.complete && document.querySelector('#personal-invite-qr')?.naturalWidth>0")
                assert page.locator('#personal-invite-qr').evaluate("img=>img.complete&&img.naturalWidth>0&&img.src.startsWith('data:image/png')")
                expect(page.get_by_role('button',name='QR',exact=True)).to_be_visible()
                expect(page.locator('.personal-invite-modal .modal-fixed-header .modal-close')).to_be_visible()
                expect(page.locator('.personal-invite-modal .modal-fixed-footer')).to_be_visible()
                # The shareable PNG keeps branding outside the matrix.
                # Compare every module outside the intentional avatar overlay, including its quiet zone.
                assert page.locator('.personal-invite-modal .invite-brand').count()==0
                pixels=page.locator('#personal-invite-qr').evaluate("""(img,rows)=>{
                    const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
                    const ctx=c.getContext('2d');ctx.drawImage(img,0,0);
                    const band=c.height-c.width,scale=c.width/rows.length;
                    const data=ctx.getImageData(0,0,c.width,c.height).data;
                    let correct=true;
                    for(let y=0;y<rows.length;y++)for(let x=0;x<rows.length;x++){
                      const i=4*((band+y*scale+Math.floor(scale/2))*c.width+x*scale+Math.floor(scale/2));
                      if(Math.hypot(x-(rows.length-1)/2,y-(rows.length-1)/2)<=5.5)continue;
                      if([[4,4],[rows.length-11,4],[4,rows.length-11]].some(([a,b])=>x>=a&&x<a+7&&y>=b&&y<b+7))continue;
                      const v=rows[y][x]==='1'?0:255;
                      if(data[i]!==v||data[i+1]!==v||data[i+2]!==v||data[i+3]!==255)correct=false;
                    }
                    return {band,correct,branded:data[0]===249&&data[1]===231&&data[2]===163};
                }""",rows)
                assert pixels=={'band':104,'correct':True,'branded':True},pixels
                import base64, io, zxingcpp
                from PIL import Image
                png=base64.b64decode(page.locator('#personal-invite-qr').get_attribute('src').split(',',1)[1])
                decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(png)))
                assert decoded and decoded.text==url, 'Branded invitation QR must decode to its exact URL'
                expect(page.locator('a[download="shursh-invite.png"]')).to_have_count(0)
                assert 'max.ru/:share?text=' in page.get_by_role('link',name='MAX',exact=True).get_attribute('href')
                assert 't.me/share/url' in page.get_by_role('link',name='Telegram',exact=True).get_attribute('href')
                assert 'vk.com/share.php' in page.get_by_role('link',name='VK',exact=True).get_attribute('href')
                # Capture actual new UI; generated fixture link is not a real hosted invitation.
                output=OUTPUT/'friend-invite';output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/f'{engine}-mobile-qr.png'),animations='disabled')
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                page.set_viewport_size({'width':320,'height':780})
                page.wait_for_function("""()=>{const el=document.querySelector('.personal-invite-social');if(!el)return false;const r=[...el.children].map(c=>c.getBoundingClientRect());return r.length===5&&r.every(x=>Math.abs(x.top-r[0].top)<1)&&r.every(x=>x.left>=0&&x.right<=innerWidth+1&&x.height>=44)}""")
                page.screenshot(path=str(output/f'{engine}-320-qr.png'),animations='disabled')
                page.set_viewport_size({'width':1440,'height':900})
                page.screenshot(path=str(output/f'{engine}-desktop-qr.png'),animations='disabled')
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                guest=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844}).new_page()
                guest.goto(url)
                expect(guest.get_by_text('Александр приглашает тебя в Шурш!',exact=True)).to_be_visible()
                expect(guest.get_by_role('button',name='Создать аккаунт',exact=True)).to_be_visible()
                browser_login(guest,'other@example.test',landing='friend_invite')
                expect(guest.get_by_role('button',name='Принять заявку',exact=True)).to_be_visible()
                guest.get_by_role('button',name='Принять заявку',exact=True).click()
                expect(guest.get_by_text('Вы уже друзья',exact=True)).to_be_visible()
                assert urlsplit(guest.url).path==urlsplit(url).path

                # Disabling search must not force the owner to navigate to
                # profile settings before deliberately sharing a new link.
                page.keyboard.press('Escape')
                expect(page.locator('.modal')).to_have_count(0)
                call(owner,'PATCH','/api/profile/me',{'discoverable':False,'allow_friend_invites':False})
                assert call(application.test_client(),'GET','/api/friend-invites/'+urlsplit(url).path.split('/')[-1]).json['relationship']=='guest'
                page.set_viewport_size({'width':390,'height':844})
                page.get_by_role('button',name='Пригласить друга').click()
                expect(page.locator('#personal-invite-link')).to_be_visible()
                new_url=page.locator('#personal-invite-link').get_attribute('data-invite-url')
                assert new_url==url
                profile=call(owner,'GET','/api/profile/me').json['profile']
                assert profile['discoverable'] is False and profile['allow_friend_invites'] is False
                assert not call(other,'GET','/api/users/search?q=%40qrowner').json['users']
                landing=call(application.test_client(),'GET','/api/friend-invites/'+urlsplit(new_url).path.split('/')[-1]).json
                assert landing['relationship']=='guest'
                expect(page.locator('#personal-invite-qr')).to_be_visible()
                page.screenshot(path=str(output/f'{engine}-hidden-profile-qr.png'),animations='disabled')
            finally:browser.close()
    finally:
        call(owner,'DELETE','/api/friend-invites/me',{})
        call(owner,'PATCH','/api/profile/me',{'name':'Owner','handle':'','last_name':'','patronymic':'','show_full_name':False,'discoverable':True,'allow_friend_invites':False})
        call(other,'PATCH','/api/profile/me',{'name':'Other','handle':''})
        with db.transaction(write=True) as con:
            con.execute('DELETE FROM friendships WHERE user_low=? AND user_high=?',(aid,bid))


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_mobile_shared_sheets_header_actions_and_swipes(browser_https,engine):
    out=OUTPUT/'mobile-interactions';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            for width,height in ((320,568),(390,844),(760,844)):
                ctx=browser.new_context(viewport={'width':width,'height':height},has_touch=True,
                    is_mobile=True,ignore_https_errors=True,reduced_motion='no-preference')
                page=ctx.new_page()
                page.goto(browser_https+'/');browser_login(page)
                page.wait_for_function("()=>ownerWarmupReady",timeout=15000)
                buttons=page.locator('.dashboard-welcome .btn-row .btn')
                boxes=[b.bounding_box() for b in buttons.all()]
                assert len(boxes)==2 and abs(boxes[0]['y']-boxes[1]['y'])<=1 and boxes[0]['x']+boxes[0]['width']<=boxes[1]['x']+1,boxes
                assert all(b['height']>=43.9 for b in boxes),boxes # subpixel tolerance, CSS min-height remains 44px
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                for selector in ('.dashboard-new-list','.santa-create-cta','header .header-bell'):
                    page.locator(selector).click()
                    dialog=page.locator('.modal')
                    expect(dialog).to_be_visible()
                    page.wait_for_function("()=>document.querySelector('.modal')?.getAnimations().length===0")
                    rect=dialog.bounding_box()
                    assert abs(rect['x'])<=1 and abs(rect['width']-width)<=1 and abs(rect['y']+rect['height']-height)<=1,rect
                    assert rect['y']>=-1,rect
                    header=dialog.locator('.modal-fixed-header')
                    close=header.locator('.modal-close')
                    expect(close).to_be_visible()
                    h,b=header.bounding_box(),close.bounding_box()
                    assert b['width']>=43.9 and b['height']>=43.9 and abs((h['y']+h['height']/2)-(b['y']+b['height']/2))<=2,(h,b)
                    assert b['x']+b['width']<=h['x']+h['width'],(h,b)
                    area=dialog.locator('.modal-scroll-area')
                    before=header.bounding_box()
                    footer=dialog.locator('.modal-fixed-footer')
                    foot_before=footer.bounding_box() if footer.count() else None
                    area.evaluate("el=>el.scrollTop=el.scrollHeight")
                    assert abs(header.bounding_box()['y']-before['y'])<=1
                    if foot_before:
                        assert abs(footer.bounding_box()['y']-foot_before['y'])<=1
                    area.evaluate("el=>el.scrollTop=0")
                    page.screenshot(path=str(out/f"{engine}-{width}-{selector.split()[-1].replace('.','')}.png"),animations='disabled')
                    page.keyboard.press('Escape')
                    expect(dialog).to_have_count(0)
                # Shared shell height increases and settles; close is not a delayed display:none.
                result=page.evaluate("""async()=>{
                  modal({title:'Размер',content:'<div id="motion-content" style="height:30px"></div>'});
                  await new Promise(r=>setTimeout(r,350));
                  const dialog=document.querySelector('.modal'),before=dialog.getBoundingClientRect().height;
                  document.querySelector('#motion-content').style.height='150px';
                  const samples=[];const start=performance.now();
                  while(performance.now()-start<400){await new Promise(requestAnimationFrame);samples.push(dialog.getBoundingClientRect().height);}
                  const after=dialog.getBoundingClientRect().height;
                  closeModal();const closing=dialog.isConnected&&dialog.closest('[data-backdrop]').inert;
                  await new Promise(r=>setTimeout(r,330));
                  return {before,after,samples,closing,removed:!dialog.isConnected};
                }""")
                assert result['after']>result['before']+50 and result['closing'] and result['removed'],result
                assert any(result['before']+2<h<result['after']-2 for h in result['samples']),result
                # Header keeps its layout and fixed document offset while collapsing.
                page.evaluate("scrollTo({top:0,behavior:'instant'})")
                page.wait_for_function("()=>!document.querySelector('.site-header').classList.contains('is-condensed') && Math.abs(document.querySelector('.site-header').getBoundingClientRect().height-132)<1")
                metrics=page.evaluate("""async()=>{
                  document.body.style.minHeight='3000px';const h=document.querySelector('.site-header'),bar=h.querySelector('.topbar');
                  const initial=h.getBoundingClientRect().height,offset=getComputedStyle(document.querySelector('#app')).paddingTop;
                  const display=getComputedStyle(bar).display;scrollTo({top:300,behavior:'instant'});
                  const frames=[],opacities=[],nav=h.querySelector('.nav'),start=performance.now();
                  while(performance.now()-start<420){await new Promise(requestAnimationFrame);frames.push(h.getBoundingClientRect().height);opacities.push(Number(getComputedStyle(nav).opacity));}
                  return {initial,frames,opacities,scrollbar:getComputedStyle(nav).scrollbarWidth,final:h.getBoundingClientRect().height,display,afterDisplay:getComputedStyle(bar).display,offset,afterOffset:getComputedStyle(document.querySelector('#app')).paddingTop,y:scrollY};
                }""")
                assert metrics['initial']>metrics['final']+30 and abs(metrics['final']-62)<2,metrics
                assert metrics['display']==metrics['afterDisplay'] and metrics['offset']==metrics['afterOffset'] and abs(metrics['y']-300)<2,metrics
                assert any(metrics['final']+2<h<metrics['initial']-2 for h in metrics['frames']),metrics
                assert any(.05<o<.95 for o in metrics['opacities']),metrics
                page.evaluate("scrollTo({top:0,behavior:'instant'})")
                page.wait_for_function("()=>!document.querySelector('.site-header').classList.contains('is-condensed') && Math.abs(document.querySelector('.site-header').getBoundingClientRect().height-132)<1")
                # Synthetic touch events use the real handler, not a direct nav call.
                def swipe(selector,dx,dy=0,x=width/2):
                    page.evaluate("""([selector,dx,dy,x])=>{
                      const target=document.querySelector(selector);if(!target)throw Error(selector);
                      const y=160,id=5;
                      const touch=(a,b)=>({identifier:id,clientX:a,clientY:b,target});
                      for(const [name,active,changed] of [['touchstart',[touch(x,y)],[touch(x,y)]],['touchmove',[touch(x+dx,y+dy)],[touch(x+dx,y+dy)]],['touchend',[],[touch(x+dx,y+dy)]]]){
                       const e=new Event(name,{bubbles:true});Object.defineProperties(e,{touches:{value:active},changedTouches:{value:changed}});target.dispatchEvent(e);
                      }
                    }""",[selector,dx,dy,x])
                if engine=='chromium':
                    # CDP delivers genuine browser touch input on the mobile context.
                    point=page.locator('.dashboard-welcome p').bounding_box()
                    x=width*.78;y=round(point['y']+point['height']/2)
                    client=ctx.new_cdp_session(page)
                    client.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
                    for i in range(1,7):
                        client.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x-i*width*.08,'y':y}]})
                    client.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                    client.detach()
                else:swipe('.dashboard-welcome p',-100)
                expect(page).to_have_url(re.compile(r'/lists$'))
                expect(page.locator('[data-wishlist-view="mine"]')).to_have_attribute('aria-selected','true')
                swipe('#wishlist-view-content',-100)
                expect(page.locator('[data-wishlist-view="friends"]')).to_have_attribute('aria-selected','true')
                swipe('#wishlist-view-content',100)
                expect(page.locator('[data-wishlist-view="mine"]')).to_have_attribute('aria-selected','true')
                swipe('main h1',-90,110)
                expect(page).to_have_url(re.compile(r'/lists$'))
                swipe('main h1',-100,0,10)
                expect(page).to_have_url(re.compile(r'/lists$'))
                swipe('main h1',-100)
                expect(page).to_have_url(re.compile(r'/santas$'))
                swipe('#santa-state-panel',-100)
                expect(page.locator('[data-santa-state="finished"]')).to_have_attribute('aria-selected','true')
                ctx.close()
        finally:browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_mobile_toast_in_sheet_flow_and_lifecycle(browser_https,engine):
    """Use the shared modal/notice functions; no network mutations or mock CSS."""
    out=OUTPUT/'mobile-toast';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            for width,height in ((320,568),(390,844),(760,844),(568,320)):
                ctx=browser.new_context(viewport={'width':width,'height':height},
                    has_touch=True,is_mobile=True,ignore_https_errors=True,reduced_motion='no-preference')
                page=ctx.new_page();page.goto(browser_https+'/')
                expect(page.locator('main h1').first).to_be_visible()
                page.evaluate("""()=>{
                  notice('Уведомление перед открытием');
                  modal({title:'Проверка',content:'<input id="toast-test-input" class="input" aria-label="Тест"><div style="height:1200px"></div>',
                         onSubmit:async()=>{throw new Error('Проверь данные')}});
                }""")
                dialog=page.locator('.modal')
                rail=dialog.locator('.modal-toast-rail')
                toast=rail.locator('.toast')
                expect(toast).to_have_text('Уведомление перед открытием')
                expect(page.locator('#toast-root .toast')).to_have_count(0)
                page.wait_for_function("()=>document.querySelector('.modal')?.getAnimations().length===0")
                def geometry():
                    return page.evaluate("""()=>{
                      const d=document.querySelector('.modal'),rail=d.querySelector('.modal-toast-rail');
                      const rect=e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,height:r.height}};
                      const footer=d.querySelector('.modal-fixed-footer'),scroller=d.querySelector('.modal-scroll-area');
                      return {sheet:rect(d),rail:rect(rail),header:rect(d.querySelector('.modal-fixed-header')),
                        body:rect(scroller),footer:rect(footer),toast:rect(rail.querySelector('.toast')),
                        scroll:scroller.scrollHeight>scroller.clientHeight,position:getComputedStyle(rail.querySelector('.toast')).position,
                        width:innerWidth,height:innerHeight};
                    }""")
                def assert_geometry(g):
                    assert g['position']=='static' and g['scroll'],g
                    assert g['header']['bottom']<=g['rail']['top']+1,g
                    assert g['rail']['bottom']<=g['body']['top']+1,g
                    assert g['body']['bottom']<=g['footer']['top']+1,g
                    assert g['footer']['bottom']<=g['height']+1,g
                    assert g['body']['height']>0 and g['rail']['height']>0,g
                    assert g['toast']['left']>=-1 and g['toast']['right']<=g['width']+1,g
                assert_geometry(geometry())
                field=dialog.locator('#toast-test-input');field.fill('Сохрани текст')
                page.evaluate("notice('Новое сообщение')")
                expect(toast).to_have_text('Новое сообщение')
                expect(field).to_be_focused();expect(field).to_have_value('Сохрани текст')
                expect(page.locator('.toast')).to_have_count(1)
                dialog.locator('.modal-fixed-footer button[type=submit]').click()
                expect(toast).to_have_text('Проверь данные')
                expect(toast).to_have_attribute('role','alert')
                expect(toast).to_have_class(re.compile(r'\berror\b'))
                page.wait_for_function("()=>document.querySelector('.modal')?.getAnimations().length===0")
                assert_geometry(geometry())
                page.screenshot(path=str(out/f'{engine}-{width}x{height}-error.png'),animations='disabled')
                page.evaluate("notice('Длинное сообщение '.repeat(45))")
                page.wait_for_function("()=>document.querySelector('.modal')?.getAnimations().length===0")
                assert_geometry(geometry())
                assert rail.evaluate("el=>el.scrollHeight>el.clientHeight")
                # Resizing to desktop restores the same node and its original timer.
                # Isolate breakpoint timing from the long-message screenshot.
                page.evaluate("notice('Перенос уведомления');window.savedToast=document.querySelector('.toast');window.toastStarted=performance.now()")
                page.set_viewport_size({'width':900,'height':844})
                page.wait_for_function("()=>!matchMedia('(max-width:760px)').matches",timeout=2000)
                expect(page.locator('#toast-root .toast')).to_have_count(1)
                assert page.evaluate("savedToast===document.querySelector('#toast-root .toast')")
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_function("()=>matchMedia('(max-width:760px)').matches",timeout=2000)
                expect(toast).to_have_count(1)
                assert page.evaluate("savedToast===document.querySelector('.modal-toast-rail .toast')")
                # Replace the sheet (and then close it); never duplicate or lose feedback.
                page.evaluate("modal({title:'Следующая модалка',content:'<p>Новое содержимое</p>'})")
                expect(toast).to_have_count(1)
                assert page.evaluate("savedToast===document.querySelector('.modal-toast-rail .toast')")
                # Moving through both breakpoints and replacing the dialog must
                # not restart the notification's original 4.5-second lifetime.
                expect(toast).to_have_count(0,timeout=5500)
                elapsed=page.evaluate("performance.now()-toastStarted")
                assert 4300<=elapsed<=5400,elapsed
                page.evaluate("notice('Готово')")
                expect(toast).to_have_text('Готово')
                page.keyboard.press('Escape');expect(dialog).to_have_count(0)
                expect(page.locator('#toast-root .toast')).to_have_text('Готово')
                expect(page.locator('.toast')).to_have_count(1)
                expect(page.locator('.toast')).to_have_count(0,timeout=6500)
                ctx.close()
        finally:browser.close()

@pytest.mark.browser
@pytest.mark.parametrize('engine', ['chromium','webkit'])
def test_landing_crayon_art_responsive_motion_and_decoding(browser_https, engine):
    """Real guest shell, approved assets, two engines and six responsive widths."""
    from app import UI_VERSION, LANDING_ART_ASSETS
    expected = {Path(asset).stem for asset in LANDING_ART_ASSETS}
    with sync_playwright() as play:
        browser = getattr(play,engine).launch(headless=True)
        try:
            for width in (320,375,390,768,1024,1440):
                context = browser.new_context(viewport={'width':width,'height':900},
                    is_mobile=width<=390, has_touch=width<=390, ignore_https_errors=True,
                    reduced_motion='no-preference')
                try:
                    page = context.new_page()
                    errors = []
                    failures = []
                    page.on('pageerror', lambda err: errors.append(str(err)))
                    page.on('requestfailed', lambda req: failures.append(req.url) if '/art/crayon/' in req.url else None)
                    page.on('response', lambda res: failures.append(res.url) if '/art/crayon/' in res.url and res.status not in (200,304) else None)
                    page.goto(browser_https+'/', wait_until='domcontentloaded')
                    expect(page.locator('.hero-copy h1')).to_contain_text('Подарки, о которых',timeout=10000)
                    # The cookie acknowledgment is independently covered by the
                    # existing cookie tests. Dismiss it for clean visual evidence.
                    notice = page.locator('.cookie-notice button')
                    expect(notice).to_be_visible()
                    notice.click()
                    expect(page.locator('.cookie-notice')).to_have_count(0)
                    page.evaluate("()=>document.fonts.ready")
                    expect(page.locator('img[data-art]')).to_have_count(12)
                    assert set(page.locator('img[data-art]').evaluate_all('(imgs)=>imgs.map(i=>i.dataset.art)')) == expected
                    # Hero layers are eagerly requested and move continuously.
                    # Do not use an actionability check on an animated element.
                    # Scroll only the static lazy illustrations; preserve native lazy loading.
                    for image in page.locator('img[data-art][loading="lazy"]').all():
                        image.evaluate("(img)=>img.scrollIntoView({block:'center',behavior:'instant'})")
                        image.evaluate("""img=>Promise.race([
                            img.decode(),new Promise((_,reject)=>setTimeout(
                                ()=>reject(Error('WebP decode timeout: '+img.dataset.art)),8000))
                        ])""")
                    page.evaluate("""()=>Promise.race([
                        Promise.all([...document.querySelectorAll('.hero-stage img')].map(img=>img.decode())),
                        new Promise((_,reject)=>setTimeout(()=>reject(Error('Hero WebP decode timeout')),8000))
                    ])""")
                    page.evaluate("scrollTo({top:0,behavior:'instant'})")
                    metrics = page.evaluate("""() => {
                      const imgs=[...document.querySelectorAll('img[data-art]')];
                      const a=imgs.map(i=>{
                        const c=document.createElement('canvas');c.width=i.naturalWidth;c.height=i.naturalHeight;
                        const ctx=c.getContext('2d');ctx.drawImage(i,0,0);
                        const pixels=ctx.getImageData(0,0,c.width,c.height).data;
                        let transparent=false,opaque=false;
                        for(let p=3;p<pixels.length;p+=4){transparent||=pixels[p]===0;opaque||=pixels[p]>240;if(transparent&&opaque)break;}
                        return {name:i.dataset.art,src:new URL(i.src).pathname,valid:i.complete&&i.naturalWidth===Number(i.getAttribute('width'))&&i.naturalHeight===Number(i.getAttribute('height')),transparent,opaque};
                      });
                      return {images:a,overflow:document.documentElement.scrollWidth-innerWidth,
                        layers:document.querySelectorAll('.hero-stage > img').length,
                        labels:document.querySelectorAll('.hero-visual > .tiny-bubble').length,
                        svgArt:document.querySelectorAll('.hero-stage svg,.step-art svg,.mock-art svg,.santa-art svg,.privacy-illustration svg').length};
                    }""")
                    # Bounding-box visibility: a heading clipped by its overflow
                    # ancestor can still pass Playwright's to_be_visible assertion.
                    showcase = page.evaluate("""() => {
                      const card=document.querySelector('.showcase');
                      const box=card.getBoundingClientRect();
                      const copy=card.querySelector('.showcase-copy').getBoundingClientRect();
                      const mock=card.querySelector('.showcase-mock').getBoundingClientRect();
                      const pieces=[...card.querySelectorAll('.showcase-copy .section-label,.showcase-copy h2,.showcase-copy p,.showcase-copy button,.showcase-mock')];
                      return {scrollTop:card.scrollTop,scrollLeft:card.scrollLeft,overflow:getComputedStyle(card).overflowY,contained:pieces.every(el=>{
                        const r=el.getBoundingClientRect();
                        return r.width>0&&r.height>0&&r.top>=box.top-1&&r.bottom<=box.bottom+1&&r.left>=box.left-1&&r.right<=box.right+1;
                      }),ordered:mock.top>=copy.bottom-1,gap:box.bottom-mock.bottom};
                    }""")
                    assert showcase['scrollTop']==0 and showcase['scrollLeft']==0 and showcase['overflow']=='clip', (engine,width,showcase)
                    assert showcase['contained'], (engine,width,showcase)
                    if width<=760:
                        assert showcase['ordered'] and 0<=showcase['gap']<=60, (engine,width,showcase)
                    # Decorative U+2733 previously rendered as a green system
                    # emoji on iOS. Geometry, not font fallback, must paint all
                    # three sites, including the large final CTA decoration.
                    ornaments = page.evaluate("""() => {
                      const selectors=[['.bubble-gift','::before'],
                        ['.marquee-inner span','::before'],['.final-cta','::after']];
                      return selectors.flatMap(([selector,pseudo])=>
                        [...document.querySelectorAll(selector)].map(el=>{
                          const s=getComputedStyle(el,pseudo);
                          const visible=el.getClientRects().length>0;
                          return {selector,visible,content:s.content,clip:s.clipPath,
                            background:s.backgroundColor,color:s.color,
                            width:parseFloat(s.width),height:parseFloat(s.height),
                            position:s.position,pointerEvents:s.pointerEvents};
                        }));
                    }""")
                    assert len(ornaments)==6, (engine,width,ornaments)
                    for mark in ornaments:
                        assert mark['content'] in ('""',"''"), (engine,width,mark)
                        assert mark['clip'].startswith('polygon('), (engine,width,mark)
                        assert mark['background']==mark['color'], (engine,width,mark)
                        assert mark['pointerEvents']=='none', (engine,width,mark)
                        if mark['visible']:
                            assert mark['width']>0 and abs(mark['width']-mark['height'])<1, (engine,width,mark)
                        if mark['selector']=='.final-cta':
                            assert mark['position']=='absolute', (engine,width,mark)
                    # The large background ornament must not intercept the CTA.
                    page.locator('.final-cta button').click(trial=True)
                    page.evaluate("scrollTo({top:0,behavior:'instant'})")
                    assert metrics['overflow']<=2, (engine,width,metrics)
                    assert metrics['layers']==4 and metrics['labels']==2 and metrics['svgArt']==0
                    for item in metrics['images']:
                        assert item['valid'] and item['transparent'] and item['opaque'], item
                        assert item['src']==f"/ui/{UI_VERSION}/art/crayon/{item['name']}.webp"
                    motion = page.evaluate("""async () => {
                      const layers=[...document.querySelectorAll('.hero-stage img')];
                      const moving=layers.filter(i=>i.matches('.float-one,.float-two,.wobble'));
                      const animations=moving.map(i=>i.getAnimations()[0]);
                      if(animations.some(a=>!a))return {moving:0,clear:false};
                      for(const a of animations)a.pause();
                      await Promise.all(animations.map(a=>a.ready));
                      const bubbles=[...document.querySelectorAll('.hero-visual .tiny-bubble')];
                      const overlaps=(a,b)=>Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.5&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.5;
                      const transforms=[];let clear=true;
                      for(const phase of [0,.25,.5,.75,1]){
                        for(const a of animations){const t=a.effect.getTiming();a.currentTime=Number(t.delay)+Number(t.duration)*phase;}
                        transforms.push(moving.map(i=>getComputedStyle(i).transform));
                        for(const i of layers)for(const b of bubbles)if(overlaps(i.getBoundingClientRect(),b.getBoundingClientRect()))clear=false;
                      }
                      const changed=moving.map((_,i)=>new Set(transforms.map(t=>t[i])).size>1);
                      for(const a of animations)a.play();
                      return {moving:moving.length,changed,clear};
                    }""")
                    assert motion['moving']==3 and all(motion['changed']) and motion['clear'], (engine,width,motion)
                    page.emulate_media(reduced_motion='reduce')
                    page.wait_for_function("()=>[...document.querySelectorAll('.hero-stage img')].every(i=>getComputedStyle(i).animationName==='none')")
                    assert not errors and not failures, (engine,width,errors,failures)
                    folder=OUTPUT/'landing-crayon'
                    folder.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(folder/f'{engine}-{width}-full.png'),full_page=True)
                    page.locator('.hero-visual').screenshot(path=str(folder/f'{engine}-{width}-hero.png'))
                    page.locator('.final-cta').screenshot(path=str(folder/f'{engine}-{width}-cta.png'))
                finally:
                    context.close()
        finally:
            browser.close()

@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_service_crayon_covers_footer_and_circular_gift_gallery(browser_https,engine):
    """Exercise the real shared renderers without any mutation of hosted data."""
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            for width in (320,390,1280):
                ctx=browser.new_context(viewport={'width':width,'height':844},has_touch=width<760,
                    is_mobile=width<760,ignore_https_errors=True,reduced_motion='reduce')
                page=ctx.new_page()
                try:
                    page.goto(browser_https+'/')
                    expect(page.locator('main h1').first).to_be_visible()
                    data=page.evaluate("""()=>{
                      const lists=Array.from({length:150},(_,i)=>1+i*10).map(id=>({id,title:'Список '+id,theme:'mint',occasion:'Просто так',wish_count:0}));
                      const map=assignWishlistCovers(lists);
                      const again=assignWishlistCovers([...lists].reverse());
                      const node=document.createElement('div');
                      node.innerHTML=lists.map(l=>listCard(l,map)).join('');
                      const slots=[...node.querySelectorAll('[data-cover-variant]')].map(x=>x.dataset.coverVariant);
                      const srcs=[...node.querySelectorAll('.wishlist-cover-art')].map(x=>[...x.querySelectorAll('img')].map(i=>i.getAttribute('src')).join('|'));
                      const f=document.querySelector('.footer'),c=f.querySelector('.footer-credit');
                      const fr=f.getBoundingClientRect(),cr=c.getBoundingClientRect();
                      return {unique:new Set(slots).size,art:new Set(srcs).size,stable:lists.every(l=>map.get(wishlistCoverKey(l))===again.get(wishlistCoverKey(l))),
                        right:Math.abs(fr.right-cr.right),align:getComputedStyle(c).textAlign};
                    }""")
                    assert data['unique']==150 and data['art']==150 and data['stable'],data
                    themed=page.evaluate("""async()=>{
                      // Independent semantic allowlist: do not derive the oracle
                      // from the implementation's own pools.
                      const allowed={
                        'День рождения':['step-gift','hero-gift'],
                        'Годовщина':['privacy','step-share','hero-mail'],
                        'Новоселье':['cup','step-gift','hero-gift'],
                        'Свадьба':['step-share','privacy','hero-mail','hero-gift'],
                        'Новый год':['santa','hero-gift','step-gift'],
                        'Просто так':['camera','ticket','cup','step-list','step-gift','hero-gift','step-share','hero-mail','hero-mascot','privacy'],
                        'Другое':['step-share','camera','hero-mascot','hero-mail','cup','ticket','step-list','step-gift','hero-gift','privacy']
                      };
                      const primary={'Новый год':['santa'],'Новоселье':['cup'],'Свадьба':['step-share','privacy','hero-mail']};
                      const occasions=Object.keys(allowed);
                      const lists=occasions.flatMap((occasion,i)=>Array.from({length:20},(_,j)=>({id:2000+i*100+j,occasion})));
                      const map=assignWishlistCovers(lists);
                      const again=assignWishlistCovers([...lists].reverse());
                      const node=document.createElement('div');
                      node.innerHTML=lists.map(l=>wishlistCover(l,map)).join('');
                      const cards=[...node.children];
                      const names=cards.map(c=>[...c.querySelectorAll('img')].map(img=>img.dataset.serviceArt));
                      const variants=names.map(a=>a.join('|'));
                      const images=[...new Map([...node.querySelectorAll('img')].map(i=>[i.src,i])).values()];
                      await Promise.all(images.map(i=>{i.loading='eager';return i.decode()}));
                      const fallback=['','Unknown','__proto__','constructor',null].every(occasion=>
                        wishlistCoverParts({occasion},50).every(name=>allowed['Другое'].includes(name)));
                      return {pools:occasions.length,unique:new Set(variants).size,stable:lists.every(l=>map.get(wishlistCoverKey(l))===again.get(wishlistCoverKey(l))),
                        thematic:lists.every((l,i)=>names[i].every(name=>allowed[l.occasion].includes(name))&&(primary[l.occasion]||allowed[l.occasion]).includes(names[i][0])),
                        fallback,trimmed:wishlistCoverParts({occasion:' День рождения '},0)[0]==='step-gift',
                        decoded:images.every(i=>i.naturalWidth>0&&i.naturalHeight>0)};
                    }""")
                    assert themed=={'pools':7,'unique':140,'stable':True,'thematic':True,'fallback':True,'trimmed':True,'decoded':True},themed
                    order=page.evaluate("""async()=>{
                      const l={id:98765,occasion:'День рождения'},slot=2;
                      const host=document.createElement('div');host.className='list-cover';
                      host.style.cssText='position:fixed;left:0;top:0;width:280px;height:150px;visibility:hidden';
                      host.innerHTML=wishlistCover(l,new Map([[wishlistCoverKey(l),slot]]));
                      document.body.append(host);
                      try{
                        const art=host.firstElementChild,big=art.firstElementChild,small=art.querySelector('.cover-companions img');
                        if(!small)return false;
                        const a=big.getBoundingClientRect(),b=small.getBoundingClientRect();
                        return art.classList.contains('wishlist-cover-gifts-reversed')&&a.width>b.width&&a.left+a.width/2>b.left+b.width/2;
                      }finally{host.remove();}
                    }""")
                    assert order
                    assert data['right']<=2 and data['align']=='right',data
                    page.evaluate("contactDeveloperModal()")
                    expect(page.locator('.modal')).not_to_contain_text('кабинет')
                    expect(page.locator('.modal-fixed-header .modal-close')).to_be_visible()
                    expect(page.locator('.modal-fixed-footer [type=submit]')).to_be_visible()
                    page.keyboard.press('Escape')
                    expect(page.locator('.modal')).to_have_count(0)
                    page.evaluate("loginModal()")
                    expect(page.locator('[name=remember]')).to_be_checked()
                    page.locator('label.shursh-checkbox').filter(has=page.locator('[name=remember]')).click()
                    expect(page.locator('[name=remember]')).not_to_be_checked()
                    page.keyboard.press('Escape')
                    expect(page.locator('.modal')).to_have_count(0)
                    page.evaluate("loginModal()")
                    expect(page.locator('[name=remember]')).to_be_checked()
                    page.keyboard.press('Escape')
                    expect(page.locator('.modal')).to_have_count(0)
                    page.evaluate("modal({title:'Дата обмена',content:field('Дата обмена','exchange_date','','date','2027-02-12',true)})")
                    expect(page.locator('input[type=date]')).to_have_attribute('aria-hidden','true')
                    page.locator('.ui-calendar-trigger').click()
                    expect(page.locator('.ui-calendar-popover')).to_be_visible()
                    assert page.locator('.ui-calendar-popover').evaluate("el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1}")
                    page.locator('.ui-calendar-popover [data-date="2027-02-15"]').click()
                    expect(page.locator('input[type=date]')).to_have_value('2027-02-15')
                    expect(page.locator('.ui-calendar-popover')).to_have_count(0)
                    page.keyboard.press('Escape')
                    expect(page.locator('.modal')).to_have_count(0)
                    # Load the real versioned WebP resources via the shared service
                    # renderer and verify decoding, rather than only inspecting URLs.
                    decoded=page.evaluate("""async()=>{
                      const names=['step-gift','camera','cup','ticket','step-list','step-share','hero-gift','hero-mail','hero-mascot','privacy','santa'];
                      return await Promise.all(names.map(async name=>{
                        const holder=document.createElement('div');
                        holder.innerHTML=serviceArt(name);
                        const img=holder.firstElementChild;
                        img.loading='eager';
                        await img.decode();
                        return img.naturalWidth>0&&img.naturalHeight>0;
                      }));
                    }""")
                    assert len(decoded)==11 and all(decoded)
                    page.evaluate("""()=>{
                      activeGameContext={own:[{id:1,title:'Первый',description:'Первое описание'},
                        {id:2,title:'Второй',description:'Длинное описание '.repeat(150),image_data:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="400"><rect width="80" height="400" fill="purple"/></svg>')},{id:3,title:'Третий'}],
                        recipient:[{id:4,title:'Только получатель'},{id:5,title:'Другой подарок'}]};
                      showGameWishDetails({dataset:{source:'own',id:'1'}});
                    }""")
                    dialog=page.locator('.gift-details-modal')
                    expect(dialog).to_have_attribute('aria-label','Первый')
                    expect(dialog.locator('.gift-gallery-peek')).to_have_count(2)
                    expect(dialog.locator('.gift-gallery-count')).to_have_text('1 / 3')
                    expect(dialog.locator('.gift-gallery-prev')).to_have_attribute('aria-label','Предыдущий подарок: Третий')
                    expect(dialog.locator('.gift-gallery-next')).to_have_attribute('aria-label','Следующий подарок: Второй')
                    geometry=dialog.locator('.gift-gallery').evaluate("""el=>{
                      const a=el.querySelector('.gift-gallery-prev').getBoundingClientRect(),
                        b=el.querySelector('.gift-dialog-media').getBoundingClientRect(),
                        c=el.querySelector('.gift-gallery-next').getBoundingClientRect();
                      const left=el.querySelector('.gift-gallery-prev .gift-gallery-preview-art').getBoundingClientRect(),
                        right=el.querySelector('.gift-gallery-next .gift-gallery-preview-art').getBoundingClientRect();
                      return {ordered:a.right<=b.left+1&&b.right<=c.left+1,peeks:a.width>=44&&c.width>=44,
                        sameSize:Math.abs(left.width-b.width)<=1&&Math.abs(right.width-b.width)<=1&&Math.abs(left.height-b.height)<=1&&Math.abs(right.height-b.height)<=1,
                        overlap:left.right>b.left&&right.left<b.right,
                        hit:[a,b,c].every((r,i)=>document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.closest(['.gift-gallery-prev','.gift-dialog-media','.gift-gallery-next'][i])),
                        dark:getComputedStyle(el.querySelector('.gift-gallery-preview-art')).filter,
                        overflow:el.scrollWidth-el.clientWidth};
                    }""")
                    assert geometry['ordered'] and geometry['peeks'] and geometry['sameSize'] and geometry['overlap'] and geometry['hit'] and geometry['dark']=='none' and geometry['overflow']<=2,geometry
                    def deck_size():
                        return dialog.evaluate("""el=>[el.offsetWidth,el.offsetHeight,el.querySelector('.gift-dialog-media').offsetWidth,el.querySelector('.gift-dialog-media').offsetHeight]""")
                    initial_size=deck_size()
                    dialog.locator('.gift-gallery-prev').click()
                    expect(dialog).to_have_attribute('aria-label','Третий')
                    dialog.locator('.gift-gallery-next').click()
                    expect(dialog).to_have_attribute('aria-label','Первый')
                    page.keyboard.press('ArrowRight')
                    expect(dialog).to_have_attribute('aria-label','Второй')
                    assert deck_size()==initial_size
                    page.evaluate("""()=>{
                      const target=document.querySelector('.gift-gallery .gift-dialog-media');
                      const t=(x)=>({identifier:1,clientX:x,clientY:150,target});
                      for(const [name,active,changed] of [['touchstart',[t(150)],[t(150)]],['touchend',[],[t(60)]]]){
                        const e=new Event(name,{bubbles:true});Object.defineProperties(e,{touches:{value:active},changedTouches:{value:changed}});target.dispatchEvent(e);
                      }
                    }""")
                    expect(dialog).to_have_attribute('aria-label','Третий')
                    expect(dialog.locator('.gift-dialog-edit')).to_have_attribute('data-id','3')
                    assert deck_size()==initial_size
                    if width>=760:
                        media=dialog.locator('.gift-dialog-media').bounding_box()
                        x=media['x']+media['width']/2;y=media['y']+media['height']/2
                        page.mouse.move(x+50,y);page.mouse.down();page.mouse.move(x-55,y,steps=8);page.mouse.up()
                        expect(dialog).to_have_attribute('aria-label','Первый')
                        assert deck_size()==initial_size
                        page.keyboard.press('ArrowLeft')
                        expect(dialog).to_have_attribute('aria-label','Третий')
                    dialog.locator('.gift-dialog-edit').focus()
                    page.keyboard.press('ArrowRight')
                    expect(dialog).to_have_attribute('aria-label','Первый')
                    expect(dialog).to_be_focused()
                    page.keyboard.press('ArrowLeft')
                    expect(dialog).to_have_attribute('aria-label','Третий')
                    for image in dialog.locator('img').all():
                        image.evaluate("(img)=>{img.loading='eager';return img.decode()}")
                    folder=OUTPUT/'service-crayon-gallery';folder.mkdir(parents=True,exist_ok=True)
                    dialog.screenshot(path=str(folder/f'{engine}-{width}-gallery.png'))
                    page.keyboard.press('Escape');expect(dialog).to_have_count(0)
                    page.evaluate("showGameWishDetails({dataset:{source:'recipient',id:'4'}})")
                    expect(dialog).to_have_attribute('aria-label','Только получатель')
                    expect(dialog.locator('.gift-dialog-edit')).to_have_count(0)
                    dialog.locator('.gift-gallery-prev').click()
                    expect(dialog).to_have_attribute('aria-label','Другой подарок')
                    expect(dialog.locator('.gift-gallery-count')).to_have_text('2 / 2')
                    page.keyboard.press('Escape');expect(dialog).to_have_count(0)
                    page.evaluate("activeGameContext.own=[{id:1,title:'Один'}];showGameWishDetails({dataset:{source:'own',id:'1'}})")
                    expect(dialog.locator('.gift-gallery')).to_have_count(0)
                    expect(dialog.locator('.gift-dialog-fallback img.service-art')).to_be_visible()
                finally:ctx.close()
        finally:browser.close()


@pytest.mark.browser
def test_mobile_cookie_notice_never_overlays_owner_tabs(browser_https):
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as play:
        for engine in ("chromium", "webkit"):
            browser = getattr(play, engine).launch(headless=True)
            try:
                for width in (320, 390, 760):
                    context = browser.new_context(viewport={"width":width,"height":640},
                        ignore_https_errors=True, reduced_motion="reduce", has_touch=True)
                    try:
                        page = context.new_page()
                        page.goto(browser_https + "/", wait_until="domcontentloaded")
                        notice = page.locator(".cookie-notice")
                        expect(notice).to_be_visible()
                        browser_login(page)
                        expect(page.locator(".dashboard-page")).to_be_visible()
                        for path, heading, selector in ROUTES:
                            page.evaluate("(path)=>nav(path)", path)
                            expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                            expect(page.locator("#page-view")).not_to_have_attribute("aria-busy","true")
                            expect(notice).to_have_count(1)
                            assert notice.evaluate("""el=>{
                                const r=el.getBoundingClientRect();
                                const v=document.querySelector('#page-view').getBoundingClientRect();
                                return getComputedStyle(el).position==='relative' && r.bottom<=v.top+1;
                            }"""),(engine,width,path)
                        notice.locator("button").click()
                        expect(notice).to_have_count(0)
                        page.reload(wait_until="domcontentloaded")
                        expect(page.locator("#page-view main h1").first).to_be_visible()
                        expect(notice).to_have_count(0)
                    finally:
                        context.close()
            finally:
                browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_cookie_notice_nested_routes_dialogs_and_keyboard_viewport(browser_https, application, engine):
    """Keep consent unacknowledged; test real renderers and pointer hit targets.
    Viewport resize models available keyboard space, not a native OS keyboard.
    """
    from test_cloud import login, call, make_list, IDS
    from uuid import uuid4

    owner = login(application)
    lid, wid, key = make_list(owner)
    eid = call(owner, 'POST', '/api/santas',
               {'title': 'Cookie audit ' + uuid4().hex[:8]}, 201).json['id']
    invite = call(owner, 'GET', f'/api/santas/{eid}').json['event']['invite_key']
    out = OUTPUT / 'cookie-interactions'
    out.mkdir(parents=True, exist_ok=True)
    report = []

    def hit(locator):
        locator.scroll_into_view_if_needed()
        result = locator.evaluate("""el => {
          const r=el.getBoundingClientRect(), x=r.left+r.width/2, y=r.top+r.height/2;
          const target=document.elementFromPoint(x,y);
          return {hit:!!target&&(target===el||el.contains(target)),
                  cookie:!!target?.closest('.cookie-notice'),
                  inViewport:x>=0&&x<innerWidth&&y>=0&&y<innerHeight};
        }""")
        assert result['inViewport'] and result['hit'] and not result['cookie'], result
        locator.click(trial=True)

    def page_gate(page):
        notice = page.locator('.cookie-notice')
        expect(notice).to_have_count(1)
        assert notice.evaluate("""el => {
          const view=document.querySelector('#page-view');
          return getComputedStyle(el).position==='relative' &&
            el.getBoundingClientRect().bottom<=view.getBoundingClientRect().top+1;
        }""")
        assert page.evaluate("localStorage.getItem('shursh-cookie-notice-v1')!=='yes'")

    def dialog_gate(page, label, width, height):
        dialog = page.locator('.modal')
        expect(dialog).to_be_visible()
        expect(page.locator('.cookie-notice')).to_have_count(1)
        page.wait_for_function("()=>document.querySelector('.modal')?.getAnimations().length===0")
        close = dialog.locator('.modal-close').first
        hit(close)
        fields = dialog.locator('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=date]):not([readonly]):not([disabled]):visible, textarea:not([readonly]):not([disabled]):visible')
        editable = bool(fields.count())
        if editable:
            field = fields.first
            hit(field)
            field.click()
            expect(field).to_be_focused()
            value = field.input_value()
            page.set_viewport_size({'width':width,'height':max(320, height-300)})
            expect(field).to_be_focused()
            expect(field).to_have_value(value)
            hit(field)
            expect(field).to_be_focused()
            hit(close)
            footer = dialog.locator('.modal-fixed-footer button:not([disabled]):visible')
            if footer.count():
                hit(footer.last)
            page.screenshot(path=str(out/f'{engine}-{width}-{label}-reduced.png'), animations='disabled')
            page.set_viewport_size({'width':width,'height':height})
            expect(field).to_be_focused()
            expect(field).to_have_value(value)
        else:
            page.set_viewport_size({'width':width,'height':max(320,height-300)})
            hit(close)
            page.set_viewport_size({'width':width,'height':height})
        hit(close)
        close.click()
        expect(dialog).to_have_count(0)
        page_gate(page)
        report.append({'width':width,'dialog':label,'editable':editable})

    with sync_playwright() as play:
        browser = getattr(play,engine).launch(headless=True)
        try:
            for width,height in ((320,640),(390,844),(760,844)):
                context = browser.new_context(viewport={'width':width,'height':height},
                    has_touch=True,is_mobile=True,ignore_https_errors=True,reduced_motion='reduce')
                try:
                    page = context.new_page()
                    page.goto(browser_https+'/',wait_until='domcontentloaded')
                    expect(page.locator('main h1').first).to_be_visible()
                    page_gate(page)
                    for label, opener in (
                        ('login', "loginModal()"),
                        ('register', "loginModal('register')"),
                        ('confirmation', "confirmationModal('fixture@example.test')"),
                        ('feedback-guest', "contactDeveloperModal()"),
                    ):
                        page.evaluate(opener)
                        dialog_gate(page,label,width,height)
                    browser_login(page)
                    expect(page.locator('.dashboard-page')).to_be_visible()
                    for path,label in ((f'/list/{lid}','list'),(f'/santa/{eid}','santa'),
                                       (f'/w/{key}','shared-list'),(f'/join/{invite}','invite'),
                                       (f"/users/{IDS['other@example.test']}",'profile')):
                        page.evaluate("(path)=>nav(path)",path)
                        expect(page).to_have_url(re.compile(re.escape(path)+r'$'))
                        expect(page.locator('#page-view main h1').first).to_be_visible()
                        expect(page.locator('#page-view')).not_to_have_attribute('aria-busy','true')
                        page_gate(page)
                        page.screenshot(path=str(out/f'{engine}-{width}-{label}.png'),animations='disabled')
                        if label=='list':
                            page.evaluate("wishModal()")
                            dialog_gate(page,'wish',width,height)
                        if label=='santa':
                            page.evaluate("addPlayerModal()")
                            dialog_gate(page,'santa-personal-invite',width,height)
                    page.evaluate("nav('/profile')")
                    expect(page.locator('main h1').first).to_contain_text('Мой профиль')
                    for label, opener in (
                        ('profile-edit','socialEditProfileModal()'),
                        ('avatar','socialEditAvatarModal()'),
                        ('email',"socialAccountModal('email')"),
                        ('password',"socialAccountModal('password')"),
                        ('wishlist','listModal()'),
                        ('santa-create','santaModal()'),
                        ('connect-game','connectGameModal()'),
                        ('notifications','socialNotificationsModal()'),
                        ('confirm',"confirmAction('Проверка','Тест',async()=>{})"),
                        ('feedback','contactDeveloperModal()'),
                    ):
                        page.evaluate(opener)
                        dialog_gate(page,label,width,height)
                    page.evaluate("nav('/friends')")
                    expect(page.locator('main h1').first).to_contain_text('Друзья')
                    search=page.locator('#social-search-form input[name=q]')
                    hit(search)
                    search.click()
                    expect(search).to_be_focused()
                    page.set_viewport_size({'width':width,'height':max(320,height-300)})
                    hit(search)
                    expect(search).to_be_focused()
                    page.set_viewport_size({'width':width,'height':height})
                    page.evaluate("socialPersonalInviteModal()")
                    dialog_gate(page,'friend-qr',width,height)
                    notice=page.locator('.cookie-notice')
                    notice.locator('button').click()
                    expect(notice).to_have_count(0)
                    page.reload(wait_until='domcontentloaded')
                    expect(page.locator('main h1').first).to_be_visible()
                    expect(notice).to_have_count(0)
                finally:
                    context.close()
        finally:
            browser.close()
    (out/f'{engine}-metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_admin_device_presence_color_and_refresh(browser_https, application, monkeypatch, engine):
    """Presence is an advisory visible-tab heartbeat; admin refresh keeps focus."""
    from test_cloud import login, call, IDS
    from cloud import db

    monkeypatch.setenv('SHURSH_ADMIN_EMAILS', 'owner@example.test')
    member=login(application,'other@example.test')
    uid=str(IDS['other@example.test'])
    with db.transaction(write=True) as con:
        con.execute("UPDATE admin_user_activity SET last_seen_at=now()-interval '10 minutes',last_platform='windows' WHERE user_id=?",(uid,))
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            context=browser.new_context(viewport={'width':390,'height':844},ignore_https_errors=True,reduced_motion='reduce')
            page=context.new_page()
            page.goto(browser_https+'/')
            browser_login(page)
            page.evaluate("nav('/admin/users')")
            expect(page.locator('main h1')).to_have_text('Пользователи')
            cell=page.locator('[data-admin-visit-user="'+uid+'"]')
            icon=cell.locator('.admin-device-presence')
            expect(icon).to_be_visible()
            expect(icon).not_to_have_class(re.compile(r'\bis-online\b'))
            search=page.locator('#admin-users-query')
            search.focus()
            page.evaluate("window.presenceSearch=document.querySelector('#admin-users-query');window.presenceTable=document.querySelector('.admin-users-table')")
            call(member,'GET','/api/notifications/unread',headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0)','X-Shursh-Visit':'1'})
            page.evaluate("socialRefreshAdminPresence()")
            expect(icon).to_have_class(re.compile(r'\bis-online\b'))
            expect(icon).to_have_css('color','rgb(22, 163, 74)')
            expect(icon).to_have_attribute('title',re.compile('В сети'))
            expect(search).to_be_focused()
            assert page.locator('.admin-users-table th').all_text_contents()[4:7]==['Вишлисты','Подарки','Рефы']
            expect(page.locator('.admin-users-table [data-admin-count="gifts"]').first).to_be_visible()
            expect(page.locator('.admin-users-table [data-admin-count="referrals"]').first).to_be_visible()
            assert page.evaluate("presenceSearch===document.querySelector('#admin-users-query')&&presenceTable===document.querySelector('.admin-users-table')")
            boundaries=page.evaluate("""()=>{
                const now=Date.now(),stamp=delta=>new Date(now-delta).toISOString();
                return [0,299999,300000,300001,-1].map(delta=>socialAdminPresenceOnline({last_seen_at:stamp(delta),last_seen_source:'visit'},now))
                  .concat(socialAdminPresenceOnline({last_seen_at:stamp(0),last_seen_source:'session'},now));
            }""")
            assert boundaries==[True,True,False,False,False,False]
            with db.transaction(write=True) as con:
                con.execute("UPDATE admin_user_activity SET last_seen_at=now()-interval '10 minutes' WHERE user_id=?",(uid,))
            page.evaluate("socialRefreshAdminPresence()")
            expect(icon).not_to_have_class(re.compile(r'\bis-online\b'))
            expect(search).to_be_focused()
            row=cell.locator('xpath=..')
            row.locator('[data-admin-count="gifts"]').click()
            expect(page.get_by_role('dialog',name='Подарки')).to_be_visible()
            expect(page.locator('.modal-fixed-header')).to_be_visible()
            expect(page.locator('.modal-fixed-footer')).to_be_visible()
            page.keyboard.press('Escape')
            row.locator('[data-admin-count="discoverable"]').click()
            expect(page.locator('#fld-current_password')).to_be_visible()
            page.keyboard.press('Escape')
            page.goto(browser_https+'/admin/audit')
            expect(page.locator('main h1')).to_have_text('Журнал событий')
            page.get_by_role('tab',name='Пользователи').click()
            expect(page.get_by_role('tab',name='Пользователи')).to_have_attribute('aria-selected','true')
            page.get_by_role('tab',name='Админы').click()
            page.locator('.admin-audit-row').first.click()
            expect(page.get_by_role('dialog',name='Подробности события')).to_be_visible()
            output=OUTPUT/'admin-audit';output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/f'{engine}-details.png'),animations='disabled')
            context.close()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_hotfix_admin_direct_reload_and_error_report(browser_https,application,monkeypatch,engine):
    import time
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':844},reduced_motion='reduce')
            page=ctx.new_page()
            page.goto(browser_https+'/')
            browser_login(page)
            page.route('**/social-ui.js',lambda route:(time.sleep(.7),route.continue_()))
            page.goto(browser_https+'/admin/users',wait_until='domcontentloaded')
            expect(page.locator('main h1')).to_have_text('Пользователи')
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('main h1')).to_have_text('Пользователи')
            page.evaluate("errorView(new ReferenceError('socialAdminUsersPage is not defined'))")
            expect(page.locator('.error-approved-art img')).to_be_visible()
            expect(page.locator('.error-page h1')).to_have_text('Не удалось загрузить интерфейс')
            expect(page.locator('.error-page > p:not([data-incident-result])')).to_have_count(0)
            expect(page.locator('.error-page')).not_to_contain_text('is not defined')
            btn=page.locator('[data-action="report-incident"]')
            expect(btn).to_have_text('Сообщить об ошибке')
            with page.expect_response(lambda r:r.url.endswith('/api/incidents')) as response:
                btn.click()
            assert response.value.status in (200,201)
            expect(btn).to_be_disabled()
            expect(btn).to_have_text('Сообщение отправлено')
            expect(page.locator('[data-incident-result]')).to_contain_text('получила сообщение')
            output=OUTPUT/'hotfix';output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/f'{engine}-error-report.png'))
            page.evaluate("nav('/profile')")
            expect(page.get_by_role('heading',name='Мой профиль',exact=True)).to_be_visible()
            page.get_by_role('button',name='Редактировать профиль').click()
            modal=page.locator('.profile-edit-modal')
            expect(modal).to_be_visible()
            assert modal.evaluate("el=>el.offsetWidth>=760")
            assert modal.locator('#modal-form').evaluate("el=>getComputedStyle(el).gridTemplateColumns.split(' ').length===2")
            modal.screenshot(path=str(output/f'{engine}-profile-edit.png'))
            page.keyboard.press('Escape')
            assert page.evaluate("new Set([1,2,3,4].map(santaCardArt)).size===4&&santaCardArt(3)===santaCardArt(3)")
            ctx.close()
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_photo_fallback_and_adaptive_santa_layout(browser_https,engine):
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1440,'height':900},ignore_https_errors=True,reduced_motion='reduce')
            page.goto(browser_https+'/')
            expect(page.locator('main h1').first).to_be_visible()
            fallback=page.evaluate("""async()=>{
                const source=document.createElement('canvas');source.width=64;source.height=48;
                source.getContext('2d').fillRect(0,0,64,48);
                const blob=await new Promise(r=>source.toBlob(r,'image/png'));
                const native=HTMLCanvasElement.prototype.toDataURL,bitmap=window.createImageBitmap;
                window.createImageBitmap=()=>Promise.reject(new Error('unavailable'));
                HTMLCanvasElement.prototype.toDataURL=function(type,q){return native.call(this,type==='image/webp'?'image/png':type,q);};
                try{return (await compressToWebp(new File([blob],'photo.png',{type:'image/png'}))).startsWith('data:image/jpeg;base64,');}
                finally{HTMLCanvasElement.prototype.toDataURL=native;window.createImageBitmap=bitmap;}
            }""")
            assert fallback
            page.evaluate("""()=>{modal({title:'Фото',content:'<div class="file-picker"><input type="file" name="image"></div>'});}""")
            expect(page.locator('.localized-file-button')).to_have_text('Выбери файл')
            page.keyboard.press('Escape')
            page.evaluate("""()=>{const main=document.querySelector('main');main.innerHTML='<div class="santa-detail-layout" style="width:100%"><div><div class="panel" style="height:120px">Левый</div></div><div><div class="panel" style="height:620px">Правый</div></div></div><section class="panel" id="game-chat"><input value="черновик"></section>';setupSantaChatLayout();}""")
            expect(page.locator('.santa-detail-layout>div:first-child>#game-chat')).to_have_count(1)
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('.santa-detail-layout + #game-chat')).to_have_count(1)
            expect(page.locator('#game-chat input')).to_have_value('черновик')
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_profile_feedback_and_inline_santa_polish(browser_https,application,engine):
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            page=browser.new_page(ignore_https_errors=True,viewport={'width':390,'height':844})
            page.goto(browser_https+'/')
            browser_login(page)
            page.evaluate("contactDeveloperModal()")
            expect(page.locator('[name=reply_email]')).to_be_checked()
            page.locator('label.shursh-checkbox').filter(has=page.locator('[name=reply_email]')).click()
            expect(page.locator('#fld-email')).to_be_hidden()
            expect(page.locator('#fld-email')).to_be_disabled()
            page.locator('label.shursh-checkbox').filter(has=page.locator('[name=reply_email]')).click()
            expect(page.locator('#fld-email')).to_be_visible()
            expect(page.locator('#fld-email')).to_be_enabled()
            expect(page.locator('[name=notify_site]')).to_be_visible()
            assert page.locator('[name=topic] option[value=thanks]').count()==1
            page.keyboard.press('Escape')
            page.evaluate("socialEditProfileModal()")
            expect(page.locator('[name=show_last_name]')).to_be_visible()
            expect(page.locator('[name=show_patronymic]')).to_be_visible()
            expect(page.locator('[name=show_full_name]')).to_have_count(0)
            page.keyboard.press('Escape')
            page.evaluate("listModal()")
            expect(page.locator('#wishlist-cover-file')).to_have_count(1)
            page.keyboard.press('Escape')
            page.evaluate("""()=>{const root=document.querySelector('main');root.innerHTML='<div class="santa-date-inline"><input type="date" data-santa-date-input value="2027-02-12"></div>';enhanceCalendars(root);}""")
            page.locator('.santa-date-inline .ui-calendar-trigger').click()
            expect(page.locator('.ui-calendar-popover')).to_be_visible()
            expect(page.locator('.modal-backdrop')).to_have_count(0)
            page.locator('.ui-calendar-toolbar [data-shift="1"]').click()
            expect(page.locator('.ui-calendar-day[data-date="2027-03-13"]')).to_be_visible()
            page.locator('.ui-calendar-toolbar [data-shift="-1"]').click()
            page.locator('.ui-calendar-day[data-date="2027-02-13"]').click()
            expect(page.locator('[data-santa-date-input]')).to_have_value('2027-02-13')
        finally:
            browser.close()


@pytest.mark.browser
@pytest.mark.parametrize('engine',['chromium','webkit'])
def test_branded_document_404_and_diagnostic(browser_https,application,monkeypatch,engine):
    from test_cloud import login,call
    monkeypatch.setenv('SHURSH_ADMIN_EMAILS','owner@example.test')
    manager=login(application)
    paths={'/missing-page':'Страница не найдена','/santa/invalid':'Игра не найдена','/list/invalid':'Вишлист не найден','/u/!':'Пользователь не найден','/users/invalid':'Пользователь не найден','/join/!':'Приглашение не найдено','/i/!':'Приглашение не найдено','/p/!':'Личная ссылка недействительна','/r/!':'Бронь не найдена','/w/!':'Вишлист не найден','/uploads/no-such-image.webp':'Изображение не найдено'}
    out=OUTPUT/'document-404';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as play:
        browser=getattr(play,engine).launch(headless=True)
        try:
            for enabled in (False,True):
                ctx=browser.new_context(ignore_https_errors=True,java_script_enabled=enabled,viewport={'width':320,'height':780},reduced_motion='reduce')
                try:
                    page=ctx.new_page()
                    for index,(path,heading) in enumerate(paths.items()):
                        response=page.goto(browser_https+path+'?hidden=DO-NOT-REFLECT')
                        assert response.status==404
                        assert 'text/html' in response.headers['content-type']
                        expect(page.locator('h1')).to_have_text(heading)
                        expect(page.locator('.error-approved-art img')).to_be_visible()
                        expect(page.locator('.error-page a[href="/"]')).to_be_visible()
                        assert 'DO-NOT-REFLECT' not in page.content()
                        assert page.locator('h1').count()==1
                        if enabled:
                            page.wait_for_function("document.querySelector('.error-approved-art img').naturalWidth>0")
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                            expect(page.locator('[data-report-404]')).to_be_visible()
                        else:
                            expect(page.locator('[data-report-404]')).to_be_hidden()
                        if index in (0,1,2,5):
                            page.screenshot(path=str(out/f'{engine}-320-{enabled}-{index}.png'),animations='disabled')
                    if enabled:
                        page.set_viewport_size({'width':1440,'height':900})
                        page.goto(browser_https+'/santa/invalid')
                        with page.expect_response(lambda r:r.url.endswith('/api/incidents')) as sent:
                            page.locator('[data-report-404]').click()
                        assert sent.value.status in (200,201)
                        expect(page.locator('[data-report-404]')).to_be_disabled()
                        expect(page.locator('[data-report-status]')).to_contain_text('получила сообщение')
                        page.screenshot(path=str(out/f'{engine}-desktop-reported.png'),animations='disabled')
                        page.locator('.error-page a[href="/"]').click()
                        expect(page.locator('main h1').first).to_be_visible()
                finally:
                    ctx.close()
        finally:
            browser.close()
    items=call(manager,'GET','/api/admin/feedback').json['items']
    assert any('HTTP: 404' in item['message'] and '/santa/*' in item['message'] and 'Версия UI:' in item['message'] and not item['reply_email'] and not item['notify_site'] for item in items)
