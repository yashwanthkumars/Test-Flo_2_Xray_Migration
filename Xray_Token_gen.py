import requests
 
AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
 
payload = {
    "client_id": "YOUR_TOKEN",
    "client_secret": "YOUR_TOKEN"
}
 
response = requests.post(AUTH_URL, json=payload)
 
if response.status_code == 200:
    token = response.json()
    print("✅ Xray token:", token)
else:
    print("❌ Auth failed:", response.status_code, response.text)