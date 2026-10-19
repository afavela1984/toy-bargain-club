"""Official Best Buy API -> temporary state -> existing branded static site.
No product data is committed. Never print request URLs or exception bodies.
"""
import datetime as dt
import decimal
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
BRANDS = {'lego', 'mattel', 'hasbro', 'fisher-price', 'melissa & doug', 'vtech',
          'leapfrog', 'spin master', 'ravensburger', 'crayola', 'playmobil',
          'jazwares', 'mga entertainment', 'bandai', 'moose toys', 'hot wheels', 'barbie'}
FIELDS = 'sku,name,manufacturer,modelNumber,salePrice,regularPrice,onSale,onlineAvailability,condition,priceRestriction,url,image,categoryPath,details'
MAX_AGE = dt.timedelta(hours=48)

def stamp(now):
    return now.isoformat().replace('+00:00', 'Z')

def parse_stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)

def safe_url(value, hosts):
    try:
        u = urllib.parse.urlsplit(value)
        return u.scheme == 'https' and u.hostname in hosts and not u.username and not u.password and u.port in (None, 443)
    except (ValueError, TypeError):
        return False

def get_json(url, opener=urllib.request.urlopen, sleeper=time.sleep):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'Accept':'application/json', 'User-Agent':'ToyBargainClub/1.0'})
            with opener(request, timeout=25) as response:
                body = response.read(12_000_001)
                if len(body) > 12_000_000:
                    raise ValueError('response_too_large')
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError('retailer_http_' + str(exc.code)) from None
            # Respect bounded Retry-After without exposing headers/URLs.
            retry = exc.headers.get('Retry-After', '2')
            sleeper(min(30, max(1, int(retry))) if retry.isdigit() else 2 ** (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError('retailer_network_error') from None
            sleeper(2 ** (attempt + 1))
    raise RuntimeError('request_failed')

def discover(key, fetch=get_json, sleeper=time.sleep):
    products = []
    # All on-sale, orderable new products: classify by returned toy taxonomy,
    # rather than guessing a changing category ID or scraping retailer pages.
    for page in range(1, 21):
        query = urllib.parse.urlencode({'apiKey':key, 'format':'json', 'show':FIELDS,
            'pageSize':100, 'page':page, 'sort':'percentSavings.dsc'})
        url = 'https://api.bestbuy.com/v1/products(onSale=true&onlineAvailability=true&condition=new)?' + query
        payload = fetch(url)
        if not isinstance(payload, dict) or not isinstance(payload.get('products'), list):
            raise ValueError('invalid_retailer_schema')
        total = payload.get('totalPages')
        if type(total) is not int or total < 0:
            raise ValueError('invalid_pagination')
        products.extend(payload['products'])
        if page >= total:
            return products
        sleeper(1)  # One request per second; max 20 requests per run.
    # Bounded sample, honestly documented. Doesn't pretend complete catalog coverage.
    return products

def minimum_age(details):
    for d in details if isinstance(details, list) else []:
        if not isinstance(d, dict):
            continue
        label = str(d.get('name', '')).lower()
        if any(term in label for term in ('minimum age', 'recommended minimum age', 'recommended age', 'recommended age range')):
            value = str(d.get('value', '')).strip().lower()
            if any(x in value for x in ('month', 'adult', 'under')):
                continue
            m = re.match(r'^(?:ages?\s*)?(\d{1,2})(?:\s*(?:years?|yrs?|\+|and up|and older|[-–])|$)', value)
            if m and 3 <= int(m[1]) <= 17:
                return int(m[1])
    return None

def normalize(p, now):
    if not isinstance(p, dict):
        return None
    if p.get('onlineAvailability') is not True or p.get('onSale') is not True:
        return None
    if str(p.get('condition', '')).lower() != 'new' or p.get('priceRestriction') not in (None, ''):
        return None
    if str(p.get('manufacturer', '')).lower() not in BRANDS:
        return None
    path = p.get('categoryPath')
    if not isinstance(path, list) or not any(re.search(r'\btoys?\b', str(c.get('name', '')), re.I) for c in path if isinstance(c, dict)):
        return None
    name = p.get('name')
    if not isinstance(name, str) or not name.strip() or re.search(r'\b(refurbished|pre-owned|open.box|video game|blu.ray|dvd)\b', name, re.I):
        return None
    age = minimum_age(p.get('details'))
    if age is None or not str(p.get('sku', '')).isdigit():
        return None
    try:
        sale, regular = (decimal.Decimal(str(p[k])) for k in ('salePrice', 'regularPrice'))
        if not sale.is_finite() or not regular.is_finite() or not 0 < sale < regular <= 2000:
            return None
        savings = regular - sale
        discount = savings / regular * 100
        if discount < 25 or savings < 5:
            return None
    except (decimal.InvalidOperation, KeyError, TypeError):
        return None
    if not safe_url(p.get('url'), {'www.bestbuy.com', 'bestbuy.com'}):
        return None
    if not safe_url(p.get('image'), {'pisces.bbystatic.com', 'images.bestbuy.com'}):
        return None
    return dict(id='bestbuy-' + str(p['sku']), name=name, brand=p['manufacturer'],
        model=str(p.get('modelNumber') or ''), age=age, price=float(sale), regular=float(regular),
        savings=float(savings), discount=float(discount), url=p['url'], image=p['image'],
        category='Building toys' if 'lego' == str(p['manufacturer']).lower() else 'Toys & games',
        checked=stamp(now), expires=stamp(now + MAX_AGE))

def select(products, now):
    unique = {}
    for p in products:
        deal = normalize(p, now)
        if deal:
            unique[deal['id']] = deal
    return sorted(unique.values(), key=lambda d:(-d['discount'], -d['savings'], d['id']))[:100]

def fresh_state(old, now):
    # Same validator for persisted source rows prevents damaged state publishing.
    try:
        checked = parse_stamp(old['last_success'])
        if not dt.timedelta(0) <= now - checked < MAX_AGE:
            return None
        rows = old['source_products']
        if not isinstance(rows, list):
            return None
        deals = select(rows, checked)
        return {'last_success':stamp(checked), 'source_products':rows, 'deals':deals}
    except (KeyError, ValueError, TypeError, OverflowError):
        return None

def card(d, now):
    e = lambda v:html.escape(str(v), quote=True)
    attrs = dict(id=d['id'], age=d['age'], category=d['category'], discount=d['discount'],
        name=d['name'].lower(), price=d['price'], savings=d['savings'], checked=d['checked'], expires=d['expires'])
    data = ' '.join('data-' + k + '="' + e(v) + '"' for k,v in attrs.items())
    stale = now - parse_stamp(d['checked']) > dt.timedelta(hours=30)
    return f'''<article class="card toy-card" {data}><div class="photo"><img alt="{e(d['name'])}" src="{e(d['image'])}" loading="lazy" decoding="async" width="600" height="600" onerror="this.hidden=true;this.nextElementSibling.hidden=false"/><span class="img-fallback" style="display:flex" hidden>Photo unavailable — view exact product at Best Buy</span><span class="off">{math.floor(d['discount'])}% OFF</span><button type="button" class="favorite" data-fav="{e(d['id'])}" aria-label="Save {e(d['name'])}" aria-pressed="false">♡</button></div><div class="details"><div class="eyebrow">Best Buy · {e(d['category'])} · Minimum age {d['age']}</div><h3>{e(d['name'])}</h3><div class="prices"><strong>${d['price']:.2f}</strong><s>${d['regular']:.2f}</s></div><div class="saving">Save ${d['savings']:.2f} vs. retailer regular price</div><p class="price-note">Advertised discount; historical savings not independently verified.</p><p class="product-note">Model: {e(d['model'])}. Check product age guidance and shipping at Best Buy.</p><p class="verified">{'Stale price — confirm at retailer' if stale else 'Price checked: ' + e(d['checked'])}</p><a class="shop" href="{e(d['url'])}" target="_blank" rel="noopener noreferrer">Shop at Best Buy ↗</a></div></article>'''

def render(template, state, status, now, build_id):
    deals = state['deals'] if state else []
    local = parse_stamp(state['last_success']).astimezone(dt.timezone(dt.timedelta(hours=-7))) if state else None
    values = {'DEAL_CARDS': ''.join(card(d, now) for d in deals), 'DEAL_COUNT':str(len(deals)),
        'CHECK_TIME':html.escape('Last successful check: ' + local.strftime('%b %d, %Y · %I:%M %p Arizona') if local else 'No successful price check yet'),
        'STATUS':html.escape(status)}
    for k,v in values.items():
        template = template.replace('<!--' + k + '-->', v)
    return template.replace('</head>', '<meta name="tbc-build" content="' + html.escape(build_id, quote=True) + '"/></head>')

def main():
    now = dt.datetime.now(UTC)
    root = Path(__file__).resolve().parents[1]
    state_path = root / '.runtime/state.json'
    old = {}
    if state_path.exists():
        try:
            old = json.loads(state_path.read_text())
        except (ValueError, OSError):
            pass
    state = fresh_state(old, now)
    success = False
    key = os.environ.get('BESTBUY_API_KEY', '')
    if key:
        try:
            rows = discover(key)
            deals = select(rows, now)
            # Save only qualifying raw rows. All cache content expires within 48h;
            # artifact retention is 2 days and no pricing enters Git history.
            ids = {d['id'] for d in deals}
            source = [p for p in rows if 'bestbuy-' + str(p.get('sku')) in ids]
            state = {'last_success':stamp(now), 'source_products':source, 'deals':deals}
            success = True
            status = f'{len(deals)} qualifying deals from Best Buy. Prices exclude shipping and tax.'
        except Exception:
            # Do not print exception object: urllib exceptions may contain API key URLs.
            status = 'Retailer refresh failed. Showing the last successful check where still valid.' if state else 'Retailer refresh failed. No valid prices available.'
            print('::error::Best Buy refresh failed. Request details suppressed to protect credentials.')
    else:
        status = 'Automatic pricing is awaiting Best Buy API authorization. No live offers are claimed.'
        print('::error::BESTBUY_API_KEY is missing. No retailer request was made.')
    if not state:
        state = None
    out = root / 'dist'
    out.mkdir(exist_ok=True)
    build_id = os.environ.get('GITHUB_RUN_ID', 'local') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    page = render((root / 'templates/site.html').read_text(), state, status, now, build_id)
    (out / 'index.html').write_text(page)
    (out / '.nojekyll').touch()
    (out / 'build.json').write_text(json.dumps({'build_id':build_id, 'checked':state['last_success'] if state else None, 'count':len(state['deals']) if state else 0}))
    state_path.parent.mkdir(exist_ok=True)
    if state:
        state_path.write_text(json.dumps(state))
    elif state_path.exists():
        state_path.unlink()
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write('refresh_ok=' + str(success).lower() + '\n')
    print('Build complete: ' + str(len(state['deals']) if state else 0) + ' qualifying offers; refresh_ok=' + str(success).lower())

if __name__ == '__main__':
    main()
