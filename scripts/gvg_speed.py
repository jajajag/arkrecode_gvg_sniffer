import argparse
from collections import Counter
import json
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.helper import calculate_team_stats, get_role


DEFAULT_PROCESS = 'Ark ReCode.exe'

HOOK_JS = r'''
const mod = Process.getModuleByName("GameAssembly.dll");
const BASE = mod.base;

function addr(rva) {
    return BASE.add(ptr(rva));
}

function readIl2CppString(p) {
    if (p.isNull()) return null;
    try {
        const len = p.add(0x10).readS32();
        return p.add(0x14).readUtf16String(len);
    } catch (_) {
        return null;
    }
}

function readByteArrayAsUtf8(arr, maxLen = 1024 * 1024) {
    if (arr.isNull()) return null;
    try {
        const len = arr.add(0x18).readU32();
        if (len <= 0 || len > maxLen) return null;
        const data = arr.add(0x20);
        const bytes = data.readByteArray(len);
        return new TextDecoder("utf-8").decode(bytes);
    } catch (_) {
        return null;
    }
}

function isJsonText(s) {
    if (!s) return false;
    s = s.trim();
    return s.startsWith("{") || s.startsWith("[");
}

function emitPacket(tag, s) {
    if (!isJsonText(s)) return;
    send({tag: tag, text: s.trim()});
}

function getFrameText(fr) {
    try {
        const textPtr = fr.add(0x18).readPointer();
        const text = readIl2CppString(textPtr);
        if (isJsonText(text)) return text;
        const dataPtr = fr.add(0x10).readPointer();
        const dataText = readByteArrayAsUtf8(dataPtr);
        if (isJsonText(dataText)) return dataText;
        return null;
    } catch (_) {
        return null;
    }
}

Interceptor.attach(addr(0x88C280), {
    onEnter(args) {
        emitPacket("SEND", readIl2CppString(args[1]));
    }
});

Interceptor.attach(addr(0x8A5CC0), {
    onEnter(args) {
        this.fr = args[0];
    },
    onLeave(_) {
        emitPacket("RECV", getFrameText(this.fr));
    }
});
'''


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
    if not rows:
        return
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


def fmt_float(value, digits=6):
    if value is None:
        return '-'
    return f'{value:.{digits}f}'.rstrip('0').rstrip('.')


def role_sort_key(role_id):
    try:
        return tuple(int(part) for part in role_id.split('-'))
    except ValueError:
        return (99, 99, 99)


def action_delta(start, end):
    if start is None or end is None:
        return None
    delta = end - start
    if delta < 0:
        delta += 1
    return delta


def estimate_speed_value(values):
    rounded = [round(value) for value in values]
    counts = Counter(rounded)
    top_count = max(counts.values())
    modes = [value for value, count in counts.items() if count == top_count]
    if top_count > 1 and len(modes) == 1:
        return modes[0]
    return round(statistics.median(values))


def iter_team_maps(start_info):
    for side, key in (('1', 'CampData1'), ('2', 'CampData2')):
        role_map = (start_info.get(key) or {}).get('PositionRoleMap') or {}
        if role_map:
            yield side, 0, role_map

    if not (start_info.get('CampData1') or {}).get('PositionRoleMap'):
        for wave, camp in enumerate(start_info.get('WaveCampDatas') or []):
            role_map = (camp or {}).get('PositionRoleMap') or {}
            if role_map:
                yield '1', wave, role_map


def build_role_info(start_info):
    role_info = {}
    for side, wave, role_map in iter_team_maps(start_info):
        positions = sorted(role_map, key=lambda pos: int(pos))
        roles = [role_map[pos] for pos in positions]
        stats_list = calculate_team_stats(roles) if side == '1' else [None] * len(roles)
        for pos, role, stats in zip(positions, roles, stats_list):
            role_id = f'{side}-{wave}-{pos}'
            speed = round(stats.get('Speed', 0)) if stats else None
            role_info[role_id] = {
                'name': get_role(role.get('StaticID', '')),
                'static_id': role.get('StaticID', ''),
                'side': side,
                'speed': speed,
            }
    return role_info


