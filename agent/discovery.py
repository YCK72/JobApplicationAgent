import html
import re
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from . import db, apify_source
from .config import secret
from .policy import NeedsReview


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = TextParser()
    parser.feed(html.unescape(value or ''))
    return ' '.join(parser.parts)


def discover(config):
    found = 0
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for source in config.sources:
            try:
                board = source['board']
                provider = source['provider']
                if provider != 'apify_actor' and not re.fullmatch(r'[A-Za-z0-9_-]+', board):
                    raise ValueError('Invalid board slug')
                run_path = None
                if provider == 'apify_actor':
                    result = apify_source.dataset(client, source)
                    if result is None:
                        db.event('Apify scraper running; results will be imported on the next discovery cycle')
                        continue
                    board, run_path = result
                if provider in ('apify', 'apify_actor'):
                    token = secret('APIFY_TOKEN')
                    resp = client.get(f'https://api.apify.com/v2/datasets/{board}/items',
                        params={'clean': 'true', 'format': 'json', 'limit': 10000},
                        headers={'Authorization': f'Bearer {token}'} if token else {})
                    resp.raise_for_status()
                    postings = []
                    for j in resp.json():
                        url = j.get('applyUrl') or j.get('applicationUrl')
                        if not url or not url.startswith('https://'):
                            continue
                        postings.append(dict(title=j.get('title') or j.get('jobTitle') or '',
                            url=url, company=j.get('companyName') or source.get('company', ''),
                            location=j.get('location') or '',
                            description=j.get('descriptionText') or plain(j.get('descriptionHtml', ''))))
                elif provider == 'greenhouse':
                    resp = client.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs', params={'content': 'true'})
                    resp.raise_for_status()
                    postings = [dict(title=j['title'], url=j['absolute_url'],
                        location=j['location']['name'], description=plain(j.get('content', '')))
                        for j in resp.json()['jobs']]
                elif provider == 'ashby':
                    resp = client.get(f'https://api.ashbyhq.com/posting-api/job-board/{board}')
                    resp.raise_for_status()
                    postings = [dict(title=j['title'], url=j.get('applyUrl') or j['jobUrl'],
                        location='; '.join(filter(None, [j.get('location', ''),
                            (j.get('address') or {}).get('postalAddress', {}).get('addressCountry', '')])),
                        description=j.get('descriptionPlain', '') or plain(j.get('descriptionHtml', '')))
                        for j in resp.json()['jobs'] if j.get('isListed', True)]
                elif provider == 'lever':
                    postings = []
                    for skip in range(0, 10000, 100):
                        resp = client.get(f'https://api.lever.co/v0/postings/{board}', params={'mode': 'json', 'limit': 100, 'skip': skip})
                        resp.raise_for_status()
                        batch = resp.json()
                        for j in batch:
                            postings.append(dict(title=j['text'], url=j['applyUrl'],
                                location=j.get('categories', {}).get('location', ''),
                                description=plain(j.get('description', '') + ' '.join(
                                    x.get('content', '') for x in j.get('lists', [])) + j.get('additional', ''))))
                        if len(batch) < 100:
                            break
                else:
                    raise ValueError('Unknown source provider')
                for j in postings:
                    db.add(dict(j, company=j.get('company') or source['company'], source=provider))
                    found += 1
                db.event(f"Discovery: {source['company']}: {len(postings)} postings")
                if run_path:
                    apify_source.consumed(run_path)
            except Exception as exc:
                reason = str(exc) if isinstance(exc, NeedsReview) else type(exc).__name__
                db.event(f"Discovery failed for {source.get('company', 'source')}: {reason}")
        app_id, app_key = secret('ADZUNA_APP_ID'), secret('ADZUNA_APP_KEY')
        if app_id and app_key:
            for query in config.queries:
                for page in range(1, 4):
                    try:
                        r = client.get(f'https://api.adzuna.com/v1/api/jobs/us/search/{page}', params={
                            'app_id': app_id, 'app_key': app_key, 'what': query, 'results_per_page': 50,
                            'sort_by': 'date', 'max_days_old': 14})
                        r.raise_for_status()
                        rows = r.json()['results']
                        for j in rows:
                            db.add(dict(title=j['title'], company=j['company']['display_name'],
                                location=j['location']['display_name'], url=j['redirect_url'],
                                description=plain(j['description']), source='adzuna'))
                            found += 1
                        if len(rows) < 50:
                            break
                    except Exception as exc:
                        db.event(f'Adzuna discovery failed: {type(exc).__name__}')
                        break
    return found
