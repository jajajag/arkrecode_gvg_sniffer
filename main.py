import json
import threading
from utils.analyzer import analyze_hits
from utils.printer import print_report

query_list = [
    "GuildWarHandler.QueryFullGuildWarData", # 团战数据
    "PVPHandler.QueryPVPData", # JJC数据
    "PVPHandler.QueryRevengeEnemyData", # 复仇数据
    "AccountHandler.QueryPlayerCardData", # 好友JJC和辅助团员数据
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

    # 进佣兵团则进行团战总结，否则打印PVP数据
    if req.get("route") == "GuildWarHandler.QueryFullGuildWarData":
        threading.Thread(target=analyze_hits, 
                         args=(data, req['data']['AID'], 
                               req['data']['SessionID'],),
                         daemon=True).start()
    else:
        threading.Thread(target=print_report, args=(data,), daemon=True).start()

def response(flow):
    process(flow)
