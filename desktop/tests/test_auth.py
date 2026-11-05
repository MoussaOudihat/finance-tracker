"""Authentification locale : compatibilité bcrypt 5 (mots de passe > 72 octets)."""
import bcrypt
import pytest

import auth
from database import Database

LONG = "é" * 40 + " phrase de passe très longue"      # > 72 octets en UTF-8


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "a.db"))
    yield d
    d.close()


def test_long_password_roundtrip(db):
    auth.setup_password(db, "moi", LONG, "Ville ?", "Lyon")
    assert auth.verify_password(db, LONG)
    assert not auth.verify_password(db, "autre mot de passe")


def test_hash_created_by_bcrypt4_still_verifies(db):
    """Hachage produit par bcrypt < 5, qui tronquait silencieusement à 72 octets."""
    raw = LONG.strip().lower().encode("utf-8")
    legacy = bcrypt.hashpw(raw[:72], bcrypt.gensalt(4)).decode()
    db.set_setting("auth_password_hash", "bcrypt:" + legacy)
    db.set_setting("auth_password_salt", "")
    assert auth.verify_password(db, LONG)


def test_long_secret_answer(db):
    auth.setup_password(db, "moi", "court", "Question ?", LONG)
    assert auth.verify_secret_answer(db, LONG.upper())     # insensible à la casse
    assert not auth.verify_secret_answer(db, "mauvaise réponse")
