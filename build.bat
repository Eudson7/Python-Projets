@echo off
rem ============================================================
rem  Gera o executavel do Win Janitor
rem  Requisitos: Python 3.12 instalado (py -3.12 no prompt)
rem  Rode com duplo clique na pasta do projeto.
rem ============================================================
cd /d "%~dp0"

echo [1/3] Instalando dependencias...
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Falhou ao instalar dependencias.
    exit /b 1
)

echo [2/3] Gerando o executavel...
py -3.12 -m PyInstaller win_janitor.spec --noconfirm
if errorlevel 1 (
    echo Falhou ao gerar o executavel.
    exit /b 1
)

echo [3/3] Pronto!
echo.
echo   Executavel: dist\WinJanitor\WinJanitor.exe
echo   Copie a pasta dist\WinJanitor inteira para onde quiser.
echo.
pause
