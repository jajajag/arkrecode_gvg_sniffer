from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import requests
import sqlite3
import UnityPy

from utils.helper import APP_ROOT as ROOT_DIR, DATA_DIR
MASTER_DB = DATA_DIR / 'master.db'
MASTER_DATA = DATA_DIR / 'master.json'
CATALOG_DIR = DATA_DIR / 'catalogs'
STATICDATA_DIR = DATA_DIR / 'staticdata'
CONFIG = DATA_DIR / 'config.json'
DEFAULT_EXTS = ('.bundle', '.unity3d', '.assets', '.ab', '')
TEXT_TABLES = {'CHS', 'CHT', 'DEU', 'ENG', 'FRA', 'JPN', 'KOR', 'SPA', 'THA',
               'VIE'}

def _qident(name):
    return '"' + name.replace('"', '""') + '"'

def _clean_ident(name, fallback):
    name = re.sub(r'\s+', '_', (name or '').strip())
    name = re.sub(r'[^0-9A-Za-z_\u4e00-\u9fff.-]', '_', name).strip('._-')
    return name or fallback

def _unique_names(names):
    used = defaultdict(int)
    out = []
    for i, name in enumerate(names, 1):
        base = _clean_ident(name, f'col_{i}')
        used[base] += 1
        out.append(base if used[base] == 1 else f'{base}_{used[base]}')
    return out

def _safe_text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8-sig', errors='replace')
    if not isinstance(value, str):
        value = str(value)
    return value.encode('utf-8', errors='replace').decode('utf-8')

def _split_row(line):
    return line.rstrip('\r\n').split('@')

def _parse_table(text):
    lines = [ln.rstrip('\r') for ln in text.splitlines() if ln.rstrip('\r')]
    if not lines:
        return [], []

    if '@' in lines[0]:
        headers = _unique_names(_split_row(lines[0]))
        data_lines = lines[1:]
    else:
        headers = ['value']
        data_lines = lines

    width = len(headers)
    rows = []
    for line in data_lines:
        cells = _split_row(_safe_text(line))
        if len(cells) < width:
            cells += [''] * (width - len(cells))
        elif len(cells) > width:
            extra = len(cells) - width
            headers.extend(f'extra_{i + 1}' for i in range(extra))
            for row in rows:
                row.extend('' for _ in range(extra))
            width = len(headers)
        rows.append(cells)
    return headers, rows

def _candidate_files(data_dir, exts):
    files = []
    for path in sorted(data_dir.rglob('*')):
        if not path.is_file():
            continue
        if path.name == 'master.db' \
                or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3'}:
            continue
        if path.suffix.lower() in exts or 'bundle' in path.name.lower():
            files.append(path)
    return files

def _file_key(path):
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.as_posix()

def _fingerprint(files, catalog_name=None):
    return {
        'catalog_name': catalog_name,
        'files': [
            {'path': _file_key(path), 'size': path.stat().st_size,
             'mtime_ns': path.stat().st_mtime_ns} for path in files
        ],
    }

def _load_json(path):
    if not path.exists():
        return None
    try:
        with path.open('r', encoding='utf-8') as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None

def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

def _load_config():
    return _load_json(CONFIG) or {}

def _save_config(config):
    _save_json(CONFIG, config)

def _select_rows_by_key(conn, table, key, columns):
    cols = ', '.join(_qident(col) for col in columns)
    return {row[key]: dict(row) for row in conn.execute(
        f'SELECT {cols} FROM {_qident(table)}')}

def _select_rows_grouped(conn, table, key, columns):
    cols = ', '.join(_qident(col) for col in columns)
    groups = {}
    for row in conn.execute(f'SELECT {cols} FROM {_qident(table)}'):
        data = dict(row)
        groups.setdefault(data[key], []).append(data)
    return groups

