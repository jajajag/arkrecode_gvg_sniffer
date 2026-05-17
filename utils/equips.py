import numpy as np
import sqlite3
import warnings
from collections import defaultdict
from itertools import combinations
from sklearn.decomposition import NMF
from sklearn.exceptions import ConvergenceWarning
from utils.helper import get_prop_score

warnings.filterwarnings('ignore', category=ConvergenceWarning)

# 最低40分，且满足模板孤立度和内聚度要求
MIN_SCORE = 40
MIN_ORPHAN = 0.08
MIN_COHERENCE = 0.10
# 传说装备
MIN_CLASS_LV = 4
TYPE_MAP = {
    '1': 'Weapon', '2': 'Head', '3': 'Body',
    '4': 'Necklace', '5': 'Ring', '6': 'Shoes'
}
# 85级装备
VALID_EQUIPS = {'E010', 'E016', 'E022', 'E028', 'E034'}
TEMPLATE = None

# 保存PVP前百装备数据到数据库
def save_pvp_equips(data, db_path='data.db'):
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE IF NOT EXISTS pvp_equips (
            equip_id TEXT PRIMARY KEY, cuid INTEGER, player_name TEXT,
            equip_type TEXT, static_id TEXT, set_name TEXT,
            class_lv INTEGER, lv INTEGER, main_prop TEXT, main_value REAL,
            sub1_prop TEXT, sub1_value REAL, sub2_prop TEXT, sub2_value REAL,
            sub3_prop TEXT, sub3_value REAL, sub4_prop TEXT, sub4_value REAL
        )
    ''')
    # 1. Go through players' defence teams
    for item in data['PVPRankInfoList']:
        player_info = item['PlayerInfo']
        cuid = player_info['CUID']
        player_name = player_info['Name']

        role_map = item['PVPInfo']['DefenceTeam']['PositionRoleMap']

        # 2. Go through roles
        for role in role_map.values():
            equip_map = role.get('EquipmentMap', {})

            # 3. Go through equipments
            for equip_type, equip in equip_map.items():
                equip_id = equip['_id']['$oid']

                new_lv = equip['LV']
                old_lv = conn.execute(
                    'SELECT lv FROM pvp_equips WHERE equip_id = ?',
                    (equip_id,)
                ).fetchone()
                # Skip if existing record has same or higher level
                if old_lv and new_lv <= old_lv[0]:
                    continue

                main_prop = equip['MainProp']
                # Pad subprops to ensure we have 4 entries
                subprops = equip['SubProps']['SourceValues']
                subprops = (subprops + [{}] * 4)[:4]

                conn.execute('''
                    INSERT OR REPLACE INTO pvp_equips (
                        equip_id, cuid, player_name, equip_type, static_id,
                        set_name, class_lv, lv, main_prop, main_value,
                        sub1_prop, sub1_value, sub2_prop, sub2_value,
                        sub3_prop, sub3_value, sub4_prop, sub4_value
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    equip_id, cuid, player_name, equip_type,
                    equip['StaticID'], equip['Set'], equip['ClassLV'], new_lv,
                    main_prop['PropertyType'], main_prop['Value'],
                    subprops[0].get('PropertyType', ''),
                    subprops[0].get('Value', 0),
                    subprops[1].get('PropertyType', ''),
                    subprops[1].get('Value', 0),
                    subprops[2].get('PropertyType', ''),
                    subprops[2].get('Value', 0),
                    subprops[3].get('PropertyType', ''),
                    subprops[3].get('Value', 0),
                ))

    conn.commit()
    conn.close()

    print(f'Saved PVP equips to DB: {db_path}')

# 通过竞技场前百装备数据统计模板
def update_equip_templates(db_path='data.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute('''
        CREATE TABLE IF NOT EXISTS equip_templates (
            set_name TEXT, equip_type TEXT, main_prop TEXT,
            sub1_prop TEXT, sub2_prop TEXT, sub3_prop TEXT, sub4_prop TEXT,
            sample_count INTEGER, topic_count INTEGER,
            topic_mass REAL, coherence REAL, orphan REAL
        )
    ''')
    try:
        rows = conn.execute('''
            SELECT * FROM pvp_equips WHERE lv = 15 AND class_lv >= 4
              AND set_name != '' AND equip_type != '' AND main_prop != ''
        ''').fetchall()
    except Exception:
        conn.close()
        print(f'装备数据表不存在！')
        return

    groups = defaultdict(list)
    all_props = set()
    for row in rows:
        # Group the equip by (set_name, equip_type, main_prop) and subprops
        key = (row['set_name'], row['equip_type'], row['main_prop'])
        subs = {row[f'sub{i}_prop'] for i in range(1, 5) if row[f'sub{i}_prop']}
        if subs:
            groups[key].append(subs)
            all_props.update(subs)

    prop_list = sorted(all_props)
    prop_idx = {p: i for i, p in enumerate(prop_list)}
    # Clear old templates
    conn.execute('DELETE FROM equip_templates')

    for (set_name, equip_type, main_prop), transactions in groups.items():
        # Build NMF templates for this group of equips and insert into DB
        for t in build_nmf_templates(transactions, prop_list, prop_idx):
            core = (t['core'] + [''] * 4)[:4]
            conn.execute('''
                INSERT INTO equip_templates (
                    set_name, equip_type, main_prop,
                    sub1_prop, sub2_prop, sub3_prop, sub4_prop,
                    sample_count, topic_count, topic_mass, coherence, orphan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                set_name, equip_type, main_prop,
                core[0], core[1], core[2], core[3],
                len(transactions), t['topic_count'],
                t['topic_mass'], t['coherence'], t['orphan']
            ))

    conn.commit()
    conn.close()
    print(f'Updated equip templates in DB: {db_path}')

