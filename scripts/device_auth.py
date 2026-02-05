import requests
import time

client_id = 'd679d9d3-5dd1-454f-b3dd-53f3a9b909c3'
tenant_id = '1cdfbb46-a98c-40e1-9173-60fda279a56c'
scopes = 'offline_access Calendars.Read Mail.Read Mail.Send User.Read'

# Step 1: Get device code
device_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/devicecode'
response = requests.post(device_url, data={
    'client_id': client_id,
    'scope': scopes,
})

data = response.json()
device_code = data['device_code']

print('='*60)
print('Go to:', data['verification_uri'])
print('Enter code:', data['user_code'])
print('='*60)
print()
print('Waiting for you to sign in...')

# Step 2: Poll for token
token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'

for i in range(120):
    time.sleep(5)
    token_response = requests.post(token_url, data={
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        'client_id': client_id,
        'device_code': device_code,
    })
    token_data = token_response.json()

    if 'refresh_token' in token_data:
        print()
        print('SUCCESS!')
        print()
        print('='*60)
        print('REFRESH TOKEN - Copy this for GitHub secrets:')
        print('='*60)
        print()
        print(token_data['refresh_token'])
        print()
        print('='*60)
        break
    elif token_data.get('error') == 'authorization_pending':
        continue
    else:
        print('Error:', token_data)
        break
