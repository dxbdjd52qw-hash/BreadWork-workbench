#!/usr/bin/env python3
"""Import the approved four-week plan. Dry-run by default; no credentials needed.

Run against the existing SQLite database on the application server:
  python3 scripts/import_testing_plan.py --db /opt/ytwb-backend/ytwb.db
  python3 scripts/import_testing_plan.py --db /opt/ytwb-backend/ytwb.db --apply
"""
import argparse
import collections
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from urllib.parse import quote

PREFIX = 'testing-plan-2026-10-31'
START = dt.date(2026, 10, 31)
WEEKS = [
    ('第 1 周 · Python / pytest', 'Python 工程化与测试基础', [
        ('搭建 Python venv 与 Git 项目', '建立项目目录和 Git 仓库，运行第一条 pytest；复习常用 Linux 文件与目录命令。'),
        ('复习函数、类、模块与数据结构', '用类表示 CAN 报文，完成列表、字典与模块拆分练习。'),
        ('处理 JSON / CSV 测试数据', '读取模拟报文数据并导出 CSV，分离测试输入和预期结果。'),
        ('添加 logging 与异常处理', '为解析工具添加日志；对缺字段、错误类型和非法输入作清晰处理。'),
        ('练习 pytest 断言与 Fixture', '编写正常、边界和异常用例；用 Fixture 管理测试环境。'),
        ('完成参数化测试与首周小工具', '用参数化覆盖多组数据，提交数据处理工具、测试代码与运行说明。'),
        ('第 1 周复盘与休息', '验收：能够独立处理 JSON/CSV 并运行 pytest；整理问题、补缺，留出休息时间。'),
    ]),
    ('第 2 周 · CAN / DBC', '汽车电子与 CAN 通信', [
        ('理解 CAN 总线与标准帧 / 扩展帧', '画出简化 ECU 通信关系，解释标识符、仲裁和帧的基本结构。'),
        ('理解 CAN ID、DLC、周期与 CAN FD', '记录常见字段，区分经典 CAN 与 CAN FD；练习报文周期检查。'),
        ('阅读 DBC 并练习信号解析', '用 cantools 读取小型 DBC，理解起始位、长度、字节序、比例因子和偏移。'),
        ('使用 python-can 虚拟总线收发', '使用 Virtual Bus 模拟报文收发，不需要购买 CAN 硬件。'),
        ('了解 UDS 常见服务并整理岗位要求', '了解会话控制、读取数据等诊断服务；开始关注日常实习，记录岗位要求与差距。'),
        ('集成 CAN 解析测试并尝试首批投递', '完成虚拟报文收发与解析用例；按实际进度整理简历并尝试合适岗位。'),
        ('第 2 周复盘与休息', '验收：能模拟 CAN 通信并解析简单信号；复盘岗位反馈和知识缺口，安排休息。'),
    ]),
    ('第 3 周 · HIL / 嵌入式', 'HIL 测试与嵌入式基础', [
        ('区分 MIL、SIL、HIL 与台架组成', '画出 ECU、被控对象模型、接口和测试执行模块；先理解原理。'),
        ('理解 ECU / VCU / BMS 与信号输入输出', '以简化控制器为例梳理输入、输出、状态与测试需求。'),
        ('设计故障注入与状态迁移用例', '列出信号缺失、报文超时、异常值等输入及预期故障响应。'),
        ('了解 CANoe / CAPL、dSPACE、Simulink 的用途', '仅了解各工具在流程中的作用，不以掌握商业工具为本月前提。'),
        ('复习 C 指针、结构体、位运算与 volatile', '完成结构体和位掩码练习，了解变量访问与硬件交互的基本问题。'),
        ('了解 MCU、GPIO、ADC、PWM 并实现简化状态机', '用 OFF、READY、DRIVE、FAULT 演示状态迁移，为综合项目准备模型。'),
        ('第 3 周复盘与休息', '验收：能解释 HIL 测试流程并给出 ECU 测试思路；梳理薄弱点，留出休息。'),
    ]),
    ('第 4 周 · 项目 / 实习', 'ECU/CAN 综合项目与实习准备', [
        ('建立 ECU/CAN 自动化测试项目骨架', '使用 Python + pytest，整理需求、虚拟 CAN 接口、DBC 与目录结构。'),
        ('实现报文收发、信号解析与状态切换', '整合 python-can 和 cantools，接入简化 ECU 状态机。'),
        ('实现超时、异常数据与故障响应测试', '覆盖报文丢失、边界值与异常输入，明确每项测试的预期行为。'),
        ('完善 pytest 用例、日志与测试报告', '运行测试，保存可复现日志和报告，修复发现的问题。'),
        ('完善 GitHub README 与测试开发简历', '写清安装、运行、架构、测试范围与软件仿真限制；只写实际完成的成果。'),
        ('准备面试讲解并继续投递日常实习', '练习 Python、pytest、CAN、HIL 基础问答，演示项目并更新投递记录。'),
        ('第 4 周验收、月度复盘与休息', '验收完整项目、测试报告、README、简历；依据面试反馈决定后续学习重点。'),
    ]),
]
RESOURCES = [
    ('Python', 'https://docs.python.org/zh-cn/3/tutorial/'),
    ('pytest', 'https://docs.pytest.org/en/stable/'),
    ('CAN', 'https://python-can.readthedocs.io/'),
    ('DBC', 'https://cantools.readthedocs.io/'),
    ('UDS', 'https://udsoncan.readthedocs.io/'),
    ('Git', 'https://git-scm.com/book/zh/v2'),
    ('Simulink 入门（选学）', 'https://www.mathworks.com/learn/tutorials/simulink-onramp.html'),
]


