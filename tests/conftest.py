import os
import sys
import tempfile

# Racine du projet importable (database, config, web…)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Logs et données de test hors du dossier data/ réel, et pas d'app web
# construite automatiquement à l'import (les tests créent la leur).
os.environ.setdefault("FINTRACK_DATA_DIR", tempfile.mkdtemp(prefix="fintrack-test-"))
os.environ["FINTRACK_WEB_NO_AUTOAPP"] = "1"