def build_master_data(db_path=MASTER_DB, out_path=MASTER_DATA):
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        stat_cols = [
            'HP', 'Attack', 'Defence', 'Speed', 'CriticalRate',
            'CriticalDamageRate', 'EffectHitRate', 'ResistanceRate',
            'PinchRate',
        ]
        value_cols = ['HPValue', 'AttackValue', 'DefenceValue', 'SpeedValue']
        rate_cols = [
            'HPRate', 'AttackRate', 'DefenceRate', 'SpeedRate', 'CriticalRate',
            'CriticalDamageRate', 'EffectHitRate', 'ResistanceRate',
            'PinchRate',
        ]
        role_cols = [
            'ID', 'NAME', 'RolePropertyID', 'TeamImprint', 'SelfImprint',
            *stat_cols,
        ]
        role_property_cols = ['ID', 'LV', *stat_cols]
        role_awaken_cols = ['RoleID', 'LV', *value_cols, *rate_cols]
        artifact_cols = ['ID', 'Base.AttackValue', 'Base.HPValue',
                         'Max.AttackValue', 'Max.HPValue']
        equipment_set_cols = ['ID', 'Count', 'Name', *rate_cols]
        passive_cols = ['PassiveProp.DynamicField1',
                        'PassiveProp.DynamicField2',
                        'PassiveProp.DynamicField3']
        roles = _select_rows_by_key(conn, 'Role', 'ID', role_cols)
        items = _select_rows_by_key(conn, 'Item', 'ID', ['ID', 'Name'])
        equipment_sets = _select_rows_by_key(conn, 'EquipmentSet', 'ID',
                                             equipment_set_cols)
        localize_keys = {
            'UI_Equip_Weapon', 'UI_Equip_Helmet', 'UI_Equip_Armor',
            'UI_Equip_Necklace', 'UI_Equip_Ring', 'UI_Equip_Boots',
            'UI_Equip_Attributes_AttackRate', 'UI_Equip_Attack',
            'UI_PropertyCriticalDamage', 'UI_Equip_Critical',
            'UI_Guild_Defense', 'UI_PropertyEffectHit', 'UI_Equip_Health',
            'UI_PropertyResistance', 'UI_PropertySpeed',
        }
        localize_keys.update(row['NAME'] for row in roles.values()
                if row.get('NAME'))
        localize_keys.update(row['Name'] for row in items.values()
                if row.get('Name'))
        localize_keys.update(row['Name'] for row in equipment_sets.values()
                if row.get('Name'))
        placeholders = ', '.join('?' for _ in localize_keys)
        localization = {}
        if localize_keys:
            localization = dict(conn.execute(
                f'SELECT Key, Value FROM CHS WHERE Key IN ({placeholders})',
                tuple(sorted(localize_keys)),
            ).fetchall())
        data = {
            'localization': localization,
            'roles': roles,
            'role_properties': _select_rows_grouped(
                conn, 'RoleProperty', 'ID', role_property_cols),
            'role_awaken': _select_rows_grouped(
                conn, 'RoleAwaken', 'RoleID', role_awaken_cols),
            'role_imprints': _select_rows_by_key(
                conn, 'RoleImprint', 'ID',
                ['ID', 'Base.DynamicField1', 'LevelAdd.DynamicField1']),
            'artifacts': _select_rows_by_key(
                conn, 'Artifact', 'ID', artifact_cols),
            'items': items,
            'skills': _select_rows_by_key(
                conn, 'Skill', 'ID', ['ID', *passive_cols]),
            'skill_levels': _select_rows_grouped(
                conn, 'SkillLevel', 'SkillID',
                ['SkillID', 'LV', *passive_cols]),
            'equipment_sets': equipment_sets,
            'activities': _select_rows_by_key(
                conn, 'Activity', 'ID', ['ID', 'Type']),
            'scenes': _select_rows_grouped(
                conn, 'Scene', 'Chapter', ['Chapter', 'ID', 'MyCampTeam']),
        }
    finally:
        conn.close()
    _save_json(out_path, data)

def _data_dir_catalog(data_dir):
    return data_dir.name if data_dir.name.startswith('catalog_') else None

