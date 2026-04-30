"""
auth.py — Gestion de l'authentification locale
Utilise SHA-256 + sel aléatoire pour stocker les secrets en base.
"""
import hashlib
import secrets
import datetime
from database import Database


# ─────────────────────────────────────────────────────────────
#  Primitives cryptographiques
# ─────────────────────────────────────────────────────────────

def _generate_salt() -> str:
    return secrets.token_hex(16)


def _hash(value: str, salt: str) -> str:
    """SHA-256 du couple (valeur + sel). La valeur est normalisée."""
    normalized = value.strip().lower()
    return hashlib.sha256((normalized + salt).encode("utf-8")).hexdigest()


def _verify(value: str, stored_hash: str, salt: str) -> bool:
    return _hash(value, salt) == stored_hash


# ─────────────────────────────────────────────────────────────
#  Mot de passe
# ─────────────────────────────────────────────────────────────

def has_password(db: Database) -> bool:
    """Retourne True si un mot de passe a déjà été configuré."""
    return bool(db.get_setting("auth_password_hash"))


def setup_password(db: Database, password: str,
                   question: str, answer: str) -> None:
    """Initialise le mot de passe + question secrète (premier lancement)."""
    pwd_salt = _generate_salt()
    db.set_setting("auth_password_hash", _hash(password, pwd_salt))
    db.set_setting("auth_password_salt", pwd_salt)
    db.set_setting("auth_secret_question", question.strip())

    ans_salt = _generate_salt()
    db.set_setting("auth_secret_answer_hash", _hash(answer, ans_salt))
    db.set_setting("auth_secret_answer_salt", ans_salt)


def verify_password(db: Database, password: str) -> bool:
    stored = db.get_setting("auth_password_hash")
    salt   = db.get_setting("auth_password_salt")
    if not stored or not salt:
        return False
    return _verify(password, stored, salt)


def change_password(db: Database, new_password: str) -> None:
    """Change le mot de passe (appelé après vérification de la question secrète)."""
    pwd_salt = _generate_salt()
    db.set_setting("auth_password_hash", _hash(new_password, pwd_salt))
    db.set_setting("auth_password_salt", pwd_salt)


def update_secret_question(db: Database, question: str, answer: str) -> None:
    """Met à jour la question secrète."""
    db.set_setting("auth_secret_question", question.strip())
    ans_salt = _generate_salt()
    db.set_setting("auth_secret_answer_hash", _hash(answer, ans_salt))
    db.set_setting("auth_secret_answer_salt", ans_salt)


# ─────────────────────────────────────────────────────────────
#  Question secrète
# ─────────────────────────────────────────────────────────────

def get_secret_question(db: Database) -> str:
    return db.get_setting("auth_secret_question", "")


def verify_secret_answer(db: Database, answer: str) -> bool:
    stored = db.get_setting("auth_secret_answer_hash")
    salt   = db.get_setting("auth_secret_answer_salt")
    if not stored or not salt:
        return False
    return _verify(answer, stored, salt)


# ─────────────────────────────────────────────────────────────
#  Session persistante (30 jours)
# ─────────────────────────────────────────────────────────────

SESSION_DAYS = 30


def has_valid_session(db: Database) -> bool:
    """Retourne True si une session active existe (pas expirée)."""
    token  = db.get_setting("auth_session_token")
    expiry = db.get_setting("auth_session_expiry")
    if not token or not expiry:
        return False
    try:
        exp = datetime.date.fromisoformat(expiry)
        return datetime.date.today() <= exp
    except ValueError:
        return False


def create_session(db: Database) -> None:
    """Crée une session valide pour SESSION_DAYS jours."""
    token  = secrets.token_urlsafe(32)
    expiry = (datetime.date.today() +
               datetime.timedelta(days=SESSION_DAYS)).isoformat()
    db.set_setting("auth_session_token", token)
    db.set_setting("auth_session_expiry", expiry)


def clear_session(db: Database) -> None:
    db.set_setting("auth_session_token", "")
    db.set_setting("auth_session_expiry", "")


def session_expiry_label(db: Database) -> str:
    """Retourne une chaîne lisible de la date d'expiration de session."""
    expiry = db.get_setting("auth_session_expiry")
    if not expiry:
        return ""
    try:
        exp  = datetime.date.fromisoformat(expiry)
        days = (exp - datetime.date.today()).days
        if days <= 0:
            return "Session expirée"
        elif days == 1:
            return "Session expire demain"
        else:
            return f"Session valide encore {days} jours"
    except ValueError:
        return ""
