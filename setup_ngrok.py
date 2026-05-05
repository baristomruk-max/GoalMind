import urllib.request
import zipfile
import os
import subprocess
import time
import json

url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
file_name = "ngrok.zip"

if not os.path.exists("ngrok.exe"):
    print("Downloading ngrok...")
    urllib.request.urlretrieve(url, file_name)

    print("Extracting ngrok...")
    with zipfile.ZipFile(file_name, 'r') as zip_ref:
        zip_ref.extractall(".")

print("Configuring ngrok...")
subprocess.run(["ngrok.exe", "config", "add-authtoken", "3Au3i7OsOxNwprCgHE5CdAMA4Xg_2btouU73MKs2gm1Mkt2QB"], check=True)

print("Starting ngrok...")
# Start hidden
proc = subprocess.Popen(["ngrok.exe", "http", "5000"], creationflags=subprocess.CREATE_NO_WINDOW)

print("Waiting for ngrok to initialize...")
time.sleep(3)

print("Fetching Public URL...")
try:
    req = urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels')
    data = json.loads(req.read().decode('utf-8'))
    print("\nSUCCESS! Public URL:")
    print(data['tunnels'][0]['public_url'])
except Exception as e:
    print("Failed to get URL:", e)