def _insert_table(conn, table, source_file, asset_name, columns, rows):
    conn.execute(f'DROP TABLE IF EXISTS {_qident(table)}')
    conn.execute(f'CREATE TABLE {_qident(table)} '
                 f'({", ".join(f"{_qident(c)} TEXT" for c in columns)})')
    if rows:
        col_sql = ', '.join(_qident(c) for c in columns)
        placeholders = ', '.join('?' for _ in columns)
        conn.executemany(
            f'INSERT INTO {_qident(table)} ({col_sql}) VALUES ({placeholders})',
            [tuple(_safe_text(cell) for cell in row[: len(columns)]) \
                    for row in rows])
    conn.execute(
        'INSERT INTO __table_manifest(table_name, source_file, asset_name, '
        'row_count, column_count) VALUES (?, ?, ?, ?, ?)',
        (table, str(source_file), asset_name, len(rows), len(columns)),
    )

def _extract_file(path, conn, seen_tables):
    env = UnityPy.load(str(path))
    table_count = 0
    row_count = 0

    for obj in env.objects:
        if obj.type.name != 'TextAsset':
            continue
        try:
            data = obj.read()
            asset_name = _clean_ident(getattr(data, 'm_Name', ''),
                                      f'textasset_{obj.path_id}')
            if asset_name in TEXT_TABLES and asset_name != 'CHS':
                continue
            columns, rows = _parse_table(_safe_text(getattr(
                data, 'm_Script', '')))
            if not columns and not rows:
                continue

            seen_tables[asset_name] = seen_tables.get(asset_name, 0) + 1
            table = asset_name if seen_tables[asset_name] == 1 \
                    else f'{asset_name}_{seen_tables[asset_name]}'
            _insert_table(conn, table, path, asset_name, columns, rows)
            table_count += 1
            row_count += len(rows)
        except Exception as exc:
            print(f'WARN: skipped asset {path}:'
                  f'{getattr(obj, "path_id", "?")}: {exc}')

    return table_count, row_count

def build_master_db(data_dir, out_path=MASTER_DB, force=False, exts=None,
                    catalog_name=None):
    data_dir = Path(data_dir)
    out_path = Path(out_path)
    scan_exts = tuple(e.lower() if e.startswith('.') else '.' + e.lower() \
            for e in (exts or DEFAULT_EXTS))
    files = _candidate_files(data_dir, scan_exts)
    if not files:
        print(f'No candidate Unity files found under {data_dir}')
        return 0, 0

    fingerprint = _fingerprint(
            files, catalog_name or _data_dir_catalog(data_dir))
    config = _load_config()
    if out_path.exists() and not force and MASTER_DATA.exists() \
            and config.get('master_db') == fingerprint:
        print(f'Up to date: {out_path}')
        return 0, 0
    if out_path.exists() and not force \
            and config.get('master_db') == fingerprint:
        build_master_data(out_path, MASTER_DATA)
        print(f'Built data cache: {MASTER_DATA}')
        return 0, 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    total_tables = 0
    total_rows = 0
    conn = sqlite3.connect(out_path)
    try:
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute(
            'CREATE TABLE __table_manifest'
            '(table_name TEXT PRIMARY KEY, source_file TEXT, asset_name TEXT,'
            ' row_count INTEGER, column_count INTEGER)'
        )
        seen_tables = {}
        for path in files:
            try:
                tables, rows = _extract_file(path, conn, seen_tables)
                if tables:
                    print(f'已读取 staticdata：{path.name}'
                          f'（{tables}表 / {rows}行）')
                total_tables += tables
                total_rows += rows
            except Exception as exc:
                print(f'WARN: skipped {path.name}: {exc}')
        conn.commit()
    finally:
        conn.close()

    catalog_name = fingerprint.get('catalog_name')
    if catalog_name:
        catalog_state = config.get('catalog') \
                if isinstance(config.get('catalog'), dict) else {}
        config['catalog'] = {**catalog_state, 'catalog_name': catalog_name}
    config['master_db'] = fingerprint
    _save_config(config)
    build_master_data(out_path, MASTER_DATA)
    print(f'完成：写入 {total_tables} 表 / {total_rows} 行 -> {out_path.name}')
    return total_tables, total_rows

def _catalog_name(info):
    name = info.get('NewCatalogName')
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None

