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
    ("/lists", "Твои вишлисты", 'header .nav [data-nav="/lists"]'),
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
            assert box is not None and box["y"] >= 11 and box["y"]+box["height"] <= 800, box
            assert box["x"] >= 10 and box["x"]+box["width"] <= 365, box
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
                browser_login(page)
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
                # Long profile modal on mobile: centered with safe viewport margins.
                page.locator('header .nav [data-nav="/profile"]').click()
                page.locator('[data-social-action="edit-profile"]').click()
                expect(page.locator(".modal")).to_be_visible()
                bbox=page.locator(".modal").bounding_box()
                assert bbox and bbox["y"]>=11 and bbox["y"]+bbox["height"]<=832,bbox
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
            page=browser.new_page(viewport={'width':390,'height':844},reduced_motion='reduce')
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
            page.locator('.modal-fixed-footer [type="submit"]').click()
            expect(page.locator('.santa-game-status')).to_contain_text('Игра завершена')
            expect(page.locator('[data-action="finish-santa"]')).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            assert page.evaluate("""async id => {
                const response=await fetch('/api/santas/'+id);
                return response.ok&&(await response.json()).event.status==='finished';
            }""",id)
        finally:
            browser.close()
