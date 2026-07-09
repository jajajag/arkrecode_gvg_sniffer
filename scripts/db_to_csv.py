import argparse
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.helper import data_path, get_role

FIELDNAMES = [
    'date', 'def_1', 'def_2', 'def_3', 'atk_1', 'atk_2', 'atk_3',
    'win', 'dead', 'def_cuid', 'def_name', 'def_guild',
    'atk_cuid', 'atk_name', 'atk_guild', 'battle_id'
]

def load_units(conn, battle_id, round_idx, side):
    rows = conn.execute('''
        SELECT role_id, dead FROM gvg_units
        WHERE battle_id = ? AND round_idx = ? AND side = ?
        ORDER BY pos
    ''', (battle_id, round_idx, side)).fetchall()
    return [dict(row) for row in rows]

def db_to_csv(db_path=None, filename=None):
    db_path = data_path('data.db') if db_path is None else db_path
    filename = data_path('团战防守.csv') \
        if filename is None else filename
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rounds = conn.execute('''
        SELECT * FROM gvg_rounds
        ORDER BY start_ts, battle_id, round_idx
    ''').fetchall()

    rows = []
    for r in rounds:
        atk_team = (load_units(conn, r['battle_id'], r['round_idx'], 'atk')
                    + [{}] * 3)[:3]
        def_team = (load_units(conn, r['battle_id'], r['round_idx'], 'def')
                    + [{}] * 3)[:3]
        rows.append({
            'date': datetime.fromtimestamp(r['start_ts'] / 1000,
                tz=timezone.utc).strftime('%Y-%m-%d'),
            'atk_1': get_role(atk_team[0].get('role_id', '')),
            'atk_2': get_role(atk_team[1].get('role_id', '')),
            'atk_3': get_role(atk_team[2].get('role_id', '')),
            'def_1': get_role(def_team[0].get('role_id', '')),
            'def_2': get_role(def_team[1].get('role_id', '')),
            'def_3': get_role(def_team[2].get('role_id', '')),
            'win': bool(r['win']),
            'dead': ''.join(str(i) for i, u in enumerate(
                def_team[:3] + atk_team[:3], start=1) if u.get('dead')),
            'atk_cuid': r['atk_cuid'],
            'atk_name': r['atk_name'],
            'atk_guild': r['atk_guild'],
            'def_cuid': r['def_cuid'],
            'def_name': r['def_name'],
            'def_guild': r['def_guild'],
            'battle_id': r['battle_id'],
        })

    conn.close()

    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)

    print(f'Saved: {filename} (rows={len(rows)})')

if __name__ == '__main__':
    db_to_csv()