def _patch_domain(info):
    domains = []
    for key in ('PathDomain', 'PathDomains'):
        value = info.get(key)
        if isinstance(value, str):
            domains.extend(part.strip() for part in re.split(r'[,;|]', value) \
                    if part.strip())
    return domains[0].rstrip('/') if domains else None

def _download_json(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()

def _download_file(url, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + '.tmp')
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with tmp_path.open('wb') as fp:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fp.write(chunk)
    tmp_path.replace(out_path)

def _staticdata_bundle_urls(catalog, patch_domain):
    urls = []
    for internal_id in catalog.get('m_InternalIds', []):
        if not isinstance(internal_id, str):
            continue
        lower_id = internal_id.lower()
        if 'staticdata' not in lower_id or '.bundle' not in lower_id:
            continue
        url = internal_id.replace('http://PatchDomain', patch_domain)
        url = url.replace('https://PatchDomain', patch_domain)
        if url.startswith('//'):
            url = f'https:{url}'
        if not url.startswith(('http://', 'https://')):
            url = f'{patch_domain}/{url.lstrip("/")}'
        if url not in urls:
            urls.append(url)
    return urls

def _bundle_path(catalog_name, url):
    name = Path(urlparse(url).path).name or 'staticdata.bundle'
    return STATICDATA_DIR / catalog_name / name

def _ensure_catalog_staticdata(bulletin):
    info = bulletin.get('Info', bulletin)
    if not isinstance(info, dict):
        return None

    catalog_name = _catalog_name(info)
    patch_domain = _patch_domain(info)
    if not catalog_name or not patch_domain:
        return None

    config = _load_config()
    catalog_state = config.get('catalog')
    if (
        isinstance(catalog_state, dict)
        and catalog_state.get('catalog_name') == catalog_name
        and MASTER_DB.exists()
        and MASTER_DATA.exists()
    ):
        print(f'master.db 已是最新 catalog：{catalog_name}')
        return None
    if isinstance(catalog_state, dict) \
            and catalog_state.get('catalog_name') == catalog_name \
            and MASTER_DB.exists():
        build_master_data(MASTER_DB, MASTER_DATA)
        print(f'master_data 已从现有 master.db 生成：{catalog_name}')
        return None

    catalog_url = f'{patch_domain}/Android/{catalog_name}.json'
    print(f'正在下载 catalog：{catalog_name}')
    catalog = _download_json(catalog_url)
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    _save_json(CATALOG_DIR / f'{catalog_name}.json', catalog)
    config['catalog'] = {
        'catalog_name': catalog_name,
        'url': catalog_url,
    }
    _save_config(config)

    urls = _staticdata_bundle_urls(catalog, patch_domain)
    if not urls:
        raise RuntimeError(
                f'catalog 中没有找到 staticdata bundle：{catalog_name}')

    target_dir = STATICDATA_DIR / catalog_name
    for url in urls:
        out_path = _bundle_path(catalog_name, url)
        if out_path.exists():
            continue
        print(f'正在下载 staticdata：{out_path.name}')
        _download_file(url, out_path)

    return target_dir

def ensure_master_db(bulletin=None):
    try:
        build_data_dir = _ensure_catalog_staticdata(bulletin) \
                if bulletin else DATA_DIR
        if build_data_dir is None:
            return
        info = bulletin.get('Info', bulletin) if bulletin else {}
        catalog_name = _catalog_name(info) if isinstance(info, dict) else None
        build_master_db(build_data_dir, MASTER_DB, catalog_name=catalog_name)
        if bulletin:
            if catalog_name:
                config = _load_config()
                catalog_state = config.get('catalog') \
                        if isinstance(config.get('catalog'), dict) else {}
                config['catalog'] = {**catalog_state,
                                     'catalog_name': catalog_name}
                _save_config(config)
    except Exception as exc:
        if isinstance(exc, requests.RequestException) \
                or isinstance(exc, (OSError, RuntimeError)):
            print(f'master.db 下载失败，继续使用现有数据：{exc}')
        else:
            raise

def connect_master():
    if not MASTER_DB.exists():
        return None
    return sqlite3.connect(MASTER_DB)
