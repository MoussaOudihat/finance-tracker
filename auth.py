"""
auth.py — Gestion de l'authentification locale

Hachage : bcrypt (si disponible) avec migration automatique depuis l'ancien SHA-256.
Migration transparente : à la première connexion réussie avec un hash SHA-256 legacy,
le mot de passe est automatiquement re-haché en bcrypt sans action utilisateur.

Pour installer bcrypt : python -m pip install bcrypt
"""
import hashlib
import secrets
import datetime
from database import Database
from logger import log

# ── Détection bcrypt ─────────────────────────────────────────
try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False
    log.warning("bcrypt non installé — hachage legacy SHA-256 utilisé. "
                "Installez bcrypt : python -m pip install bcrypt")

_BCRYPT_PREFIX = "bcrypt:"   # préfixe pour distinguer les hashs bcrypt des SHA-256 legacy


# ─────────────────────────────────────────────────────────────
#  Primitives cryptographiques — bcrypt (préféré) + SHA-256 (legacy)
# ─────────────────────────────────────────────────────────────

def _generate_salt() -> str:
    return secrets.token_hex(16)


# ── Bcrypt ───────────────────────────────────────────────────
def _bcrypt_hash(value: str) -> str:
    """Retourne un hash bcrypt préfixé par _BCRYPT_PREFIX."""
    normalized = value.strip().lower().encode("utf-8")
    hashed = _bcrypt.hashpw(normalized, _bcrypt.gensalt(rounds=12))
    return _BCRYPT_PREFIX + hashed.decode("utf-8")


def _bcrypt_verify(value: str, stored: str) -> bool:
    normalized = value.strip().lower().encode("utf-8")
    stored_hash = stored[len(_BCRYPT_PREFIX):].encode("utf-8")
    try:
        return _bcrypt.checkpw(normalized, stored_hash)
    except Exception:
        return False


# ── SHA-256 legacy (conservé pour rétrocompatibilité) ────────
def _hash(value: str, salt: str) -> str:
    normalized = value.strip().lower()
    return hashlib.sha256((normalized + salt).encode("utf-8")).hexdigest()


def _verify(value: str, stored_hash: str, salt: str) -> bool:
    return _hash(value, salt) == stored_hash


def _is_bcrypt(stored: str) -> bool:
    return stored.startswith(_BCRYPT_PREFIX)


# ─────────────────────────────────────────────────────────────
#  Mot de passe
# ─────────────────────────────────────────────────────────────

def has_password(db: Database) -> bool:
    """Retourne True si un mot de passe a déjà été configuré."""
    return bool(db.get_setting("auth_password_hash"))


def setup_password(db: Database, password: str,
                   question: str, answer: str) -> None:
    """Initialise le mot de passe + question secrète (premier lancement)."""
    if _BCRYPT_AVAILABLE:
        db.set_setting("auth_password_hash", _bcrypt_hash(password))
        db.set_setting("auth_password_salt", "")          # non utilisé avec bcrypt
        db.set_setting("auth_secret_answer_hash", _bcrypt_hash(answer))
        db.set_setting("auth_secret_answer_salt", "")
    else:
        pwd_salt = _generate_salt()
        db.set_setting("auth_password_hash", _hash(password, pwd_salt))
        db.set_setting("auth_password_salt", pwd_salt)
        ans_salt = _generate_salt()
        db.set_setting("auth_secret_answer_hash", _hash(answer, ans_salt))
        db.set_setting("auth_secret_answer_salt", ans_salt)
    db.set_setting("auth_secret_question", question.strip())


def verify_password(db: Database, password: str) -> bool:
    """
    Vérifie le mot de passe. Migre automatiquement les hashs SHA-256 legacy
    vers bcrypt à la première connexion réussie.
    """
    stored = db.get_setting("auth_password_hash")
    if not stored:
        return False

    if _is_bcrypt(stored):
        # Hash bcrypt moderne
        return _BCRYPT_AVAILABLE and _bcrypt_verify(password, stored)

    # ── Hash SHA-256 legacy ──────────────────────────────────
    salt = db.get_setting("auth_password_salt", "")
    if not _verify(password, stored, salt):
        return False
    # Migration automatique vers bcrypt après succès
    if _BCRYPT_AVAILABLE:
        log.info("Migration du hash mot de passe SHA-256 → bcrypt")
        db.set_setting("auth_password_hash", _bcrypt_hash(password))
        db.set_setting("auth_password_salt", "")
    return True


def change_password(db: Database, new_password: str) -> None:
    """Change le mot de passe (appelé après vérification de la question secrète)."""
    if _BCRYPT_AVAILABLE:
        db.set_setting("auth_password_hash", _bcrypt_hash(new_password))
        db.set_setting("auth_password_salt", "")
    else:
        pwd_salt = _generate_salt()
        db.set_setting("auth_password_hash", _hash(new_password, pwd_salt))
        db.set_setting("auth_password_salt", pwd_salt)


def update_secret_question(db: Database, question: str, answer: str) -> None:
    """Met à jour la question secrète."""
    db.set_setting("auth_secret_question", question.strip())
    if _BCRYPT_AVAILABLE:
        db.set_setting("auth_secret_answer_hash", _bcrypt_hash(answer))
        db.set_setting("auth_secret_answer_salt", "")
    else:
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
    if not stored:
        return False
    if _is_bcrypt(stored):
        return _BCRYPT_AVAILABLE and _bcrypt_verify(answer, stored)
    # Legacy SHA-256
    salt = db.get_setting("auth_secret_answer_salt", "")
    if not _verify(answer, stored, salt):
        return False
    # Migration vers bcrypt
    if _BCRYPT_AVAILABLE:
        db.set_setting("auth_secret_answer_hash", _bcrypt_hash(answer))
        db.set_setting("auth_secret_answer_salt", "")
    return True


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
