"""
Authentification :
  • Utilisateur : jeton d'accès Supabase Auth (JWT) transmis en
    `Authorization: Bearer`. Vérifié LOCALEMENT par chaque service avec les
    clés publiques du projet (JWKS, ES256/RS256) — signature, expiration,
    émetteur, audience. Aucun service ne fait confiance à un user_id envoyé
    en clair.
  • Service à service : en-tête `X-Internal-Token` (secret partagé par
    paire de services), comparé en temps constant.
"""
from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Header, HTTPException, Request

log = logging.getLogger(__name__)

ALLOWED_ALGS = ["ES256", "RS256", "EdDSA"]


@dataclass(frozen=True)
class User:
    id: str
    email: str
    token: str          # jeton brut, retransmis aux services en aval (RLS)


class TokenVerifier:
    def __init__(self, supabase_url: str, *, audience: str = "authenticated",
                 jwks_client: Optional[jwt.PyJWKClient] = None, leeway: int = 30):
        base = supabase_url.rstrip("/")
        self.issuer = f"{base}/auth/v1"
        self.audience = audience
        self.leeway = leeway
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=True, lifespan=3600, timeout=5,
        )

    def verify(self, token: str) -> User:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALLOWED_ALGS:
                raise jwt.InvalidAlgorithmError(f"alg {header.get('alg')!r} refusé")
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=ALLOWED_ALGS, audience=self.audience,
                issuer=self.issuer, leeway=self.leeway,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            log.info("Jeton refusé : %s", exc.__class__.__name__)
            raise HTTPException(401, "Jeton invalide ou expiré.",
                                headers={"WWW-Authenticate": "Bearer"}) from exc
        if claims.get("role") != "authenticated":
            raise HTTPException(403, "Rôle non autorisé.")
        return User(id=claims["sub"], email=claims.get("email", ""), token=token)


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentification requise.",
                            headers={"WWW-Authenticate": "Bearer"})
    return authorization[7:].strip()


def user_dependency(verifier_attr: str = "verifier"):
    """Dépendance FastAPI : vérifie le jeton et renvoie l'utilisateur."""
    def _dep(request: Request, authorization: str | None = Header(None)) -> User:
        verifier: TokenVerifier = getattr(request.app.state, verifier_attr)
        return verifier.verify(bearer_token(authorization))
    return _dep


def secure_equals(a: str, b: str) -> bool:
    """Comparaison en temps constant, sûre pour toute chaîne (y compris
    non-ASCII : hmac.compare_digest lève TypeError sur des str non-ASCII)."""
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))


def internal_dependency(expected_attr: str = "internal_token"):
    """Dépendance FastAPI : exige X-Internal-Token (appel service à service)."""
    def _dep(request: Request, x_internal_token: str | None = Header(None)) -> None:
        expected: str = getattr(request.app.state, expected_attr)
        if not expected or not secure_equals(x_internal_token or "", expected):
            raise HTTPException(401, "Appel interne non authentifié.")
    return _dep
