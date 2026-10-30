import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('migration', ROOT / 'scripts/import_testing_plan.py')
module = importlib.util.module_from_spec(SPEC)
if SPEC.loader:
    SPEC.loader.exec_module(module)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'workbench.db'
        self.conn = sqlite3.connect(self.db)
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE records(collection TEXT,id TEXT,data TEXT,updated_at REAL,PRIMARY KEY(collection,id))')
        fixture = json.loads((ROOT / 'scripts/legacy_demo.json').read_text())[0]
        self.seed = fixture['collections']
        self.n = 0

    def insert(self, col, item):
        self.n += 1
        item = copy.deepcopy(item)
        item['id'] = 'old-' + str(self.n)
        self.conn.execute('INSERT INTO records VALUES(?,?,?,?)', (col,item['id'],json.dumps(item),0))
        self.conn.commit()
        return item['id']

    def read(self, col, rid):
        row = self.conn.execute('SELECT data FROM records WHERE collection=? AND id=?',(col,rid)).fetchone()
        return json.loads(row[0]) if row else None

    def add_anchor(self):
        return self.insert('wordBooks', self.seed['wordBooks'][0])

    def test_dry_run_does_not_mutate_database(self):
        self.add_anchor()
        rid = self.insert('progress',self.seed['progress'][0])
        report = module.migrate(self.db, apply=False)
        self.assertGreater(report['delete_counts']['progress'],0)
        self.assertFalse(self.read('progress',rid).get('deleted',False))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0],2)

    def test_apply_soft_deletes_only_exact_demo_records_and_backs_up(self):
        self.add_anchor()
        demo_id = self.insert('progress',self.seed['progress'][0])
        changed = dict(self.seed['progress'][0],pct=42,note='我的实际学习记录')
        real_id = self.insert('progress',changed)
        date_changed = dict(self.seed['progress'][0],plan='2026-12-01')
        edited_date_id = self.insert('progress',date_changed)
        chat_id = self.insert('chatSessions',{'name':'测试聊天','msgs':[{'text':'keep'}]})
        report = module.migrate(self.db,apply=True)
        self.assertTrue(self.read('progress',demo_id)['deleted'])
        self.assertGreater(self.read('progress',demo_id)['updatedAt'],'2026-10-30')
        self.assertEqual(self.read('progress',real_id)['pct'],42)
        self.assertFalse(self.read('progress',edited_date_id).get('deleted',False))
        self.assertEqual(self.read('chatSessions',chat_id)['msgs'][0]['text'],'keep')
        backup = Path(report['backup'])
        self.assertTrue(backup.is_file())
        with sqlite3.connect(backup) as b:
            self.assertEqual(b.execute('SELECT COUNT(*) FROM records').fetchone()[0],5)

    def test_repeated_import_preserves_completed_tasks(self):
        module.migrate(self.db,apply=True)
        row = self.conn.execute("SELECT id,data FROM records WHERE collection='todos' ORDER BY id LIMIT 1").fetchone()
        item = json.loads(row[1]); item['done']=True;item['updatedAt']='2026-11-04T00:00:00Z'
        self.conn.execute("UPDATE records SET data=? WHERE collection='todos' AND id=?",(json.dumps(item),row[0]));self.conn.commit()
        count = self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
        result = module.migrate(self.db,apply=True)
        self.assertEqual(result['insert_counts'],{})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0],count)
        self.assertTrue(self.read('todos',row[0])['done'])

    def test_plan_has_four_weeks_of_incomplete_work_and_software_only_hil(self):
        plan = module.build_plan()
        self.assertEqual(len(plan['todos']),28)
        self.assertEqual(len(plan['progress']),4)
        self.assertEqual(len(plan['ddls']),4)
        self.assertEqual(plan['todos'][0]['due'],'2026-10-31')
        self.assertEqual(plan['todos'][-1]['due'],'2026-11-27')
        self.assertTrue(all(not t['done'] for t in plan['todos']))
        self.assertTrue(all(p['pct']==0 and p['status']=='未开始' for p in plan['progress']))
        self.assertTrue(any('投递' in t['name'] for t in plan['todos'][7:14]))
        self.assertIn('不等同于真实硬件台架经验',plan['notes'][0]['tomorrow'])

    def test_complete_seed_batch_is_recognized_but_real_records_are_kept(self):
        for col,items in self.seed.items():
            if isinstance(items,list):
                for item in items:self.insert(col,item)
        personal = self.insert('courses',dict(self.seed['courses'][0],place='实验楼 301'))
        report=module.migrate(self.db,apply=True)
        self.assertEqual(report['delete_counts']['progress'],13)
        self.assertEqual(report['delete_counts']['courses'],5)
        self.assertFalse(self.read('courses',personal).get('deleted',False))

    def test_unknown_database_is_refused_without_creating_a_new_file(self):
        missing=Path(self.tmp.name)/'missing.db'
        with self.assertRaises(FileNotFoundError):module.migrate(missing,apply=True)
        self.assertFalse(missing.exists())

    def test_shifted_demo_batches_keep_original_fixed_exam_dates(self):
        self.insert('wordBooks',dict(self.seed['wordBooks'][0],createdAt='2026-10-07'))
        self.insert('progress',dict(self.seed['progress'][0],plan='2026-09-17'))
        ddl = self.insert('ddls',self.seed['ddls'][0])
        report=module.migrate(self.db,apply=True)
        self.assertEqual(report['delete_counts']['progress'],1)
        self.assertEqual(report['delete_counts'].get('ddls',0),1)
        self.assertTrue(self.read('ddls',ddl)['deleted'])

if __name__ == '__main__':
    unittest.main()
