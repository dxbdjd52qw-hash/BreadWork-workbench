const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function loadApp(saved) {
  const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
  const script = html.split('<script>')[1].split('/* ---------- 背景：')[0];
  const storage = new Map(saved ? [['ytwb_v1', JSON.stringify(saved)]] : []);
  const elements = new Map();
  const context = vm.createContext({
    location: { protocol: 'file:', origin: '', hash: '' },
    localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
    document: { querySelector: s => {
      if (!elements.has(s)) elements.set(s, { innerHTML: '', textContent: '', classList: { toggle() {} } });
      return elements.get(s);
    } },
    window: { addEventListener() {} },
    setTimeout: () => 1, clearTimeout() {}, console,
  });
  vm.runInContext(script, context);
  vm.runInContext('Store.load()', context);
  return { context, elements, run: source => vm.runInContext(source, context) };
}

test('a fresh device starts empty without fabricated study history', () => {
  const app = loadApp();
  const data = JSON.parse(app.run('JSON.stringify(Store.data)'));
  for (const col of ['todos','courses','wordBooks','wordLogs','progress','notes','ddls','mistakes','chatSessions']) {
    assert.equal(data[col].length, 0, col + ' must start empty');
  }
  assert.equal(Object.values(data.meta.studyMinutes).reduce((a, b) => a + b, 0), 0);
});

test('loading an existing device preserves real records and their progress', () => {
  const existing = { meta: { updatedAt: '2026-10-01', studyMinutes: { '其他': 25 } },
    todos: [{ id: 'personal', name: '实验室组会', done: true }], mistakes: [],
    progress: [{ id: 'personal-progress', subject: '数学', pct: 60 }] };
  const app = loadApp(existing);
  assert.deepEqual(JSON.parse(app.run('JSON.stringify(Store.data)')), existing);
});

test('known fabricated study minutes are cleared while genuine totals survive', () => {
  const app = loadApp({meta:{studyMinutes:{'数学':320,'英语':260,'政治':90,'单词':180,'其他':60}},mistakes:[]});
  assert.equal(app.run("Object.values(Store.data.meta.studyMinutes).reduce((a,b)=>a+b,0)"),0);
  const real = loadApp({meta:{studyMinutes:{'数学':345,'英语':260,'政治':90,'单词':180,'其他':60}},mistakes:[]});
  assert.equal(real.run("Store.data.meta.studyMinutes['数学']"),345);
});

test('every existing module can render a fresh empty device', () => {
  const app = loadApp();
  for (const name of ['renderHome','renderTodos','renderCourses','renderWords','renderProgress','renderMis','renderNotes','renderDash','renderDdl']) {
    assert.doesNotThrow(() => app.run(name+'()'), name);
  }
});

test('completing a testing task counts its time under testing instead of mathematics', () => {
  const app = loadApp();
  app.run("Store.data.todos=[{id:'testing-task',name:'CAN',cat:'测试开发',done:false}]; Todo.done('testing-task')");
  assert.equal(app.run("Store.data.meta.studyMinutes['测试开发']"),25);
  assert.equal(app.run("Store.data.meta.studyMinutes['数学']"),0);
});

test('testing progress is visible and empty exam subjects do not dilute its average', () => {
  const app = loadApp();
  app.run(`Store.data.progress = [
    {id:'w1', subject:'测试开发', sub:'第 1 周 · Python / pytest', name:'Python', pct:100, status:'已掌握', plan:'2026-11-06'},
    {id:'w2', subject:'测试开发', sub:'第 2 周 · CAN / DBC', name:'CAN', pct:0, status:'未开始', plan:'2026-11-13'},
    {id:'w3', subject:'测试开发', sub:'第 3 周 · HIL / 嵌入式', name:'HIL', pct:0, status:'未开始', plan:'2026-11-20'},
    {id:'w4', subject:'测试开发', sub:'第 4 周 · 项目 / 实习', name:'项目', pct:0, status:'未开始', plan:'2026-11-27'},
    {id:'old', subject:'数学', pct:100, deleted:true}
  ]; curModule='progress'; Prog.subj('测试开发');`);
  assert.equal(app.run('overallProgress()'), 25);
  assert.match(app.elements.get('#view').innerHTML, /CAN/);
  app.run('renderDash()');
  assert.match(app.elements.get('#view').innerHTML, /25%/);
  assert.match(app.elements.get('#view').innerHTML, /测试开发/);
  app.run('renderHome()');
  assert.match(app.elements.get('#view').innerHTML, /25%/);
});

test('existing exam progress still contributes alongside testing progress', () => {
  const app = loadApp();
  app.run(`Store.data.progress = [
    {id:'math',subject:'数学',pct:100}, {id:'testing',subject:'测试开发',pct:50}
  ]`);
  assert.equal(app.run('overallProgress()'), 75);
  app.run('Store.data.progress = []');
  assert.equal(app.run('overallProgress()'), 0);
});

test('empty exam categories can still be selected and receive new entries', () => {
  const app = loadApp();
  app.run("Store.data.progress=[{id:'testing',subject:'测试开发',sub:'第 1 周 · Python / pytest',name:'Python',pct:0,plan:'2026-11-06',status:'未开始'}]; curModule='progress'; Prog.subj('数学'); Prog.edit()");
  assert.match(app.elements.get('#modalRoot').innerHTML, /selected[^>]*>数学/);
});

test('a learning plan is editable as a plan and does not count as today\'s completed review', () => {
  const app = loadApp();
  app.run(`Store.data.notes = [{id:'plan',date:todayStr(),type:'学习计划',mood:'',
    done:'汽车测试开发四周计划',problem:'每周六天',improve:'Python 官方文档',tomorrow:'完成仿真项目'}];
    renderHome();`);
  assert.match(app.elements.get('#view').innerHTML, /今天还没写/);
  assert.match(app.elements.get('#view').innerHTML, /汽车测试开发四周计划/);
  app.run(`Notes.edit('plan')`);
  assert.match(app.elements.get('#modalRoot').innerHTML, /计划目标/);
  assert.match(app.elements.get('#modalRoot').innerHTML, /学习安排/);
  assert.match(app.elements.get('#modalRoot').innerHTML, /selected[^>]*>学习计划/);
});

test('the deployed frontend matches the editable source', () => {
  assert.equal(fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8'),
    fs.readFileSync(path.join(__dirname, '../backend/static/index.html'), 'utf8'));
});
