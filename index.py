import requests
import asyncio
import json
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter, Retry
from twitchio.ext import commands

CONFIG_FILE = 'config.json'
NOTIFICATIONS_FILE = 'notifications.json'

# Load config from a JSON file if it exists
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save config to a JSON file
def save_config(config):
    with open(CONFIG_FILE, 'w') as file:
        json.dump(config, file)

# Prompt user for config if not already saved
def get_config():
    config = load_config()
    if not config:
        config = {
            'TWITCH_CLIENT_ID': input('Enter your Twitch Client ID: '),
            'TWITCH_CLIENT_SECRET': input('Enter your Twitch Client Secret: '),
            'TWITCH_OAUTH_TOKEN': input('Enter your Twitch OAuth Token: '),
            'TWITCH_REFRESH_TOKEN': input('Enter your Twitch Refresh Token: '),
            'BLUESKY_HANDLE': input('Enter your Bluesky Handle: '),
            'BLUESKY_PASSWORD': input('Enter your Bluesky Password: '),
            'initial_channels': input('Enter your initial Twitch channel (comma separated): ').split(','),
            'whitelisted_users': input('Enter whitelisted users (comma separated): ').split(',')
        }
        save_config(config)
    return config

config = get_config()

TWITCH_CLIENT_ID = config['TWITCH_CLIENT_ID']
TWITCH_CLIENT_SECRET = config['TWITCH_CLIENT_SECRET']
TWITCH_OAUTH_TOKEN = config['TWITCH_OAUTH_TOKEN']
TWITCH_REFRESH_TOKEN = config['TWITCH_REFRESH_TOKEN']
BLUESKY_HANDLE = config['BLUESKY_HANDLE']
BLUESKY_PASSWORD = config['BLUESKY_PASSWORD']
initial_channels = config['initial_channels']
whitelisted_users = config['whitelisted_users']

CHECK_INTERVAL = 300  # Check every 5 minutes
MONTHLY_POST_INTERVAL = 30 * 24 * 60 * 60  # 30 days in seconds

# In-memory dictionary to store user IDs and custom messages
user_notifications = {}
live_notifications = {}  # Dictionary to track live stream status

# Load notifications from a JSON file if it exists
def load_notifications():
    try:
        with open(NOTIFICATIONS_FILE, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save notifications to a JSON file
def save_notifications():
    with open(NOTIFICATIONS_FILE, 'w') as file:
        json.dump(user_notifications, file)

# Function to refresh Twitch tokens
def refresh_twitch_tokens():
    global TWITCH_OAUTH_TOKEN, TWITCH_REFRESH_TOKEN
    response = requests.post(
        'https://id.twitch.tv/oauth2/token',
        params={
            'grant_type': 'refresh_token',
            'refresh_token': TWITCH_REFRESH_TOKEN,
            'client_id': TWITCH_CLIENT_ID,
            'client_secret': TWITCH_CLIENT_SECRET,
        }
    )
    response.raise_for_status()
    tokens = response.json()
    TWITCH_OAUTH_TOKEN = tokens['access_token']
    TWITCH_REFRESH_TOKEN = tokens['refresh_token']

# Function to refresh Bluesky tokens
def refresh_bluesky_tokens():
    global BLUESKY_ACCESS_TOKEN, BLUESKY_REFRESH_TOKEN
    response = requests.post(
        'https://bsky.social/xrpc/com.atproto.server.createSession',
        json={
            'identifier': BLUESKY_HANDLE,
            'password': BLUESKY_PASSWORD,
        }
    )
    response.raise_for_status()
    session = response.json()
    BLUESKY_ACCESS_TOKEN = session['accessJwt']
    BLUESKY_REFRESH_TOKEN = session['refreshJwt']

# Initialize tokens on startup
refresh_twitch_tokens()
refresh_bluesky_tokens()

# Initialize the bot
bot = commands.Bot(
    token=TWITCH_OAUTH_TOKEN,
    prefix='!',
    initial_channels=initial_channels  # Use the initial channels from config
)

# Command to add a Twitch channel and custom message to the notification list
@bot.command(name='addnotification')
async def add_notification(ctx: commands.Context):
    if ctx.author.name not in whitelisted_users:
        await ctx.send("You are not authorized to use this command.")
        return
    parts = ctx.message.content.split(' ', 2)
    if len(parts) < 2:
        await ctx.send('Usage: !addnotification <channel_name> [custom_message]')
        return
    channel = parts[1]
    twitch_link = f'https://www.twitch.tv/{channel}'
    custom_message = parts[2] if len(parts) == 3 else f'@{channel} is live: {twitch_link}'
    user_id = get_user_id(channel)
    if user_id:
        user_notifications[user_id] = f'{custom_message} {twitch_link}'
        save_notifications()
        await ctx.send(f'Notification added for channel: {channel} with message: "{custom_message} {twitch_link}"')
    else:
        await ctx.send(f'Unable to find Twitch user: {channel}')

# Command to post a test message to Bluesky
@bot.command(name='testpost')
async def test_post(ctx: commands.Context):
    if ctx.author.name not in whitelisted_users:
        await ctx.send("You are not authorized to use this command.")
        return
    message = "This is a test post from the bot."
    if post_to_bluesky(message):
        await ctx.send(f'Test post successful: {message}')
    else:
        await ctx.send('Failed to post test message to Bluesky.')

def get_user_id(username):
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
        'Authorization': f'Bearer {TWITCH_OAUTH_TOKEN}',
    }
    response = requests.get(f'https://api.twitch.tv/helix/users?login={username}', headers=headers)
    data = response.json()
    if data.get('data'):
        return data['data'][0]['id']
    return None

