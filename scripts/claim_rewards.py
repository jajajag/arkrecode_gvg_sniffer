from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.login_helper import (  # noqa: E402
    choose_account, load_accounts, login_account, send,
)


QUEST_BATCH_SIZE = 10
MAIL_BATCH_SIZE = 20


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


def oid(value):
    if isinstance(value, dict):
        return value.get('$oid')
    return value


def claim_quest_rewards(login_data, quest_ids):
    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    total = len(quest_ids)

    for batch_no, batch_ids in enumerate(chunks(quest_ids, QUEST_BATCH_SIZE), 1):
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
        start = (batch_no - 1) * QUEST_BATCH_SIZE + 1
        end = start + len(batch_ids) - 1
        print(f'已领取第 {batch_no} 批：{start}-{end}/{total}')


def query_mails(aid, session_id):
    data = send({
        'route': 'MailHandler.QueryNewestMails',
        'data': {
            'MailID': '',
            'AID': aid,
            'SessionID': session_id,
        },
    })
    if not isinstance(data, dict):
        return []
    return data.get('Mails') or []


def login_mails(login_data):
    return login_data.get('MailContainer', {}).get('Mails') or []


def unreceived_mail_ids(mails):
    mail_ids = []
    seen = set()
    for mail in mails:
        if not isinstance(mail, dict) or mail.get('IsReceived') is True:
            continue
        mail_id = oid(mail.get('_id'))
        if not mail_id or mail_id in seen:
            continue
        seen.add(mail_id)
        mail_ids.append(mail_id)
    return mail_ids


def claim_mail_rewards(login_data, mail_ids):
    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    total = len(mail_ids)

    for batch_no, batch_ids in enumerate(chunks(mail_ids, MAIL_BATCH_SIZE), 1):
        print(f'第 {batch_no} 批领取邮件：{batch_ids}')
        send({
            'route': 'MailHandler.ReceivedMails',
            'data': {
                'MailIDList': batch_ids,
                'AID': aid,
                'SessionID': session_id,
            },
        })
        end = min(batch_no * MAIL_BATCH_SIZE, total)
        print(f'已领取邮件：{end}/{total}')


def claim_all_quests(login_data):
    quest_ids = unique_in_order(iter_finished_unrewarded_quests(login_data))
    if not quest_ids:
        print('没有找到已完成但未领取的任务。')
        return

    print(f'找到 {len(quest_ids)} 个已完成但未领取的任务。')
    claim_quest_rewards(login_data, quest_ids)
    print('任务奖励领取完成。')


def claim_all_mails(login_data):
    mails = login_mails(login_data)
    if not mails:
        aid = login_data['Info']['_id']['$oid']
        session_id = login_data['SessionID']
        print('登录数据中没有邮件列表，正在查询邮箱...')
        mails = query_mails(aid, session_id)

    mail_ids = unreceived_mail_ids(mails)
    if not mail_ids:
        print('没有找到未领取邮件。')
        return

    print(f'找到 {len(mail_ids)} 封未领取邮件。')
    claim_mail_rewards(login_data, mail_ids)
    print('邮箱奖励领取完成。')


def main(login_data=None):
    if login_data is None:
        accounts = load_accounts()
        acc_idx = choose_account(accounts)
        print(f'当前账号：{accounts[acc_idx].get("Name")}')
        login_data = login_account(accounts, acc_idx)
    claim_all_quests(login_data)


if __name__ == '__main__':
    main()