# 用Non-negative Matrix Factorization (NMF)计算副属性模板
def build_nmf_templates(transactions, prop_list, prop_idx):
    if (n := len(transactions)) < 8: return []
    X = np.zeros((n, len(prop_list)), dtype=float)
    for i, subs in enumerate(transactions):
        for prop in subs:
            X[i, prop_idx[prop]] = 1.0
    k = min(len(prop_list), max(2, n // 2))
    model = NMF(n_components=k, solver='mu', max_iter=1000, random_state=42)
    W = model.fit_transform(X)
    H = model.components_
    best_topics = W.argmax(axis=1)
    topic_counts = np.bincount(best_topics, minlength=k)
    # Process topics to find core subprops
    candidates = []
    for topic in range(k):
        topic_count = int(topic_counts[topic])
        topic_mass = topic_count / n
        top_idx = np.argsort(-H[topic])[:4]
        core = [prop_list[i] for i in top_idx if H[topic][i] > 1e-9]
        if len(core) < 4: continue
        # Exclude templates that are too diffuse or isolated
        coherence = pairwise_coherence(core, transactions)
        orphan = min(orphan_score(p, core, transactions) for p in core)
        candidates.append({
            'core': core, 'topic_count': topic_count, 'topic_mass': topic_mass,
            'coherence': coherence, 'orphan': orphan
        })
    return candidates

# 计算任意两副属性一起出现的概率，越低说明越分散
def pairwise_coherence(core, transactions):
    if not (pairs := list(combinations(core, 2))):
        return 0.0
    return sum(sum(1 for subs in transactions
                   if a in subs and b in subs) / len(transactions)
               for a, b in pairs) / len(pairs)

# 计算某副属性与其他属性一起出现的概率，越低说明越孤立
def orphan_score(prop, core, transactions):
    if not (others := [p for p in core if p != prop]):
        return 0.0
    return sum(sum(1 for subs in transactions
                   if prop in subs and other in subs) / len(transactions)
               for other in others) / len(others)

# 计算装备副属性分数
def equip_score(sub_props):
    return sum(v * get_prop_score(p) for p, v in sub_props.items())

def load_equip(db_path='data.db'):
    # Load templates from DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('''
            SELECT * FROM equip_templates WHERE orphan >= ? AND coherence >= ?
        ''', (MIN_ORPHAN, MIN_COHERENCE)).fetchall()
        conn.close()
        print(f'共加载 {len(rows)} 套装备模板！')
    except Exception:
        # Return empty index if table doesn't exist
        print(f'装备模板表不存在，请先运行 9 收集装备模板！')
        return defaultdict(list)
    # Load equip_type, set, and main_prop
    index = defaultdict(list)
    for row in rows:
        key = (row['equip_type'], row['set_name'], row['main_prop'])
        core = frozenset(row[f'sub{i}_prop'] for i in range(1, 5) 
                         if row[f'sub{i}_prop'])
        index[key].append(core)
    return index

def match_equip(equip):
    global TEMPLATE
    if TEMPLATE is None: TEMPLATE = load_equip()
    eq_type = TYPE_MAP[equip['StaticID'][-1]]
    set_name = equip['Set']
    main_prop = equip['MainProp']['PropertyType']
    key = (eq_type, set_name, main_prop)
    sub_props = {x['PropertyType'] for x in equip['SubProps']['SourceValues']}
    sub_dict = {
        x['PropertyType']: x['Value']
        for x in equip['SubProps']['SourceValues']
    }
    # 1. Check if the equip is legendary
    if equip['ClassLV'] < MIN_CLASS_LV:
        return None
    # 2. Check if the equip is LV85
    if equip['StaticID'][:4] not in VALID_EQUIPS:
        return None
    speed = sub_dict.get('SpeedValue', 0)
    # 3. 速度套和复仇套副属性速度必须大于等于4
    if set_name in {'Speed', 'Revenge'} and eq_type != 'Shoes' and speed < 4:
        return None
    # 4. 碰到非鞋子的5速直接拿
    if eq_type != 'Shoes' and speed >= 5:
        return f'{eq_type} {set_name} {main_prop} {score}-> {sub_props}'
    # 5. Check min subprop score
    score = equip_score({x['PropertyType']: x['Value'] 
                         for x in equip['SubProps']['SourceValues']})
    if score < MIN_SCORE:
        return None
    # 6. Check if subprops match a template
    if sub_props in TEMPLATE.get(key, []):
        return f'{eq_type} {set_name} {main_prop} {score}-> {sub_props}'

    return None
