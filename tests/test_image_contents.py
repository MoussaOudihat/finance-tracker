"""L'image Docker n'embarque qu'une partie des modules (voir Dockerfile).
Vérifie que le code web n'importe rien d'autre — sinon l'image plante au
premier usage (ex. cloud_auth -> secrets_vault, absent de l'image)."""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _copied_paths() -> list[str]:
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    paths = []
    for line in dockerfile.splitlines():
        m = re.match(r"^COPY (?!--from)(.+) \./", line.strip())
        if m:
            paths += [p for p in m.group(1).split() if p != "requirements-web.txt"]
    return paths


def test_web_modules_import_with_image_files_only(tmp_path):
    paths = _copied_paths()
    assert "database.py" in paths and "web/" in paths
    for p in paths:
        src = os.path.join(ROOT, p)
        if os.path.isdir(src):
            shutil.copytree(src, tmp_path / p.rstrip("/"),
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, tmp_path / p)
    env = dict(os.environ, FINTRACK_WEB_NO_AUTOAPP="1",
               FINTRACK_DATA_DIR=str(tmp_path / "data"))
    # -I ignore PYTHONPATH et le dossier courant ; on n'ajoute que le dossier
    # temporaire : seuls les fichiers copiés dans l'image sont importables.
    code = (f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
            "import web.main, cloud_auth, sync_supabase; print('ok')")
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
