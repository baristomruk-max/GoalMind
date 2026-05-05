@echo off
chcp 65001 > nul
title Football Data App - Tahmin Motoru
color 0A

echo ===================================================
echo     FOOTBALL DATA APP BASLATILIYOR...
echo ===================================================
echo/

:: Sunucunun acilmasi icin kisa bir bekleme ve tarayiciyi tetikleme
start "" http://127.0.0.1:5000

:: Python uygulamasini baslat
echo Lutfen bu siyah pencereyi kapatmayin. Sunucu calisiyor...
echo/
python app.py

pause
