import re
from urllib.parse import urlsplit
import ipaddress
import socket


class NeedsReview(Exception):
    def __init__(self, reason, questions=None):
        super().__init__(reason)
        self.questions = questions or []


def normalized(text):
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def major_company(company, names):
    name = ' ' + normalized(company) + ' '
    return any(' ' + normalized(n) + ' ' in name for n in names)


def public_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Only public HTTPS application URLs are accepted')
    for addr in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(addr[4][0]).is_global:
            raise ValueError('Private and local network addresses are not allowed')
    return url


def coarse_reject(job, profile=None):
    title = job['title'].lower()
    if not re.search(r'engineer|developer|data scien|machine learning|research|mlops|ai |analyst|it specialist|it support|help.?desk|support specialist|business intelligence|systems? admin|devops|\bsre\b|infrastructure', title):
        return 'Outside the technical roles represented by the resumes'
    if re.search(r'\b(senior|sr\.?|staff|principal|lead|director|vice president|head of|manager)\b', title):
        return 'Seniority exceeds documented experience'
    text = job['description'].lower()
    if (profile or {}).get('requires_sponsorship') is True and re.search(r'(?:cannot|unable to|do not|does not|will not)\s+(?:offer |provide )?sponsor|no (?:visa )?sponsorship|without (?:current or future )?sponsorship', text):
        return 'Posting explicitly excludes required sponsorship'
    return ''


# These answers represent choices or facts an LLM cannot establish from a resume.
DECISION = re.compile(r'salary|compensation|pay expectation|start date|available to start|notice period|'
    r'disability|veteran|gender|race|ethnic|sexual|pronoun|criminal|convict|'
    r'background check|drug test|arbitration|agree|consent|certify|signature|'
    r'non.?compete|conflict of interest|relative|previously (?:applied|employed)|'
    r'export control|citizenship|security clearance|social security|passport|'
    r'expir|ead|stem opt|gpa|grade point', re.I)


def factual_answer(label, p):
    q = normalized(label)
    if DECISION.search(label):
        return None
    exact = {
        'first name': p.get('first_name'), 'given name': p.get('first_name'),
        'last name': p.get('last_name'), 'family name': p.get('last_name'),
        'full name': p.get('name'), 'name': p.get('name'),
        'email': p.get('email'), 'email address': p.get('email'),
        'phone': p.get('phone'), 'phone number': p.get('phone'),
        'linkedin': p.get('linkedin'), 'linkedin profile': p.get('linkedin'),
        'linkedin url': p.get('linkedin'), 'github': p.get('github'),
        'github url': p.get('github'), 'city': p.get('city'),
        'current location': p.get('location'), 'country': p.get('country'),
    }
    if q in exact:
        return exact[q]
    if 'sponsor' in q and not re.search(r'without|not require|no sponsor|do not', q):
        if re.search(r'currently|right now|at present', q) and 'future' not in q:
            return None
        value = p.get('requires_sponsorship')
        return ('Yes' if value else 'No') if isinstance(value, bool) else None
    if re.search(r'(legally authorized|authorized to work|eligible to work)', q) and not re.search(r'without|permanent|indefinit', q):
        value = p.get('authorized_to_work_us')
        return ('Yes' if value else 'No') if isinstance(value, bool) else None
    if re.search(r'willing to relocate|open to relocation', q):
        value = p.get('willing_to_relocate')
        return ('Yes' if value else 'No') if isinstance(value, bool) else None
    return None
