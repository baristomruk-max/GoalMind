@echo off
echo ---------------------------------------------------
echo Football Data - Uzaktan Erisim (Ngrok) Kurulumu
echo ---------------------------------------------------

if not exist ngrok.exe (
    echo [1/3] Ngrok indiriliyor...
    curl.exe -s -L -o ngrok.zip "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    echo [2/3] Zip'ten cikariliyor...
    tar -xf ngrok.zip
    del ngrok.zip
) else (
    echo [1/3] Ngrok zaten mevcut.
    echo [2/3] Kurulum adimi atlandi.
)

echo [3/3] Güvenlik Token'i ayarlanıyor...
ngrok.exe config add-authtoken 3Au3i7OsOxNwprCgHE5CdAMA4Xg_2btouU73MKs2gm1Mkt2QB

echo.
echo ===================================================
echo Ngrok tüneli baslatiliyor...
echo Ekranda cikan 'Forwarding' linkini (https://...)
echo cep telefonunuzdan acabilirsiniz.
echo Bu pencereyi kapattiginizda erisim kesilir!
echo ===================================================
echo.
ngrok.exe http 5000
pause
