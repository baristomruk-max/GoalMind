@echo off
title Football Data App
echo.
echo  ==========================================
echo    FOOTBALL DATA PREDICTOR v3.0
echo    with AI Agent System (CrewAI + Groq)
echo  ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Lutfen Python yukleyin ve PATH'e ekleyin.
    pause
    exit /b
)

echo [OK] Python bulundu.

REM .env dosyasinda ENABLE_BACKGROUND_TASKS var mi kontrol et
findstr /C:"ENABLE_BACKGROUND_TASKS=true" .env >nul 2>&1
if errorlevel 1 (
    echo.
    echo [INFO] Arka plan gorevleri aktif degil.
    echo [INFO] AI Agent'lar sadece manuel tetiklenebilir.
    echo.
)

echo.
echo  Secenekler:
echo  ------------------------------------------
echo   [1] Web Modu (Tarayici) - AI Agent AKTIF
echo   [2] Web Modu (Tarayici) - AI Agent PASIF
echo   [3] AI Agent Test (Hizli Tanilama)
echo   [4] AI Agent Tam Rutin
echo  ------------------------------------------
echo.

set /p choice="Seciminiz (1-4): "

if "%choice%"=="1" goto web_active
if "%choice%"=="2" goto web_passive
if "%choice%"=="3" goto ai_diagnostic
if "%choice%"=="4" goto ai_full
goto web_active

:web_active
echo.
echo [BASLAT] Web modu + AI Agent aktif...
echo.

REM ENABLE_BACKGROUND_TASKS=true ekle (yoksa)
findstr /C:"ENABLE_BACKGROUND_TASKS=true" .env >nul 2>&1
if errorlevel 1 (
    echo ENABLE_BACKGROUND_TASKS=true>> .env
    echo [OK] ENABLE_BACKGROUND_TASKS=true eklendi.
)

start http://127.0.0.1:5000
python app.py
goto end

:web_passive
echo.
echo [BASLAT] Web modu - AI Agent pasif...
echo.
start http://127.0.0.1:5000
set ENABLE_BACKGROUND_TASKS=false
python app.py
goto end

:ai_diagnostic
echo.
echo [BASLAT] AI Agent hizli tanilama...
echo.
python ai_agents.py --mode diagnostic
echo.
pause
goto end

:ai_full
echo.
echo [BASLAT] AI Agent tam rutin...
echo.
python ai_agents.py --mode full
echo.
pause
goto end

:end
pause
