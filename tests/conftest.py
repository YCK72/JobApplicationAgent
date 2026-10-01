import pytest

from agent import config, db, reports, browser, server, gmail


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    for module in (config, db, reports, browser, server, gmail):
        monkeypatch.setattr(module, 'DATA', tmp_path)
    monkeypatch.setattr(config, 'secret', lambda name: None)
    db.init()
    return tmp_path


@pytest.fixture
def job():
    jid = db.add({'company': 'Example Research', 'title': 'Software Engineer',
                  'url': 'https://jobs.example.org/123', 'location': 'New York, NY, USA',
                  'description': 'Build Python services and databases.'})
    db.update(jid, resume='sde')
    return db.get(jid)