def build_plan():
    """Return existing collection shapes; fixed IDs make import repeatable."""
    result = {'todos': [], 'progress': [], 'ddls': [], 'notes': []}
    for w, (sub, title, days) in enumerate(WEEKS, 1):
        end = (START + dt.timedelta(days=w * 7 - 1)).isoformat()
        for d, (name, note) in enumerate(days, 1):
            number = (w - 1) * 7 + d
            result['todos'].append({
                'id': f'{PREFIX}-day-{number:02d}',
                'name': f'测开 D{number:02d}｜{name}', 'priority': 'P1' if d == 7 else 'P0',
                'cat': '测试开发', 'due': (START + dt.timedelta(days=number - 1)).isoformat(),
                'done': False, 'note': note, 'createdAt': '2026-10-30',
            })
        result['progress'].append({
            'id': f'{PREFIX}-week-{w}', 'subject': '测试开发', 'sub': sub,
            'name': f'第 {w} 周｜{title}', 'status': '未开始', 'pct': 0,
            'plan': end, 'note': days[-1][1],
        })
        result['ddls'].append({
            'id': f'{PREFIX}-milestone-{w}', 'name': f'测开第 {w} 周验收｜{title}',
            'type': '其他', 'due': end, 'done': False, 'note': days[-1][1],
        })
    schedule = '\n\n'.join(
        f'第 {w} 周：{title}\n' + '\n'.join(f'• {name}：{note}' for name, note in days)
        for w, (_, title, days) in enumerate(WEEKS, 1)
    )
    result['notes'].append({
        'id': f'{PREFIX}-overview', 'date': '2026-10-30', 'type': '学习计划', 'mood': '🙂',
        'done': '汽车测试开发｜一个月快速学习计划\n2026-10-31 — 2026-11-27（四周）\n'
                '目标：建立 Python、pytest、CAN/DBC、Linux/Git、HIL 基础，完成可展示的 ECU/CAN 软件自动化测试项目。\n'
                '个人基础：车辆工程本科，2028 届，已有 Python、C、Java 基础。所有任务初始均未完成。',
        'problem': schedule,
        'improve': '每日约 3.5 小时：理论 40 分钟 + 编程 90 分钟 + 项目 60 分钟 + 复习/面试 20 分钟。'
                   '每周六天学习，一天复盘休息；Python/pytest 优先，每周提交实际代码。\n\n'
                   '项目：虚拟 CAN 收发、DBC 信号解析、ECU 状态切换、超时与异常检测、pytest 用例、日志与报告。\n\n'
                   '学习资料：\n' + '\n'.join(f'{name}：{url}' for name, url in RESOURCES),
        'tomorrow': '第二周起关注并尝试投递日常实习，不必等全部学完。第四周整理 GitHub、README、简历和面试讲解。\n'
                    '目标岗位：汽车电子软件测试、HIL 测试、ECU/VCU 测试、汽车网络诊断、车联网自动化与嵌入式软件测试实习。\n'
                    '边界：本月只完成 HIL 原理学习和软件仿真，不等同于真实硬件台架经验；简历只写已经实际完成的能力与成果。',
        'createdAt': '2026-10-30T13:00:00Z',
    })
    return result