def is_live_on_twitch(user_id):
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
        'Authorization': f'Bearer {TWITCH_OAUTH_TOKEN}',
    }
    response = requests.get(f'https://api.twitch.tv/helix/streams?user_id={user_id}', headers=headers)
    data = response.json()
    print(f'Twitch API response: {data}')  # Debugging line
    if data.get('data'):
        return len(data['data']) > 0
    return False

def post_to_bluesky(message):
    global BLUESKY_ACCESS_TOKEN
    headers = {
        'Authorization': f'Bearer {BLUESKY_ACCESS_TOKEN}',
        'Content-Type': 'application/json',
    }
    payload = {
        'collection': 'app.bsky.feed.post',
        'repo': 'did:plc:5i7f254otzzyqautfeqa3p4u',  # Replace with your actual Bluesky DID
        'record': {
            '$type': 'app.bsky.feed.post',
            'text': message,
            'createdAt': datetime.utcnow().isoformat() + 'Z',
        }
    }
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    try:
        print(f'Posting to Bluesky: {json.dumps(payload, indent=2)}')  # Debugging line
        response = session.post('https://bsky.social/xrpc/com.atproto.repo.createRecord', headers=headers, json=payload, timeout=10)
        print(f'Bluesky response status: {response.status_code}')  # Debugging line
        print(f'Bluesky response body: {response.text}')  # Debugging line
        if response.ok:
            print('Posted to Bluesky:', response.json())
            return True
        else:
            print('Error posting to Bluesky:', response.json())
            if response.status_code == 401:  # Unauthorized error
                refresh_bluesky_tokens()  # Refresh tokens and retry
                return post_to_bluesky(message)
            return False
    except requests.exceptions.RequestException as e:
        print(f'Error posting to Bluesky: {e}')
        return False

async def check_live_status():
    while True:
        for user_id, custom_message in user_notifications.items():
            if is_live_on_twitch(user_id):
                if not live_notifications.get(user_id):
                    print(f'User {user_id} is live on Twitch!')
                    post_to_bluesky(custom_message)
                    live_notifications[user_id] = True
            else:
                live_notifications[user_id] = False
        await asyncio.sleep(CHECK_INTERVAL)

async def post_monthly_summary():
    while True:
        await asyncio.sleep(MONTHLY_POST_INTERVAL)
        if user_notifications:
            summary_message = "Here are the channels we're tracking this month:\n"
            for user_id, message in user_notifications.items():
                channel = message.split(' ')[0].lstrip('@')
                summary_message += f"- @{channel} (https://www.twitch.tv/{channel})\n"
            post_to_bluesky(summary_message)

# Load the notifications on startup
user_notifications = load_notifications()

# Run the bot and start checking live status and posting monthly summaries
bot.loop.create_task(check_live_status())
bot.loop.create_task(post_monthly_summary())
bot.run()