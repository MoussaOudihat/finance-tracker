"""
auth.py — Authentification locale Fintrack

Hachage : bcrypt (préféré) + SHA-256 legacy avec migration automatique.
Stockage : app_settings (SQLite local).

Clés utilisées :
  auth_username            — nom d'utilisateur (en clair, pas sensible)
  auth_password_hash       — hash bcrypt ou SHA-256 du mot de passe
  auth_password_salt       — sel SHA-256 (vide si bcrypt)
  auth_secret_question     — question secrète (texte)
  auth_secret_answer_hash  — hash de la réponse
  auth_secret_answer_salt  — sel SHA-256 (vide si bcrypt)
  auth_session_token       — token session 30 jours
  auth_session_expiry      — date expiration ISO
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
    log.warning("bcrypt non installé — SHA-256 utilisé. "
                "Installez-le : pip install bcrypt")

_BCRYPT_PREFIX = "bcrypt:"


# ─────────────────────────────────────────────────────────────
#  Primitives cryptographiques
# ─────────────────────────────────────────────────────────────

def _generate_salt() -> str:
    return secrets.token_hex(16)


def _bcrypt_hash(value: str) -> str:
    normalized = value.strip().lower().encode("utf-8")
    return _BCRYPT_PREFIX + _bcrypt.hashpw(
        normalized, _bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def _bcrypt_verify(value: str, stored: str) -> bool:
    normalized = value.strip().lower().encode("utf-8")
    stored_hash = stored[len(_BCRYPT_PREFIX):].encode("utf-8")
    try:
        return _bcrypt.checkpw(normalized, stored_hash)
    except Exception:
        return False


def _sha_hash(value: str, salt: str) -> str:
    return hashlib.sha256(
        (value.strip().lower() + salt).encode("utf-8")
    ).hexdigest()


def _sha_verify(value: str, stored_hash: str, salt: str) -> bool:
    return _sha_hash(value, salt) == stored_hash


def _is_bcrypt(stored: str) -> bool:
    return stored.startswith(_BCRYPT_PREFIX)


def _do_hash(value: str) -> tuple[str, str]:
    """Retourne (hash, salt). Salt vide si bcrypt."""
    if _BCRYPT_AVAILABLE:
        return _bcrypt_hash(value), ""
    salt = _generate_salt()
    return _sha_hash(value, salt), salt


def _do_verify(value: str, stored_hash: str, stored_salt: str) -> bool:
    if _is_bcrypt(stored_hash):
        return _BCRYPT_AVAILABLE and _bcrypt_verify(value, stored_hash)
    return _sha_verify(value, stored_hash, stored_salt)


# ─────────────────────────────────────────────────────────────
#  USERNAME
# ─────────────────────────────────────────────────────────────

def get_username(db: Database) -> str:
    """Retourne le nom d'utilisateur configuré, ou chaîne vide."""
    return db.get_setting("auth_username", "")


def verify_username(db: Database, username: str) -> bool:
    """Vérifie que le username correspond (insensible à la casse)."""
    stored = get_username(db)
    if not stored:
        return False
    return stored.strip().lower() == username.strip().lower()


# ─────────────────────────────────────────────────────────────
#  MOT DE PASSE
# ─────────────────────────────────────────────────────────────

def has_password(db: Database) -> bool:
    return bool(db.get_setting("auth_password_hash"))


def setup_password(db: Database, username: str, password: str,
                   question: str, answer: str) -> None:
    """
    Initialise le compte au premier lancement.
    username  : affiché à la connexion, stocké en clair
    password  : haché (bcrypt ou SHA-256)
    question  : texte libre de la question secrète
    answer    : haché comme le mot de passe
    """
    db.set_setting("auth_username", username.strip())

    h, s = _do_hash(password)
    db.set_setting("auth_password_hash", h)
    db.set_setting("auth_password_salt", s)

    db.set_setting("auth_secret_question", question.strip())
    ah, as_ = _do_hash(answer)
    db.set_setting("auth_secret_answer_hash", ah)
    db.set_setting("auth_secret_answer_salt", as_)


# ─────────────────────────────────────────────────────────────
#  PROTECTION BRUTE-FORCE
# ─────────────────────────────────────────────────────────────

_LOCKOUT_MAX_ATTEMPTS = 5     # tentatives avant verrouillage
_LOCKOUT_MINUTES       = 10   # durée du verrouillage


