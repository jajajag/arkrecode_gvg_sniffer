from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from toolkit import (  # noqa: E402
    choose_account,
    get_login_version,
    load_accounts,
    run_bulletin,
    run_login,
    send,
)


BATCH_SIZE = 10


def iter_finished_unrewarded_quests(node):
    if isinstance(node, dict):
        if node.get('IsFinish') is True and node.get('IsRewarded') is False:
            quest_id = (
                node.get('StaticID')
                or node.get('ID')
                or node.get('QuestStaticID')
            )
            if quest_id:
                yield quest_id
        for value in node.values():
            yield from iter_finished_unrewarded_quests(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_finished_unrewarded_quests(item)


def unique_in_order(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def login(accounts, acc_idx):
    bulletin = run_bulletin()
    version = get_login_version(bulletin)
    return run_login(accounts, acc_idx, version)


def claim_rewards(login_data, quest_ids):
    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    total = len(quest_ids)

    for batch_no, batch_ids in enumerate(chunks(quest_ids, BATCH_SIZE), 1):
        print(f'第 {batch_no} 批领取奖励 list：{batch_ids}')
        payload = {
            'route': 'QuestHandler.RewardQuest',
            'data': {
                'RewardQuestInfos': [
                    {'ID': quest_id, 'Index': 0}
                    for quest_id in batch_ids
                ],
                'AID': aid,
                'SessionID': session_id,
            },
        }
        send(payload)
        start = (batch_no - 1) * BATCH_SIZE + 1
        end = start + len(batch_ids) - 1
        print(f'已领取第 {batch_no} 批：{start}-{end}/{total}')


def main():
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')

    login_data = login(accounts, acc_idx)
    quest_ids = unique_in_order(iter_finished_unrewarded_quests(login_data))
    if not quest_ids:
        print('没有找到已完成但未领取的任务。')
        return

    print(f'找到 {len(quest_ids)} 个已完成但未领取的任务。')
    claim_rewards(login_data, quest_ids)
    print('任务奖励领取完成。')


if __name__ == '__main__':
    main()
