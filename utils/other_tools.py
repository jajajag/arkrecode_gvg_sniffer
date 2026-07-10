from utils.helper import data_path


DATA_DB = data_path('data.db')


def require_data_db():
    if DATA_DB.is_file():
        return True
    print('尚未生成 data/data.db，请先使用 1「查询前排团战数据」。')
    return False


def run_hidden_tools(aid, session_id):
    from scripts import gvg_data, gvg_speed, pvp_speed

    actions = {
        '1': ('查询对手GVG信息',
              lambda: gvg_data.query_gvg_defence(aid, session_id)),
        '2': ('查询对手JJC信息',
              lambda: gvg_data.query_pvp_defence(aid, session_id)),
        '3': ('查询玩家JJC信息',
              lambda: gvg_data.query_player_pvp_info(aid, session_id)),
        '4': ('查询玩家速度', None),
        '5': ('团战测速', lambda: gvg_speed.main([])),
    }
    while True:
        print('[隐藏工具集]')
        print('0. 返回小众变态工具集')
        for key, (label, _) in actions.items():
            print(f'{key}. {label}')
        choice = input('> ').strip()
        if choice == '0':
            return
        if choice == '4':
            if require_data_db():
                name = input('请输入玩家名称：').strip()
                if name:
                    pvp_speed.main([name])
            continue
        action = actions.get(choice)
        if action:
            action[1]()


def run_other_tools(login_data, accounts=None, acc_idx=None):
    from scripts import (
        claim_rewards, db_to_csv, gvg_data, gvg_defence, gvg_summary,
        pass_scene, pvp_week_reward, vote,
    )

    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    cuid = login_data['Info']['CUID']
    week = login_data['PVPData']['PVPRankInfo']['RankWeek']

    while True:
        print('[小众变态工具集]')
        print('0. 返回主界面')
        print('1. 查询前排团战数据')
        print('2. 查询前排团战作业')
        print('3. 查询前排团战错题本')
        print('4. 领取全部成就')
        print('5. 领取全部邮箱')
        print('6. 一键通关主线爬塔元素讨伐')
        print('7. JJC定时进场')
        print('8. 投票')
        print('9. 团战数据转表格')
        choice = input('> ').strip()

        if choice == '0':
            return
        if choice == '114514':
            run_hidden_tools(aid, session_id)
        elif choice == '1':
            gvg_data.collect_gvg_data(aid, session_id, cuid, week)
        elif choice == '2':
            if not require_data_db():
                continue
            roles = [
                input(f'请输入防守角色{i}：').strip()
                for i in range(1, 4)
            ]
            if all(roles):
                gvg_defence.main(roles)
        elif choice == '3':
            if not require_data_db():
                continue
            guild = input('请输入佣兵团名称：').strip()
            if guild:
                gvg_summary.main([guild])
        elif choice == '4':
            claim_rewards.main(login_data)
        elif choice == '5':
            claim_rewards.claim_all_mails(login_data)
        elif choice == '6':
            pass_scene.main(login_data)
        elif choice == '7':
            pvp_week_reward.main(accounts, acc_idx)
        elif choice == '8':
            vote.prompt_and_vote(login_data)
        elif choice == '9':
            if require_data_db():
                db_to_csv.db_to_csv()
