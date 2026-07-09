import itertools
import json
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.helper import get_set

PARTS = ('Weapon', 'Head', 'Body', 'Necklace', 'Ring')
# 以速度套兔子的速度为基准
SPEED_SET_BASE = 189
BROKEN_SET_BASE = 169

def display_width(value):
    text = str(value)
    return sum(
        2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
        for ch in text
    )

def pad(value, width):
    text = str(value)
    return text + ' ' * max(width - display_width(text), 0)

def print_table(headers, rows):
    widths = [
        max(display_width(row[idx]) for row in [headers, *rows])
        for idx in range(len(headers))
    ]
    print(' '.join(
        pad(value, widths[idx]) for idx, value in enumerate(headers)))
    print(' '.join('-' * width for width in widths))
    for row in rows:
        print(' '.join(
            pad(value, widths[idx]) for idx, value in enumerate(row)))

def speed_value(row):
    for idx in range(1, 5):
        if row[f'sub{idx}_prop'] == 'SpeedValue':
            return float(row[f'sub{idx}_value'] or 0)
    return 0.0

def find_player_cuids(conn, query):
    if query.isdigit():
        rows = conn.execute(
            '''
            SELECT DISTINCT cuid
            FROM pvp_equips
            WHERE cuid = ?
            ''',
            (int(query),),
        ).fetchall()
    else:
        rows = conn.execute(
            '''
            SELECT DISTINCT cuid
            FROM pvp_equips
            WHERE player_name LIKE ?
            ''',
            (f'%{query}%',),
        ).fetchall()
    return [int(row['cuid']) for row in rows]

def display_player_name(names, query):
    counts = Counter(names)
    if query and not query.isdigit():
        for name, _ in counts.most_common():
            if query == name:
                return name
        for name, _ in counts.most_common():
            if query in name:
                return name
    return counts.most_common(1)[0][0]

def load_player_equips(conn, query):
    cuids = find_player_cuids(conn, query)
    if not cuids:
        return {}
    placeholders = ','.join('?' for _ in cuids)
    rows = conn.execute(
        f'''
        SELECT *
        FROM pvp_equips
        WHERE cuid IN ({placeholders})
          AND equip_type IN ('Weapon', 'Head', 'Body', 'Necklace', 'Ring')
        ORDER BY cuid, player_name, equip_type
        ''',
        cuids,
    ).fetchall()
    players, names = {}, {}
    for row in rows:
        cuid = int(row['cuid'])
        equip = dict(row)
        equip['speed'] = speed_value(row)
        players.setdefault(cuid, []).append(equip)
        names.setdefault(cuid, []).append(row['player_name'])
    return {
        (cuid, display_player_name(names[cuid], query)): equips
        for cuid, equips in players.items()
    }

def best_speed_combo(equips, used=None):
    used = used or set()
    by_part = {part: [] for part in PARTS}
    for equip in equips:
        if equip['equip_id'] in used:
            continue
        part = equip['equip_type']
        if part in by_part:
            by_part[part].append(equip)

    if any(not by_part[part] for part in PARTS):
        return None
    best_total = -1.0
    best_combo = []
    best_mode = ''
    for combo in itertools.product(*(by_part[part] for part in PARTS)):
        speed_set_count = sum(
            1 for equip in combo
            if equip['set_name'] == 'Speed'
        )
        sub_speed = sum(float(equip['speed']) for equip in combo)
        candidates = [('散件', BROKEN_SET_BASE + sub_speed)]
        if speed_set_count >= 3:
            candidates.append(('速度套', SPEED_SET_BASE + sub_speed))
        for mode, total in candidates:
            if total > best_total:
                best_total = total
                best_combo = list(combo)
                best_mode = mode
    if best_total < 0:
        return None
    return best_total, best_combo, best_mode

def fmt_speed(value):
    if value is None:
        return '-'
    return str(round(value, 2)).rstrip('0').rstrip('.')

def fmt_combo(combo):
    pieces = []
    for equip in sorted(
            combo, key=lambda item: PARTS.index(item['equip_type'])):
        set_name = get_set(equip['set_name'])[0]
        pieces.append(f'{set_name}{fmt_speed(equip["speed"])}')
    return ' '.join(pieces)

def main(argv=None):
    player_name = ' '.join(sys.argv[1:] if argv is None else argv).strip()
    if not player_name:
        print('用法: python3 scripts/pvp_speed.py <玩家名称>')
        print('示例: python3 scripts/pvp_speed.py 杂鱼')
        return 1

    try:
        conn = sqlite3.connect('data/data.db')
        conn.row_factory = sqlite3.Row
        players = load_player_equips(conn, player_name)
    except Exception:
        print(f'找不到data/data.db，请先运行9！')
        return 1
    finally:
        if 'conn' in locals():
            conn.close()
    if not players:
        print(f'没有找到包含「{player_name}」的玩家装备')
        return 0
    rows = []
    for (cuid, name), equips in sorted(
        players.items(),
        key=lambda item: (item[0][1], item[0][0]),
    ):
        first = best_speed_combo(equips)
        used = {equip['equip_id'] for equip in first[1]} if first else set()
        second = best_speed_combo(equips, used)
        rows.append([
            name,
            cuid,
            f'{fmt_speed(first[0] if first else None)}(一速'
            f'{"/" + first[2] if first else ""})',
            fmt_combo(first[1]) if first else '-',
        ])
        rows.append([
            name,
            cuid,
            f'{fmt_speed(second[0] if second else None)}(二速'
            f'{"/" + second[2] if second else ""})',
            fmt_combo(second[1]) if second else '-',
        ])
    print_table(['玩家名', 'cuid', '速度', '装备'], rows)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