def check_lockout(db: Database) -> tuple[bool, str]:
    """
    Retourne (is_locked, message).
    is_locked=True signifie que le compte est temporairement bloqué.
    """
    locked_until = db.get_setting("auth_locked_until", "")
    if not locked_until:
        return False, ""
    try:
        until_dt = datetime.datetime.fromisoformat(locked_until)
        remaining = (until_dt - datetime.datetime.now()).total_seconds()
        if remaining > 0:
            mins = int(remaining // 60) + 1
            return True, f"Compte verrouillé — réessayez dans {mins} min."
        # Verrouillage expiré — réinitialiser
        db.set_setting("auth_locked_until", "")
        db.set_setting("auth_failed_count", "0")
    except ValueError:
        db.set_setting("auth_locked_until", "")
    return False, ""


def record_failed_login(db: Database) -> None:
    """Incrémente le compteur d'échecs et verrouille si seuil atteint."""
    count = int(db.get_setting("auth_failed_count", "0")) + 1
    db.set_setting("auth_failed_count", str(count))
    if count >= _LOCKOUT_MAX_ATTEMPTS:
        until = (
            datetime.datetime.now()
            + datetime.timedelta(minutes=_LOCKOUT_MINUTES)
        ).isoformat()
        db.set_setting("auth_locked_until", until)
        log.warning("Compte verrouillé après %d tentatives échouées.", count)
    else:
        log.info("Tentative de connexion échouée (%d/%d).", count, _LOCKOUT_MAX_ATTEMPTS)


def clear_failed_logins(db: Database) -> None:
    """Réinitialise le compteur après connexion réussie."""
    db.set_setting("auth_failed_count", "0")
    db.set_setting("auth_locked_until", "")


def verify_password(db: Database, password: str) -> bool:
    """Vérifie le mot de passe. Migre SHA-256 → bcrypt si possible."""
    stored = db.get_setting("auth_password_hash")
    if not stored:
        return False

    if _is_bcrypt(stored):
        return _BCRYPT_AVAILABLE and _bcrypt_verify(password, stored)

    # SHA-256 legacy
    salt = db.get_setting("auth_password_salt", "")
    if not _sha_verify(password, stored, salt):
        return False
    if _BCRYPT_AVAILABLE:
        log.info("Migration hash mot de passe SHA-256 → bcrypt")
        h, _ = _do_hash(password)
        db.set_setting("auth_password_hash", h)
        db.set_setting("auth_password_salt", "")
    return True


def change_password(db: Database, new_password: str) -> None:
    h, s = _do_hash(new_password)
    db.set_setting("auth_password_hash", h)
    db.set_setting("auth_password_salt", s)


# ─────────────────────────────────────────────────────────────
#  QUESTION SECRÈTE
# ─────────────────────────────────────────────────────────────

def get_secret_question(db: Database) -> str:
    return db.get_setting("auth_secret_question", "")


def verify_secret_answer(db: Database, answer: str) -> bool:
    stored = db.get_setting("auth_secret_answer_hash")
    salt   = db.get_setting("auth_secret_answer_salt", "")
    if not stored:
        return False
    if not _do_verify(answer, stored, salt):
        return False
    # Migration bcrypt si SHA-256 legacy
    if not _is_bcrypt(stored) and _BCRYPT_AVAILABLE:
        ah, _ = _do_hash(answer)
        db.set_setting("auth_secret_answer_hash", ah)
        db.set_setting("auth_secret_answer_salt", "")
    return True


def update_secret_question(db: Database, question: str, answer: str) -> None:
    db.set_setting("auth_secret_question", question.strip())
    ah, as_ = _do_hash(answer)
    db.set_setting("auth_secret_answer_hash", ah)
    db.set_setting("auth_secret_answer_salt", as_)


# ─────────────────────────────────────────────────────────────
#  SESSION (7 jours)
# ─────────────────────────────────────────────────────────────

SESSION_DAYS = 7


def has_valid_session(db: Database) -> bool:
    token  = db.get_setting("auth_session_token")
    expiry = db.get_setting("auth_session_expiry")
    if not token or not expiry:
        return False
    try:
        return datetime.date.today() <= datetime.date.fromisoformat(expiry)
    except ValueError:
        return False


def create_session(db: Database) -> None:
    expiry = (datetime.date.today() +
              datetime.timedelta(days=SESSION_DAYS)).isoformat()
    db.set_setting("auth_session_token", secrets.token_urlsafe(32))
    db.set_setting("auth_session_expiry", expiry)


def clear_session(db: Database) -> None:
    db.set_setting("auth_session_token", "")
    db.set_setting("auth_session_expiry", "")


def session_expiry_label(db: Database) -> str:
    expiry = db.get_setting("auth_session_expiry")
    if not expiry:
        return ""
    try:
        days = (datetime.date.fromisoformat(expiry) - datetime.date.today()).days
        if days <= 0:
            return "Session expirée"
        if days == 1:
            return "Session expire demain"
        return f"Session valide encore {days} jours"
    except ValueError:
        return ""
