"""Resume asynchronous scraper runs without blindly starting a second paid run."""
import hashlib
import json
import re

from .config import DATA, read_json, secret, write_json
from .policy import NeedsReview


def dataset(client, source):
    actor = source['board']
    if not re.fullmatch(r'[A-Za-z0-9_~-]+', actor):
        raise ValueError('Invalid Apify actor ID')
    token = secret('APIFY_TOKEN')
    if not token:
        raise NeedsReview('Configure APIFY_TOKEN before running a LinkedIn scraper')
    fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:20]
    path = DATA / 'apify-runs' / f'{fingerprint}.json'
    state = read_json(path, {})
    headers = {'Authorization': f'Bearer {token}'}
    if state.get('status') == 'starting':
        raise NeedsReview('Apify start was interrupted or ambiguous; reconcile the run in Apify before clearing its local run record')
    if not state.get('run_id'):
        write_json(path, {'status': 'starting'})
        response = client.post(f'https://api.apify.com/v2/actors/{actor}/runs',
            headers=headers, params={'timeout': 600, 'maxItems': int(source.get('max_items', 100))},
            json=source.get('input', {}))
        response.raise_for_status()
        state = {'run_id': response.json()['data']['id'], 'status': 'running'}
        write_json(path, state)
    response = client.get(f"https://api.apify.com/v2/actor-runs/{state['run_id']}",
        headers=headers, params={'waitForFinish': 10})
    response.raise_for_status()
    run = response.json()['data']
    if run['status'] in {'READY', 'RUNNING', 'TIMING-OUT', 'ABORTING'}:
        return None
    if run['status'] != 'SUCCEEDED':
        # Preserve failed run for inspection rather than paying for repeated retries.
        raise NeedsReview('Apify run stopped with status ' + run['status'])
    return run['defaultDatasetId'], path


def consumed(path):
    # Only release the run after all items have been added to the durable queue.
    write_json(path, {})