def parse_packet_text(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def find_process_id(process_name):
    try:
        import frida
    except ImportError:
        frida = None

    if frida:
        target = process_name.lower()
        device = frida.get_local_device()
        for process in device.enumerate_processes():
            if process.name.lower() == target:
                return process.pid

    output = subprocess.check_output(
        ['tasklist', '/FO', 'CSV', '/NH'],
        text=True,
        encoding='mbcs',
        errors='ignore',
    )
    target = process_name.lower()
    for line in output.splitlines():
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == target:
            return int(parts[1])
    return None


class GvgSpeedAnalyzer:
    def __init__(self):
        self.battle_no = 0
        self.role_info = {}
        self.start_times = None
        self.printed = False

    def handle_packet(self, tag, text):
        data = parse_packet_text(text)
        if not isinstance(data, dict):
            return

        start_info = data.get('StartBattleInfo')
        if isinstance(start_info, dict):
            self.start_battle(start_info)

        round_result = data.get('RoundResult')
        if isinstance(round_result, dict):
            self.handle_round_result(data.get('Step'), round_result)

    def start_battle(self, start_info):
        self.battle_no += 1
        self.role_info = build_role_info(start_info)
        self.start_times = None
        self.printed = False
        print(f'\n===== 战斗 {self.battle_no} =====')

    def handle_round_result(self, step, round_result):
        role_time_map = round_result.get('RoleTimeMap')
        if not isinstance(role_time_map, dict):
            return
        times = {
            role_id: float(value)
            for role_id, value in role_time_map.items()
            if role_id != 'TurnRole'
        }
        if not times:
            return
        if self.start_times is None:
            self.start_times = times
            return
        if self.printed:
            return
        if step == 'StartRound' and int(round_result.get('NowTurn') or 0) == 1:
            self.print_speed_report(times)
            self.printed = True

    def print_speed_report(self, end_times):
        if not self.start_times:
            return

        rows = []
        ally_refs = []
        all_role_ids = sorted(
            set(self.start_times) | set(end_times) | set(self.role_info),
            key=role_sort_key,
        )
        for role_id in all_role_ids:
            info = self.role_info.get(role_id, {})
            start = self.start_times.get(role_id)
            end = end_times.get(role_id)
            delta = action_delta(start, end)
            speed = info.get('speed')
            if role_id.startswith('1-') and speed and delta and delta > 0:
                ally_refs.append((role_id, speed, delta))
            rows.append({
                'role_id': role_id,
                'side': '我方' if role_id.startswith('1-') else '敌方',
                'name': info.get('name') or info.get('static_id') or '?',
                'start': start,
                'end': end,
                'delta': delta,
                'speed': speed,
            })

        enemy_estimates = self.estimate_enemy_speeds(rows, ally_refs)
        table_rows = []
        for row in rows:
            role_id = row['role_id']
            speed = row['speed']
            if role_id.startswith('2-'):
                speed = enemy_estimates.get(role_id, '-')
            table_rows.append([
                row['side'],
                role_id,
                row['name'],
                fmt_float(row['start']),
                fmt_float(row['end']),
                fmt_float(row['delta']),
                speed,
            ])
        print_table(['阵营', 'RoleID', '角色', '乱速值', '行动值', '差值', '速度'], table_rows)

    def estimate_enemy_speeds(self, rows, ally_refs):
        estimates = {}
        if not ally_refs:
            return estimates
        for row in rows:
            if not row['role_id'].startswith('2-') or row['delta'] is None:
                continue
            values = [
                ally_speed / ally_delta * row['delta']
                for _, ally_speed, ally_delta in ally_refs
                if ally_delta
            ]
            if not values:
                continue
            speed = estimate_speed_value(values)
            low = min(values)
            high = max(values)
            estimates[row['role_id']] = (
                f'{speed}'
                if round(low) == round(high)
                else f'{speed}({round(low)}-{round(high)})'
            )
        return estimates


def run_live(process_name):
    try:
        import frida
    except ImportError:
        print('缺少 frida Python 包：请先 pip install frida，打包 exe 时把 frida 包一起打进去。')
        return 1

    pid = find_process_id(process_name)
    if not pid:
        print(f'找不到进程：{process_name}')
        return 1

    analyzer = GvgSpeedAnalyzer()
    device = frida.get_local_device()
    session = device.attach(pid)
    script = session.create_script(HOOK_JS)

    def on_message(message, data):
        if message.get('type') == 'send':
            payload = message.get('payload') or {}
            analyzer.handle_packet(payload.get('tag'), payload.get('text', ''))
        elif message.get('type') == 'error':
            print(message.get('stack') or message)

    script.on('message', on_message)
    script.load()
    print(f'已附加到 {process_name} (PID {pid})，等待战斗数据...')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        session.detach()
    return 0


def main():
    parser = argparse.ArgumentParser(description='实时反推 GVG/PVP 敌方速度')
    parser.add_argument(
        '-p', '--process',
        default=DEFAULT_PROCESS,
        help=f'游戏进程名，默认 {DEFAULT_PROCESS}',
    )
    args = parser.parse_args()

    return run_live(args.process)


if __name__ == '__main__':
    raise SystemExit(main())
