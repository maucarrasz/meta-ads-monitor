from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import scraper


def browser_with_text(monkeypatch, text, url="https://www.facebook.com/ads/library/"):
    page = SimpleNamespace(url=url, goto=lambda *a, **kw: None,
                           wait_for_timeout=lambda _: None,
                           inner_text=lambda *a, **kw: text)
    browser = SimpleNamespace(new_context=lambda **kw: SimpleNamespace(new_page=lambda: page), close=lambda: None)

    @contextmanager
    def playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw: browser))

    monkeypatch.setattr(scraper, "sync_playwright", playwright)


@pytest.mark.parametrize("text,count,estimate", [
    ("Meta Ad Library\n~1,234 results\nAds", 1234, True),
    ("About 45 results", 45, True),
    ("45 results", 45, False),
    ("No ads match your search criteria", 0, False),
])
def test_count_is_read_from_actual_body(monkeypatch, text, count, estimate):
    browser_with_text(monkeypatch, text)
    evidence = {}
    assert scraper.read_count("https://www.facebook.com/ads/library/", use_state=False, evidence=evidence) == (count, "OK")
    assert evidence["text"] == text
    assert evidence.get("is_estimate", False) is estimate


@pytest.mark.parametrize("text,state", [
    ("23 results\nYou must log in to continue", "LOGIN_REQUIRED"),
    ("No results\nConfirm your identity", "LOGIN_REQUIRED"),
    ("No results\nYou’re temporarily blocked", "BLOCKED"),
    ("Nothing verifiable on this page", "NONE"),
    ("1.2M results", "NONE"),
])
def test_missing_or_blocked_read_is_not_a_count(monkeypatch, text, state):
    browser_with_text(monkeypatch, text)
    value, status = scraper.read_count("https://www.facebook.com/ads/library/", use_state=False)
    assert not isinstance(value, int)
    assert status == state


@pytest.mark.parametrize('body,literal', [
    ('Meta Ad Library\n42 results\nActual cards', '42 results'),
    ('Meta Ad Library\n~1,234 results\nActual cards', '~1,234 results'),
    ('Meta Ad Library\nAbout 45 results\nActual cards', 'About 45 results'),
    ('No ads match your search criteria', 'No ads match your search criteria'),
    ('0 results', '0 results'),
])
def test_ingesta_count_text_retains_actual_read_literal(monkeypatch, body, literal):
    browser_with_text(monkeypatch, body)
    evidence = {}
    scraper.read_count('https://www.facebook.com/ads/library/', use_state=False, evidence=evidence)
    assert evidence['count_text'] == literal


def test_internal_reader_keeps_count_text_without_changing_http_schema(monkeypatch):
    import read_domain
    def read_count(url, **kwargs):
        kwargs['evidence'].update({'text': '42 results', 'count_text': '42 results', 'is_estimate': False})
        return 42, 'OK'
    monkeypatch.setattr(read_domain, 'read_count', read_count)
    internal = read_domain.read('example.com', include_count_text=True)
    public = read_domain.read('example.com')
    assert internal['_count_text'] == '42 results'
    assert '_count_text' not in public
    assert public['is_estimate'] is False


def test_runtime_can_use_preinstalled_chrome_without_changing_default(monkeypatch):
    launches = []
    browser_with_text(monkeypatch, '42 results')
    original = scraper.sync_playwright
    @contextmanager
    def playwright():
        with original() as api:
            launch = api.chromium.launch
            api.chromium.launch = lambda **kw: launches.append(kw) or launch(**kw)
            yield api
    monkeypatch.setattr(scraper, 'sync_playwright', playwright)
    monkeypatch.delenv('PLAYWRIGHT_CHROMIUM_CHANNEL', raising=False)
    scraper.read_count('https://www.facebook.com/ads/library/', use_state=False)
    monkeypatch.setenv('PLAYWRIGHT_CHROMIUM_CHANNEL', 'chrome')
    scraper.read_count('https://www.facebook.com/ads/library/', use_state=False)
    assert 'channel' not in launches[0]
    assert launches[1]['channel'] == 'chrome'


@pytest.fixture(autouse=True)
def _clean_zero(monkeypatch):
    monkeypatch.setattr(scraper, "clean_recheck", lambda url, timeout_ms=120000: ("ZERO", 0, "No ads match your search criteria"))


def test_zero_confirmed_in_clean_session_is_flagged(monkeypatch):
    browser_with_text(monkeypatch, "No ads match your search criteria")
    ev = {}
    assert scraper.read_count("https://www.facebook.com/ads/library/", use_state=False, evidence=ev) == (0, "OK")
    assert ev["zero_clean_confirmed"] is True


def test_zero_contradicted_by_clean_session_uses_the_number(monkeypatch):
    browser_with_text(monkeypatch, "No ads match your search criteria")
    monkeypatch.setattr(scraper, "clean_recheck", lambda url, timeout_ms=120000: ("NUMBER", 1900, "~1,900 results"))
    ev = {}
    assert scraper.read_count("https://www.facebook.com/ads/library/", use_state=False, evidence=ev) == (1900, "OK")
    assert ev["zero_overridden_by_clean"] is True and "zero_clean_confirmed" not in ev


def test_zero_not_confirmable_is_none_never_zero(monkeypatch):
    browser_with_text(monkeypatch, "No ads match your search criteria")
    monkeypatch.setattr(scraper, "clean_recheck", lambda url, timeout_ms=120000: ("UNKNOWN", None, ""))
    assert scraper.read_count("https://www.facebook.com/ads/library/", use_state=False) == ("NONE", "ZERO_UNCONFIRMED")