def stripped(value):
    if isinstance(value, dict):
        return {k: stripped(v) for k, v in value.items() if k not in ('id', 'updatedAt', 'deleted')}
    if isinstance(value, list):
        return [stripped(v) for v in value]
    return value


def canonical(value):
    return json.dumps(stripped(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def shifted(value, days):
    if isinstance(value, dict):
        return {k: shifted(v, days) for k, v in value.items()}
    if isinstance(value, list):
        return [shifted(v, days) for v in value]
    if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}(T|$)', value):
        date = dt.date.fromisoformat(value[:10]) + dt.timedelta(days=days)
        return date.isoformat() + value[10:]
    return value


def demo_candidates(rows):
    """Match historical full records against anchored demo batches.

    A sample word book with all original words supplies the batch date.
    Date edits, content edits, unrelated collections and chat sessions are kept.
    """
    templates = json.loads(Path(__file__).with_name('legacy_demo.json').read_text(encoding='utf-8'))
    signatures = collections.defaultdict(set)
    for fixture in templates:
        sample = fixture['collections']
        base = dt.date.fromisoformat(fixture['base'])
        anchors = set()
        for col, _, item, _ in rows:
            if col != 'wordBooks':
                continue
            try:
                days = (dt.date.fromisoformat(item.get('createdAt', '')) - base).days
            except (ValueError, TypeError):
                continue
            if any(canonical(item) == canonical(shifted(book, days)) for book in sample['wordBooks']):
                anchors.add(days)
        for col, items in sample.items():
            if not isinstance(items, list) or col == 'chatSessions':
                continue
            # Courses do not contain dates; matching them needs no batch anchor.
            for days in anchors or {0}:
                for item in items:
                    candidate=shifted(item, days)
                    if col=='ddls' and item.get('name') in ('考研初试','四六级考试','期末周开始'):
                        candidate['due']=item['due']  # 这些日期是固定日历日期，不随示例创建日移动。
                    signatures[col].add(canonical(candidate))
    return [(col, rid, item, stamp) for col, rid, item, stamp in rows
            if not item.get('deleted') and canonical(item) in signatures.get(col, set())]


def read_rows(conn):
    return [(col, rid, json.loads(data), stamp)
            for col, rid, data, stamp in conn.execute('SELECT collection,id,data,updated_at FROM records')]


def migrate(db_path, apply=False):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    uri = 'file:' + quote(str(db_path), safe='/') + ('?mode=rw' if apply else '?mode=ro')
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    backup = None
    try:
        if apply:
            conn.execute('BEGIN IMMEDIATE')
            # A separate read connection can back up while the write reservation
            # prevents other writers from changing the migration's input.
            suffix = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            backup = db_path.with_name(db_path.name + '.before-testing-plan-' + suffix + '.bak')
            fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with sqlite3.connect('file:' + quote(str(db_path), safe='/') + '?mode=ro', uri=True) as src:
                with sqlite3.connect(backup) as dest:
                    src.backup(dest)
        rows = read_rows(conn)
        candidates = demo_candidates(rows)
        existing = {(col, rid) for col, rid, _, _ in rows}
        imports = [(col, item) for col, items in build_plan().items() for item in items
                   if (col, item['id']) not in existing]
        candidate_ids={(col,rid) for col,rid,_,_ in candidates}
        report = {
            'mode': 'apply' if apply else 'dry-run',
            'delete_counts': dict(collections.Counter(col for col, _, _, _ in candidates)),
            'insert_counts': dict(collections.Counter(col for col, _ in imports)),
            'preserved_active_counts': dict(collections.Counter(
                col for col, rid, item, _ in rows if not item.get('deleted') and
                (col, rid) not in candidate_ids)),
        }
        if apply:
            stamp = max(time.time() * 1000, max((float(row[3]) for row in rows), default=0) + 1)
            iso = dt.datetime.fromtimestamp(stamp / 1000, dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
            for col, rid, original, _ in candidates:
                item = copy.deepcopy(original)
                item.update(deleted=True, updatedAt=iso)
                conn.execute('UPDATE records SET data=?,updated_at=? WHERE collection=? AND id=?',
                             (json.dumps(item, ensure_ascii=False), stamp, col, rid))
            for col, item in imports:
                item['updatedAt'] = iso
                conn.execute('INSERT INTO records(collection,id,data,updated_at) VALUES(?,?,?,?)',
                             (col, item['id'], json.dumps(item, ensure_ascii=False), stamp))
            conn.commit()
            report['backup'] = str(backup)
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(migrate(args.db, args.apply), ensure_ascii=False, indent=2))
