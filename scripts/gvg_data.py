from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.analyzer import analyze_gvg, analyze_gvg_defence, analyze_pvp_equips
from utils.exporter import export_report
from utils.login_helper import (
    choose_account, load_accounts, login_account, send,
)
from utils.printer import print_report


def query_guild_summary(aid, session_id, gid):
    data = send({
        'data': {
            'GuildID': gid,
            'AID': aid,
            'SessionID': session_id,
        },
        'route': 'GuildHandler.QueryPartialGuildDataForGuildWar',
    })
    return analyze_gvg(data, aid, session_id, save_csv=False)


def collect_gvg_data(aid, session_id, cuid, week):
    try:
        print('正在更新装备数据...')
        data = send({
            'data': {
                'Week': week,
                'AID': aid,
                'SessionID': session_id,
            },
            'route': 'PVPHandler.GetPVPRankList',
        })
    except Exception:
        print('查询失败：排名可能在结算中！')
        return
    analyze_pvp_equips(data)
    print('装备数据更新完成！')

    try:
        rank_data = send({
            'data': {'AID': aid, 'SessionID': session_id},
            'route': 'GuildWarHandler.QueryNowGuildWarRank',
        })
    except Exception:
        print('查询失败：未加入佣兵团！')
        return

    guilds = rank_data['GuildWarCampaignInfoList']
    count = input('请输入要查询的前排团战防守（最多前20）：').strip()
    count = min(int(count), 20) if count.isdigit() else 20
    for index, guild in enumerate(guilds[:count], 1):
        print(f'正在查询第{index}名佣兵团的防守数据...')
        gid = guild['GuildSubInfo']['_id']['$oid']
        rows = query_guild_summary(aid, session_id, gid)
        analyze_gvg_defence(aid, session_id, cuid, rows)
    print('防守数据查询完成！')


def query_gvg_defence(aid, session_id):
    try:
        data = send({
            'data': {'AID': aid, 'SessionID': session_id},
            'route': 'GuildWarHandler.QueryFullGuildWarData',
        })
    except Exception:
        print('查询失败：未加入佣兵团或未开启团战！')
        return
    print_report(data)
    export_report(data)


def query_pvp_defence(aid, session_id):
    if input('此功能将导致JJC进场，是否继续：（Y/n）').strip().lower() == 'n':
        return
    try:
        print('正在查询JJC信息...')
        data = send({
            'data': {'AID': aid, 'SessionID': session_id},
            'route': 'PVPHandler.QueryPVPData',
        })
    except Exception:
        print('JJC查询失败！')
        return
    print_report(data)
    revenge_logs = [
        log for log in data['PVPData']['PVPLogList']
        if log['CanRevengeBattle']
    ]
    if not revenge_logs:
        print('没有可复仇的对象！')
        return
    for index, log in enumerate(revenge_logs, 1):
        print(f'-----可复仇对象 {index}/{len(revenge_logs)}-----')
        enemy_cuid = log['PlayerInfo']['CUID']
        try:
            print_report(send({
                'data': {
                    'EnemyCUID': enemy_cuid,
                    'LogID': log['_id']['$oid'],
                    'AID': aid,
                    'SessionID': session_id,
                },
                'route': 'PVPHandler.QueryRevengeEnemyData',
            }))
        except Exception:
            print(f'复仇查询失败：{enemy_cuid}')


def login_context():
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    print('登录中...')
    data = login_account(accounts, acc_idx)
    print('登录成功！')
    return data


def main():
    data = login_context()
    collect_gvg_data(
        data['Info']['_id']['$oid'],
        data['SessionID'],
        data['Info']['CUID'],
        data['PVPData']['PVPRankInfo']['RankWeek'],
    )


if __name__ == '__main__':
    main()
