from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.analyzer import analyze_gvg, analyze_gvg_defence, analyze_pvp_equips
from utils.battle_support import query_player_card
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


def search_friend(aid, session_id, text):
    key = 'CUID' if text.isdigit() else 'Name'
    return send({
        'data': {
            key: text,
            'AID': aid,
            'SessionID': session_id,
        },
        'route': 'FriendHandler.SearchFriendList',
    }).get('FriendInfos') or []


def choose_searched_player(players):
    if not players:
        print('没有搜索到玩家！')
        return None
    print('[选择玩家]')
    for index, player in enumerate(players, 1):
        guild = player.get('GuildSubInfo', {}).get('Name', '')
        guild_text = f'，公会：{guild}' if guild else ''
        print(
            f'{index}. {player.get("Name", "")}'
            f'（UID：{player.get("CUID", "")}，LV{player.get("LV", "")}'
            f'{guild_text}）'
        )
    choice = input('请选择玩家编号：').strip()
    if not choice and len(players) == 1:
        return players[0]
    if choice.isdigit() and 1 <= int(choice) <= len(players):
        return players[int(choice) - 1]
    print('无效选择！')
    return None


def save_player_card_pvp_equips(data):
    if not isinstance(data, dict):
        print('未找到可保存的JJC防守装备。')
        return
    pvp_info = data.get('PVPInfo')
    support_data = data.get('BattleSupportData')
    player_info = (support_data or {}).get('PlayerInfo') or data.get('PlayerInfo')
    defence_team = (pvp_info or {}).get('DefenceTeam')
    if not player_info or not defence_team:
        print('未找到可保存的JJC防守装备。')
        return
    analyze_pvp_equips({
        'PVPRankInfoList': [{
            'PlayerInfo': player_info,
            'PVPInfo': pvp_info,
        }],
    })


def query_player_pvp_info(aid, session_id):
    text = input('请输入玩家名称或UID：').strip()
    if not text:
        return
    if text.isdigit():
        cuid = int(text)
    else:
        try:
            players = search_friend(aid, session_id, text)
        except Exception:
            print('搜索玩家失败！')
            return
        player = choose_searched_player(players)
        if not player:
            return
        cuid = player['CUID']
    try:
        print('正在查询玩家JJC信息...')
        data = query_player_card(aid, session_id, cuid)
    except Exception:
        print('玩家JJC查询失败！')
        return
    print_report(data)
    save_player_card_pvp_equips(data)


def query_pvp_defence(aid, session_id):
    if input('此功能将导致JJC进场，是否继续：（y/N）').strip().lower() != 'y':
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
