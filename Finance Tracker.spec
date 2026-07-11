# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# Note : data/seed_data.sql est exclu (données personnelles, non versionné).
# L'app démarre proprement sans ce fichier (base vide au premier lancement).
datas = collect_data_files('customtkinter')
datas += collect_data_files('matplotlib')
datas += [('VERSION', '.')]          # version lue au runtime par config.py
datas += [('fintrack_256.png', '.')]  # logo affiché dans sidebar et login
datas += [('fintrack.ico', '.')]      # icône fenêtre / barre des tâches


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # libs externes
        'matplotlib.backends.backend_tkagg', 'matplotlib.backends._backend_tk',
        'matplotlib.figure', 'tkinter', 'tkinter.ttk', 'sqlite3',
        'reportlab', 'reportlab.lib.pagesizes', 'reportlab.platypus',
        'reportlab.lib.styles', 'reportlab.lib.units', 'reportlab.lib.colors',
        'openpyxl', 'openpyxl.styles',
        'smtplib', 'email.mime.multipart', 'email.mime.text', 'csv',
        # IA
        'google.genai', 'google.genai.types', 'utils_ai',
        # authentification & sync
        'auth', 'ui.login', 'sync_supabase', 'bcrypt',
        'supabase', 'httpx', 'httpcore', 'anyio', 'sniffio',
        'gotrue', 'postgrest', 'realtime', 'storage3',
        # pages chargées dynamiquement via importlib (Phase 2 lazy-load)
        'ui.pages',
        'ui.pages.dashboard', 'ui.pages.revenues', 'ui.pages.expenses',
        'ui.pages.savings_entry', 'ui.pages.analyses', 'ui.pages.budget',
        'ui.pages.objectifs', 'ui.pages.patrimoine', 'ui.pages.historique',
        'ui.pages.settings', 'ui.pages.recommandations', 'ui.pages.projection',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Fintrack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='fintrack.ico',   # généré par generate_icon.py
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Fintrack',
)
