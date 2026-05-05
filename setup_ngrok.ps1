if (-not (Test-Path "ngrok.exe")) {
    Write-Host "Downloading ngrok..."
    Invoke-WebRequest -Uri "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile "ngrok.zip"
    Write-Host "Extracting ngrok..."
    Expand-Archive -Path "ngrok.zip" -DestinationPath "." -Force
}
Write-Host "Configuring auth token..."
.\ngrok.exe config add-authtoken 3Au3i7OsOxNwprCgHE5CdAMA4Xg_2btouU73MKs2gm1Mkt2QB

Write-Host "Stopping existing ngrok..."
Stop-Process -Name "ngrok" -ErrorAction SilentlyContinue

Write-Host "Starting ngrok..."
Start-Process -FilePath ".\ngrok.exe" -ArgumentList "http 5000" -WindowStyle Hidden

Start-Sleep -Seconds 3

Write-Host "Getting Public URL..."
$tunnels = (Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction SilentlyContinue).tunnels
if ($tunnels) {
    echo $tunnels[0].public_url
} else {
    echo "Failed to retrieve public URL from local API."
}
