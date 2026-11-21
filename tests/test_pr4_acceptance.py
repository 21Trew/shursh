"""PR #4 acceptance: six authenticated tabs × four responsive viewports.

Runs only against browser_http, a localhost Flask server backed by disposable
shursh_ci PostgreSQL; Supabase Auth transport is mocked by the test fixture.
Never execute this module against a hosted database or a real user account.

MutationObserver counts DOM mutations, NOT browser paint/compositor frames.
The navigation time is browser performance.now() through the E2E readiness
assertion (includes the automation scheduling/polling overhead).
"""
import json
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
VIEWPORTS = (375, 390, 768, 1440)
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
                        page.locator(selector).click()
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
                same = page.evaluate("window.__pr4Audit.end()")
                # The warm traversal ends on notifications.
                assert len(requests) == before
                assert same["newElements"] == 0
                assert same["childList"] == 0
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
            page.locator('header [data-nav="/profile"]').click()
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
            assert box is not None and abs(box["y"] + box["height"] - 812) <= 2, box
            assert box["x"] <= 2 and box["width"] >= 373, box
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
                page.locator(selector).click()
                expect(page.locator("#page-view main h1").first).to_contain_text(heading)
                expect(page.locator(".route-skeleton")).to_have_count(0)
            assert not traffic, ("Prefetched first visits unexpectedly fetched", traffic)
            page.context.set_offline(True)
            page.evaluate("() => { window.__pr4Clock=Date.now; Date.now=()=>window.__pr4Clock()+60*60*1000; }")
            # One hour later (> previous 10min DOM cache and 45s API TTL)
            # the app must still work offline with its intact DOM trees.
            for path,heading,selector in ROUTES:
                page.locator(selector).click()
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
                page.locator('[data-gallery-toast]').click()
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
