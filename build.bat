@echo off
chcp 65001 >nul
title Finance Tracker - Build EXE
cd /d "%~dp0"

echo.
echo  ==========================================
echo    Finance Tracker - Creation du .exe
echo  ==========================================
echo.

:: Cherche Python
set PYTHON_CMD=
where python >nul 2>&1 && set PYTHON_CMD=python
if not defined PYTHON_CMD (
    where python3 >nul 2>&1 && set PYTHON_CMD=python3
)
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set PYTHON_CMD=py
)
if not defined PYTHON_CMD (
    echo  ERREUR : Python introuvable dans le PATH.
    pause
    exit /b 1
)

:: Detecter si Python vient du Microsoft Store (incompatible avec PyInstaller)
for /f "delims=" %%P in ('%PYTHON_CMD% -c "import sys; print(sys.executable)"') do set PYEXE=%%P
echo %PYEXE% | findstr /i "WindowsApps" >nul
if not errorlevel 1 (
    echo.
    echo  ==========================================
    echo    ERREUR : Python Microsoft Store detecte
    echo  ==========================================
    echo.
    echo  PyInstaller est INCOMPATIBLE avec le Python
    echo  installe via le Microsoft Store.
    echo.
    echo  SOLUTION :
    echo  1. Desinstallez Python depuis le Microsoft Store
    echo  2. Telechargez Python depuis : https://www.python.org/downloads/
    echo  3. IMPORTANT : cochez "Add Python to PATH"
    echo     ET "Install for all users" pendant l installation
    echo  4. Relancez ce fichier build.bat
    echo.
    echo  Python detecte : %PYEXE%
    echo.
    pause
    exit /b 1
)

echo  Python OK : %PYEXE%

:: Dependances de l'app
echo  Verification des dependances...
%PYTHON_CMD% -c "import customtkinter, matplotlib, openpyxl" >nul 2>&1
if errorlevel 1 (
    %PYTHON_CMD% -m pip install customtkinter matplotlib openpyxl --quiet
)

:: PyInstaller
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo  Installation de PyInstaller...
    %PYTHON_CMD% -m pip install "pyinstaller>=6.0" --quiet
    if errorlevel 1 (
        echo  ERREUR : impossible d installer PyInstaller.
        pause
        exit /b 1
    )
)

:: Nettoyage des anciens builds
echo  Nettoyage...
if exist "build" rmdir /s /q "build"
if exist "dist\Finance Tracker" rmdir /s /q "dist\Finance Tracker"
if exist "Finance Tracker.spec" del /q "Finance Tracker.spec"

echo.
echo  Construction du .exe - quelques minutes...
echo.

%PYTHON_CMD% -m PyInstaller ^
  --onedir ^
  --windowed ^
  --name "Finance Tracker" ^
  --add-data "data\seed_data.sql;data" ^
  --collect-data customtkinter ^
  --collect-data matplotlib ^
  --hidden-import "matplotlib.backends.backend_tkagg" ^
  --hidden-import "matplotlib.backends._backend_tk" ^
  --hidden-import "matplotlib.figure" ^
  --hidden-import "tkinter" ^
  --hidden-import "tkinter.ttk" ^
  --hidden-import "sqlite3" ^
  --hidden-import "reportlab" ^
  --hidden-import "reportlab.lib.pagesizes" ^
  --hidden-import "reportlab.platypus" ^
  --hidden-import "reportlab.lib.styles" ^
  --hidden-import "reportlab.lib.units" ^
  --hidden-import "reportlab.lib.colors" ^
  --hidden-import "smtplib" ^
  --hidden-import "email.mime.multipart" ^
  --hidden-import "email.mime.text" ^
  --hidden-import "csv" ^
  --hidden-import "ui.pages" ^
  --hidden-import "ui.pages.dashboard" ^
  --hidden-import "ui.pages.revenues" ^
  --hidden-import "ui.pages.expenses" ^
  --hidden-import "ui.pages.savings_entry" ^
  --hidden-import "ui.pages.analyses" ^
  --hidden-import "ui.pages.budget" ^
  --hidden-import "ui.pages.objectifs" ^
  --hidden-import "ui.pages.patrimoine" ^
  --hidden-import "ui.pages.historique" ^
  --hidden-import "ui.pages.settings" ^
  --hidden-import "ui.pages.recommandations" ^
  --hidden-import "ui.pages.projection" ^
  --noconfirm ^
  main.py

set BUILD_RESULT=%errorlevel%

if %BUILD_RESULT% neq 0 (
    echo.
    echo  ERREUR lors du build.
    echo  Pour voir le detail, supprimez la ligne --windowed et relancez.
    echo.
    pause
    exit /b 1
)

:: Creer le dossier data si absent
if not exist "dist\Finance Tracker\data" mkdir "dist\Finance Tracker\data"

echo.
echo  ==========================================
echo    Build termine avec succes !
echo.
echo    Executable :
echo    dist\Finance Tracker\Finance Tracker.exe
echo.
echo    Pour distribuer : copiez le dossier complet
echo    dist\Finance Tracker  sur le PC cible.
echo    Aucune installation Python necessaire.
echo  ==========================================
echo.
pause
