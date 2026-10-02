import argparse
import getpass
import json
import shutil
from pathlib import Path

from pypdf import PdfReader

from . import db, gmail, reports
from .config import DATA, profile, set_secret, write_json


def main():
    parser = argparse.ArgumentParser(description='Job Application Agent')
    commands = parser.add_subparsers(dest='command', required=True)
    imp = commands.add_parser('import-resume')
    imp.add_argument('--kind', choices=['sde', 'aiml', 'ds', 'it', 'cv'], required=True)
    imp.add_argument('--path', type=Path, required=True)
    auth = commands.add_parser('gmail-auth')
    auth.add_argument('--client', type=Path, default=Path('secrets/gmail-client.json'))
    key = commands.add_parser('set-key')
    key.add_argument('name', choices=['OPENAI_API_KEY', 'ADZUNA_APP_ID', 'ADZUNA_APP_KEY', 'APIFY_TOKEN'])
    commands.add_parser('export')
    commands.add_parser('serve')
    args = parser.parse_args()
    db.init()
    if args.command == 'import-resume':
        text = '\n'.join(p.extract_text() or '' for p in PdfReader(args.path).pages)
        folder = DATA / 'resumes'
        folder.mkdir(exist_ok=True)
        target = folder / f'{args.kind}.pdf'
        shutil.copy2(args.path, target)
        p = profile()
        p.setdefault('resumes', {})[args.kind] = {
            'path': str(target.resolve()), 'text': text, 'enabled': args.kind != 'cv',
            'role': {'sde': 'Software Engineering', 'aiml': 'AI and Machine Learning',
                     'ds': 'Data Science', 'it': 'IT and Cloud Infrastructure', 'cv': 'Research reference only'}[args.kind]}
        write_json(DATA / 'profile.json', p)
        print(f'Imported {args.kind} into private local data')
    elif args.command == 'gmail-auth':
        print('Connected:', gmail.authorize(args.client))
    elif args.command == 'set-key':
        set_secret(args.name, getpass.getpass(f'{args.name}: '))
        print('Stored in the operating system credential vault')
    elif args.command == 'export':
        print(reports.export())
    elif args.command == 'serve':
        import sys
        # pythonw has no console streams when launched by Task Scheduler.
        if sys.stdout is None:
            sys.stdout = (DATA / 'server.log').open('a', encoding='utf-8', buffering=1)
        if sys.stderr is None:
            sys.stderr = (DATA / 'server-error.log').open('a', encoding='utf-8', buffering=1)
        import uvicorn
        uvicorn.run('agent.server:app', host='127.0.0.1', port=8765)


if __name__ == '__main__':
    main()
