@echo off
title Finance Tracker v3.0
color 0F

:: Se placer dans le dossier du projet DES LE DEBUT
cd /d "%~dp0"

echo.
echo  ==========================================
echo    Finance Tracker  v3.0
echo  ==========================================
echo.

:: ── Cherche Python (python / python3 / py) ──
set PYTHON_CMD=
where python >nul 2>&1 && set PYTHON_CMD=python
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set PYTHON_CMD=python3
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set PYTHON_CMD=py
)

if not defined PYTHON_CMD (
    echo  ERREUR : Python n'est pas installe ou pas dans le PATH.
    echo.
    echo  Telechargez Python depuis python.org :
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT : cochez "Add Python to PATH"
    echo  pendant l'installation !
    echo.
    pause
    exit /b 1
)

:: ── Detecter Python Microsoft Store (avertissement uniquement) ──
for /f "delims=" %%P in ('%PYTHON_CMD% -c "import sys; print(sys.executable)"') do set PYEXE=%%P
echo %PYEXE% | findstr /i "WindowsApps" >nul
if not errorlevel 1 (
    echo  [INFO] Python Microsoft Store detecte.
    echo  L'application fonctionne, mais le build .exe est impossible
    echo  avec cette version. Pour le build, installez Python depuis :
    echo  https://www.python.org/downloads/
    echo.
)

echo  Python : %PYEXE%
echo.

:: ── Verification des dependances ──
%PYTHON_CMD% -c "import customtkinter, matplotlib, reportlab" >nul 2>&1
if errorlevel 1 (
    echo  Installation des dependances (premiere fois uniquement)...
    echo  Peut prendre 1-2 minutes...
    echo.
    %PYTHON_CMD% -m pip install customtkinter matplotlib reportlab --quiet 2>&1
    if errorlevel 1 (
        echo.
        echo  Erreur lors de l'installation.
        echo  Essayez : clic droit sur run.bat ^> Executer en tant qu'administrateur
        echo.
        pause
        exit /b 1
    )
    echo  Dependances installees avec succes.
    echo.
) else (
    echo  Dependances OK.
    echo.
)

echo  Lancement de Finance Tracker...
echo.

%PYTHON_CMD% main.py

if errorlevel 1 (
    echo.
    echo  ==========================================
    echo    ERREUR au lancement
    echo  ==========================================
    echo  Copiez le message d'erreur ci-dessus
    echo  et transmettez-le pour obtenir de l'aide.
    echo.
    pause
)
