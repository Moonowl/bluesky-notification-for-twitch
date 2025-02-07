import requests

BLUESKY_HANDLE = ''  # Replace with your Bluesky handle
BLUESKY_PASSWORD = ''  # Replace with your Bluesky password

response = requests.post(
    'https://bsky.social/xrpc/com.atproto.server.createSession',
    json={
        'identifier': BLUESKY_HANDLE,
        'password': BLUESKY_PASSWORD,
    }
)
response.raise_for_status()
session = response.json()

access_token = session['accessJwt']
refresh_token = session['refreshJwt']

print(f'Access Token: {access_token}')
print(f'Refresh Token: {refresh_token}')
