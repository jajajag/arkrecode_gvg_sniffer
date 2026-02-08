import json
from mitmproxy.script import concurrent
from printer import print_all

query_list = [
    "GuildWarHandler.QueryFullGuildWarData",
    "PVPHandler.QueryPVPData",
    "PVPHandler.QueryRevengeEnemyData",
]

def process(flow):
    if not flow.response:
        return
    if "RouterHandler.ashx" not in flow.request.url:
        return

    try:
        req = json.loads(flow.request.content.decode("utf-8"))
    except Exception:
        return
    if req.get("route") not in query_list:
        return

    try:
        data = json.loads(flow.response.content.decode("utf-8"))
    except Exception:
        return
    
    with open("data.json", "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    #print('Saved data to data.json')
    print_all()

@concurrent
def response(flow):
    process(flow)
