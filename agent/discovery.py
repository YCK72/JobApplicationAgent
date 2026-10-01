import html
import re
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from . import db
from .config import secret


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
                if not re.fullmatch(r'[A-Za-z0-9_-]+', board):
                    raise ValueError('Invalid board slug')
                provider = source['provider']
                if provider == 'greenhouse':
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
                    db.add(dict(j, company=source['company'], source=provider))
                    found += 1
                db.event(f"Discovery: {source['company']}: {len(postings)} postings")
            except Exception as exc:
                db.event(f"Discovery failed for {source.get('company', 'source')}: {type(exc).__name__}")
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
