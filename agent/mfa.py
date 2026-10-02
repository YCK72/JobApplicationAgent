"""RFC 6238 TOTP for candidate-owned accounts with explicitly configured seeds."""
import base64
import hashlib
import hmac
import struct
import time

from .config import secret
from .policy import NeedsReview


def totp(seed, timestamp=None, *, digits=6, period=30):
    if digits not in (6, 8) or period not in (30, 60):
        raise ValueError('Unsupported TOTP parameters')
    normalized = ''.join(seed.split()).upper()
    key = base64.b32decode(normalized + '=' * (-len(normalized) % 8))
    if not key:
        raise ValueError('Empty TOTP seed')
    counter = int(time.time() if timestamp is None else timestamp) // period
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = struct.unpack('>I', digest[offset:offset+4])[0] & 0x7fffffff
    return str(number % 10**digits).zfill(digits)


def account_code(host, email):
    seed = secret(f'TOTP:{host}:{email}')
    if not seed:
        raise NeedsReview('Save the authenticator seed for this account in Settings or complete MFA in the browser')
    return totp(seed)
