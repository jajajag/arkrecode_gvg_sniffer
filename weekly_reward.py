import csv
import json
import random
import requests
import threading
import time

flag = True

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'

headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

payload = {
    "data" : {
        "RewardQuestInfos" : [{"ID" : "GuildCheckIn", "Index" : 0}],
        "CommodityID" : "",
        "AID" : "",
        "SessionID" : ""
    },
    "route" : "QuestHandler.RewardQuest"
}

def process(flow):
    global flag, payload
    if not flag:
        return
    if not flow.response:
        return
    if 'RouterHandler.ashx' not in flow.request.url:
        return

    try:
        req = json.loads(flow.request.content.decode('utf-8'))
    except Exception:
        return
    if req['route'] != 'GuildWarHandler.QueryFullGuildWarData':
        return

    try:
        data = json.loads(flow.response.content.decode('utf-8'))
    except Exception:
        return

    flag = False

    # Modify global payload
    payload['data']['AID'] = req['data']['AID']
    payload['data']['SessionID'] = req['data']['SessionID']

    threading.Thread(target=reward, daemon=True).start()

def response(flow):
    process(flow)

def reward(repeat=140):
    for i in range(repeat):
        try:
            time.sleep(random.uniform(1, 2))
            resp = requests.post(url, json=payload, headers=headers)
            resp.encoding = 'utf-8'
            data = resp.json()
            print(f'{i + 1}: {data}')
        except Exception as e:
            print(f"Error: {e}")
    print(f'刷完{repeat}次了！')
