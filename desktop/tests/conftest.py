"""Tests de l'application desktop (couche données, synchronisation)."""
import os
import sys
import tempfile

# Dossier de l'app desktop importable (database, config, sync_supabase…)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Logs et données de test hors du dossier data/ réel.
os.environ.setdefault("FINTRACK_DATA_DIR", tempfile.mkdtemp(prefix="fintrack-test-"))
