"""One public browser for the daily saved-product URL queue; never loads login state."""
import datetime
import hashlib
import os
import re
from urllib.parse import urlencode, urlparse, parse_qs
from ads_worker import valid_domain
from scraper import LOGIN_MARKERS


def product_ads_url(phrase):
    if not isinstance(phrase,str) or '/products/' not in phrase:
        raise ValueError('INVALID_PRODUCT_URL')
    domain,handle=phrase.split('/products/',1)
    if not valid_domain(domain) or not re.fullmatch(r'[a-zA-Z0-9_-]+',handle):
        raise ValueError('INVALID_PRODUCT_URL')
    return 'https://www.facebook.com/ads/library/?'+urlencode(dict(active_status='active',ad_type='all',country='ALL',q='"'+phrase+'"',search_type='keyword_exact_phrase'))


def exact_scope(phrase,url):
    try:
        parsed=urlparse(url);query=parse_qs(parsed.query,keep_blank_values=True)
        return (parsed.scheme=='https' and parsed.netloc in {'www.facebook.com','facebook.com'}
                and parsed.path.rstrip('/')=='/ads/library'
                and all(query.get(key)==[value] for key,value in dict(active_status='active',country='ALL',q='"'+phrase+'"',search_type='keyword_exact_phrase').items()))
    except ValueError:return False


def product_observation(phrase,text,current_url):
    evidence_url=product_ads_url(phrase);low=text.lower();failure='NO_VERIFIABLE_COUNT';count=None
    if 'login' in current_url.lower() or 'checkpoint' in current_url.lower() or any(marker in low for marker in LOGIN_MARKERS):
        failure='LOGIN_REQUIRED'
    elif any(marker in low for marker in ('temporarily blocked','access denied','unusual activity','too many requests')):
        failure='BLOCKED'
    elif not exact_scope(phrase,current_url):
        failure='NO_VERIFIABLE_COUNT'
    else:
        # Only a real total label counts. An empty-state message cannot manufacture zero.
        for line in text.splitlines():
            match=re.fullmatch(r'\s*(?:(?:about|approximately)\s+)?~?\s*(\d{1,3}(?:,\d{3})+|\d+)\s+(?:results?|resultados?|anuncios?)\s*',line,re.I)
            if match:
                count=int(match.group(1).replace(',',''));failure=None;break
    return dict(status='ready' if count is not None else 'error',value=count,
                observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                source='META_AD_LIBRARY',method='meta_product_url_total_v1',
                evidence_url=evidence_url,evidence_sha256=hashlib.sha256(text.encode()).hexdigest(),error_code=failure)


class SavedProductReader:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.playwright=sync_playwright().start()
        options=dict(headless=True)
        if os.environ.get('PLAYWRIGHT_CHROMIUM_CHANNEL'):options['channel']=os.environ['PLAYWRIGHT_CHROMIUM_CHANNEL']
        self.browser=self.playwright.chromium.launch(**options)
        self.context=self.browser.new_context(locale='en-US')
        self.page=self.context.new_page()
        return self

    def read(self,phrase):
        try:
            self.page.goto(product_ads_url(phrase),wait_until='domcontentloaded',timeout=60000)
            self.page.wait_for_timeout(12000)
            text=self.page.inner_text('body',timeout=15000)
            return product_observation(phrase,text,self.page.url)
        except Exception:
            return dict(status='error',value=None,error_code='READ_ERROR')

    def __exit__(self,*args):
        try:self.browser.close()
        finally:self.playwright.stop()
