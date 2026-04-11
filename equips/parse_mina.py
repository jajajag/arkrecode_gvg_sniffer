# 装备模板文件来源于蜜娜
# 装备模板来源于太上天魔
# 由ChatGPT生成
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import json
import os
import sqlite3

EK = '7872333435366e656e656e6565746566353233346d6e6e656e656e6565746566'
OK = '6e656e656e6565743334787235326d6e'

ROOT_DIR = 'equipments'
DB_PATH = 'equipments.db'

SLOT_TO_TYPE = {
    'WEAPON': 'Weapon',
    'HELMET': 'Head',
    'ARMOR': 'Body',
    'NECKLACE': 'Necklace',
    'RING': 'Ring',
    'SHOES': 'Shoes',
}

DEFAULT_MAIN = {
    'Weapon': ['AttackValue'],
    'Head': ['HPValue'],
    'Body': ['DefenceValue'],
    'Necklace': [
        'AttackRate', 'DefenceRate', 'HPRate',
        'AttackValue', 'DefenceValue', 'HPValue',
        'CriticalRate', 'CriticalDamageRate',
    ],
    'Ring': [
        'AttackRate', 'DefenceRate', 'HPRate',
        'AttackValue', 'DefenceValue', 'HPValue',
        'EffectHitRate', 'ResistanceRate',
    ],
    'Shoes': [
        'AttackRate', 'DefenceRate', 'HPRate',
        'AttackValue', 'DefenceValue', 'HPValue',
        'SpeedValue',
    ],
}


def is_hex(s):
    s = s.strip()
    if len(s) % 2:
        return False
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False


def to_bytes(s):
    s = s.strip()
    return bytes.fromhex(s) if is_hex(s) else s.encode('utf-8')


def decrypt_text(text):
    key = to_bytes(EK)
    iv = to_bytes(OK)
    data = bytes.fromhex(text) if is_hex(text) else base64.b64decode(text)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    return unpad(cipher.decrypt(data), AES.block_size).decode('utf-8')


def flat_sub_props(sub_props):
    pairs = list((sub_props or {}).items())[:4]
    pairs += [('', None)] * (4 - len(pairs))
    return [x for pair in pairs for x in pair]


def parse_file(path, status):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read().strip().lstrip('\ufeff').strip()
    if not text:
        return []

    data = json.loads(decrypt_text(text))
    if not isinstance(data, list):
        data = [data]

    name = os.path.splitext(os.path.basename(path))[0]
    if '_' not in name:
        return []

    slot, set_name = name.split('_', 1)
    slot = slot.upper()
    if slot not in SLOT_TO_TYPE:
        return []

    eq_type = SLOT_TO_TYPE[slot]
    rows = []

    for obj in data:
        if not isinstance(obj, dict):
            continue

        sub_props = obj.get('sub_props', {})
        if not isinstance(sub_props, dict):
            sub_props = {}

        main_props = [obj['main_prop']] if obj.get('main_prop') \
                else DEFAULT_MAIN.get(eq_type, ['Unknown'])

        for main_prop in main_props:
            rows.append((
                eq_type,
                set_name,
                main_prop,
                *flat_sub_props(sub_props),
                status,
            ))

    return rows


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('DROP TABLE IF EXISTS equipments')
    cur.execute('''
        CREATE TABLE equipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            set_name TEXT,
            main_prop TEXT,
            sub1 TEXT,
            sub1_value REAL,
            sub2 TEXT,
            sub2_value REAL,
            sub3 TEXT,
            sub3_value REAL,
            sub4 TEXT,
            sub4_value REAL,
            status TEXT
        )
    ''')

    total = 0

    for folder, status in [('GoldCoin', 'gold'), ('StarSource', 'star')]:
        base = os.path.join(ROOT_DIR, folder)
        if not os.path.isdir(base):
            continue

        for dirpath, _, filenames in os.walk(base):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                try:
                    rows = parse_file(path, status)
                    if not rows:
                        continue

                    cur.executemany('''
                        INSERT INTO equipments (
                            type, set_name, main_prop,
                            sub1, sub1_value,
                            sub2, sub2_value,
                            sub3, sub3_value,
                            sub4, sub4_value,
                            status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', rows)
                    total += len(rows)

                except Exception as e:
                    print(f'[WARN] {path}: {e}')

    conn.commit()
    conn.close()
    print(f'done: {total}')


if __name__ == '__main__':
    main()
