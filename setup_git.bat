@echo off
:: ============================================================
::  setup_git.bat — Initialise le repo Git et pousse sur GitHub
::  Lancer UNE SEULE FOIS depuis le dossier du projet
:: ============================================================

echo.
echo  ====================================================
echo   Finance Tracker — Configuration Git + GitHub
echo  ====================================================
echo.

:: Vérifier que git est installé
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERREUR] Git n'est pas installe sur ce PC.
    echo  Telecharge-le sur : https://git-scm.com/downloads
    pause
    exit /b 1
)

:: Se placer dans le dossier du script
cd /d "%~dp0"
echo  Dossier : %CD%
echo.

:: ── 1. Configurer Git (nom + email) ────────────────────────
git config --global user.name "Moussa Oudihat"
git config --global user.email "moussa.oudihat@gmail.com"
git config --global init.defaultBranch main
echo  [OK] Config git : Moussa Oudihat / moussa.oudihat@gmail.com

:: ── 2. Initialiser le repo ──────────────────────────────────
if exist ".git" (
    echo  [INFO] Repo git deja existant — skip git init
) else (
    git init
    echo  [OK] git init
)

:: ── 3. Ajouter tous les fichiers ────────────────────────────
git add .
echo  [OK] git add .

:: ── 4. Premier commit ────────────────────────────────────────
git commit -m "feat: initial commit — Finance Tracker v3.0"
echo  [OK] Premier commit cree
echo.

:: ── 5. Lier au repo GitHub ──────────────────────────────────
echo  ====================================================
echo   Etape suivante : cree le repo sur GitHub
echo  ====================================================
echo.
echo  1. Va sur : https://github.com/new
echo  2. Nom du repo     : finance-tracker
echo  3. Description     : Application desktop de suivi financier personnel (Python + SQLite)
echo  4. Visibilite      : Public
echo  5. NE PAS cocher   : Add README, .gitignore, license  (deja presents)
echo  6. Clique sur      : Create repository
echo.
echo  Ensuite, reviens ici et appuie sur une touche...
pause

:: ── 6. Connecter et pousser ─────────────────────────────────
git remote add origin https://github.com/MoussaOudihat/finance-tracker.git
git branch -M main
git push -u origin main

echo.
echo  ====================================================
echo   Termine ! Ton code est sur GitHub.
echo   https://github.com/MoussaOudihat/finance-tracker
echo  ====================================================
echo.
pause
