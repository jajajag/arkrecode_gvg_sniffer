import json

windows_url = 'https://sadpki-portal-v2.ebuajk.com/api/v2/token/access'
android_url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'

def request(flow):
    url = flow.request.pretty_url
    if url == windows_url:
        headers = flow.request.headers
        token = headers['Authorization'].replace('Bearer', '').strip()
        device_id = headers['DeviceId']
    elif url == android_url:
        try:
            data = json.loads(flow.request.get_text())
            if data['data']['IsNewSDK']:
                return
            token = data['data']['Token']
            device_id = data['data']['DeviceID']
        except:
            return
    else:
        return

    print('Token:', token)
    print('DeviceId:', device_id)
