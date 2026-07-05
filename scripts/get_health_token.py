"""
One-time script to get Google Health API OAuth tokens.
Run locally: python scripts/get_health_token.py

Steps:
1. Opens the auth URL in your browser
2. You log in with skhandwala1@gmail.com (your Fitbit/health account)
3. You're redirected to https://www.google.com?code=...
4. Paste that full redirect URL here
5. Script exchanges code for tokens and saves them to diskcache
"""

import json
import sys
import time
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs

import requests

# --- Fill these in from your GCP credentials ---
CLIENT_ID = input("Client ID: ").strip()
CLIENT_SECRET = input("Client Secret: ").strip()
# ------------------------------------------------

REDIRECT_URI = "https://www.google.com"
SCOPES = " ".join([
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
])

auth_params = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPES,
    "access_type": "offline",
    "prompt": "consent",  # forces refresh_token to be returned every time
}

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(auth_params)

print("\n=== Step 1: Open this URL in your browser and log in with skhandwala1@gmail.com ===")
print(auth_url)
print()

try:
    webbrowser.open(auth_url)
    print("(Tried to open browser automatically)")
except Exception:
    print("(Open the URL manually)")

print("\n=== Step 2: After authorizing, paste the full redirect URL (https://www.google.com?code=...) ===")
redirect_url = input("Redirect URL: ").strip()

parsed = urlparse(redirect_url)
code = parse_qs(parsed.query).get("code", [None])[0]
if not code:
    print("ERROR: Could not extract code from URL")
    sys.exit(1)

print("\n=== Step 3: Exchanging code for tokens... ===")
resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    },
)
resp.raise_for_status()
tokens = resp.json()

if "refresh_token" not in tokens:
    print("ERROR: No refresh_token in response. Make sure prompt=consent and the account is a test user.")
    print(json.dumps(tokens, indent=2))
    sys.exit(1)

token_data = {
    "access_token": tokens["access_token"],
    "refresh_token": tokens["refresh_token"],
    "expires_at": time.time() + tokens.get("expires_in", 3600),
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
}

print("\n=== Tokens obtained! ===")
print(f"access_token: {token_data['access_token'][:20]}...")
print(f"refresh_token: {token_data['refresh_token'][:20]}...")

# Save locally so you can copy to VM
import os
out_path = os.path.join(os.path.dirname(__file__), "health_token.json")
with open(out_path, "w") as f:
    json.dump(token_data, f, indent=2)
print(f"\nSaved to {out_path}")
print("\n=== Next: store on VM ===")
print("Run this in the browser SSH terminal on the VM:")
print()
print("python3 -c \"")
print("import diskcache, json, time")
print("token = json.loads('''")
print(json.dumps(token_data, indent=2))
print("''')")
print("c = diskcache.Cache('/opt/nutrition-bot/.cache')")
print("c['health_api_token'] = token")
print("print('Token stored:', c.get('health_api_token')['access_token'][:20])")
print("\"")
