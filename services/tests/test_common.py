import time

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from conftest import make_token
from fintrack_common.auth import secure_equals
from fintrack_common.ratelimit import Counter


def test_valid_token(verifier):
    u = verifier.verify(make_token("abc", "a@b.c"))
    assert (u.id, u.email) == ("abc", "a@b.c")


@pytest.mark.parametrize("token_kwargs", [
    {"exp_in": -120},                                   # expiré
    {"role": "anon"},                                   # pas un utilisateur
    {"iss": "https://autre.supabase.co/auth/v1"},       # autre projet
    {"key": ec.generate_private_key(ec.SECP256R1())},   # mauvaise signature
])
def test_rejected_tokens(verifier, token_kwargs):
    with pytest.raises(HTTPException) as e:
        verifier.verify(make_token("abc", **token_kwargs))
    assert e.value.status_code in (401, 403)


def test_hs256_token_refused(verifier):
    tok = __import__("jwt").encode({"sub": "x", "aud": "authenticated", "role": "authenticated",
                                    "iss": "https://proj.supabase.co/auth/v1",
                                    "exp": int(time.time()) + 60}, "secret" * 8,
                                   algorithm="HS256")
    with pytest.raises(HTTPException):
        verifier.verify(tok)


def test_secure_equals_non_ascii():
    # hmac.compare_digest(str, str) lève TypeError sur du non-ASCII (revue v2.0.0)
    assert secure_equals("élodie", "élodie")
    assert not secure_equals("élodie", "elodie")
    assert not secure_equals("", "x")


def test_local_counter_is_bounded():
    c = Counter(max_local=100)
    for i in range(1000):
        c.incr("s", str(i), window=60)
    assert len(c._local) <= 100


def test_counter_with_redis():
    import fakeredis
    c = Counter(fakeredis.FakeRedis(decode_responses=True), prefix="t")
    assert c.incr("x", "a", window=60) == 1
    assert c.incr("x", "a", window=60) == 2
    assert c.get("x", "a") == 2
    c.reset("x", "a")
    assert c.get("x", "a") == 0


def test_jwks_outage_is_503_not_401():
    import jwt as _jwt
    from fintrack_common.auth import TokenVerifier

    class Down:
        def get_signing_key_from_jwt(self, token):
            raise _jwt.PyJWKClientConnectionError("down")
    v = TokenVerifier("https://proj.supabase.co", jwks_client=Down())
    with pytest.raises(HTTPException) as e:
        v.verify(make_token("abc"))
    assert e.value.status_code == 503


def test_fmt_helpers():
    from fintrack_common.fmt import fmt_eur, month_name, shift_month
    assert fmt_eur(1234.5) == "1 234,50 €" and fmt_eur(3, sign=True) == "+3,00 €"
    assert shift_month(2026, 1, -1) == (2025, 12) and shift_month(2026, 12, 1) == (2027, 1)
    assert month_name(8, capitalize=True) == "Août"
