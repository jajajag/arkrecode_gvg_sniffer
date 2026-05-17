import sqlite3
import json

DB = 'equipments.db'
OUT = 'equipments.json'

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute('''
        SELECT
            type,
            set_name,
            main_prop,
            sub1, sub1_value,
            sub2, sub2_value,
            sub3, sub3_value,
            sub4, sub4_value,
            status
        FROM equipments
    ''')

    rows = cur.fetchall()
    conn.close()

    rules = []

    for r in rows:
        (eq_type, set_name, main_prop, 
         s1, v1, s2, v2, s3, v3, s4, v4, status) = r

        sub_props = {}

        if s1: sub_props[s1] = v1
        if s2: sub_props[s2] = v2
        if s3: sub_props[s3] = v3
        if s4: sub_props[s4] = v4

        rules.append({
            'type': eq_type,
            'set_name': set_name,
            'main_prop': main_prop,
            'status': status,
            'sub_props': sub_props,
        })

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f'导出 {len(rules)} 条规则 -> {OUT}')


if __name__ == '__main__':
    main()
