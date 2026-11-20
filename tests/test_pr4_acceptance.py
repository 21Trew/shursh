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
                stable_header = page.locator("header").element_handle()
                stable_footer = page.locator("footer").element_handle()
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
                        assert page.locator("header").element_handle() == stable_header
                        assert page.locator("footer").element_handle() == stable_footer

                # Clicking already active tab should do no app work.
                page.evaluate("window.__pr4Audit.begin()")
                before = len(requests)
                page.locator('header .nav [data-nav="/notifications"]').count() == 0
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
