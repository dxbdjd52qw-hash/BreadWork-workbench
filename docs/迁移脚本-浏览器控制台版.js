/* ============================================================
 * 麺包的工作台 · localStorage → 云端 数据迁移脚本（一次性）
 * ------------------------------------------------------------
 * 用法：
 *   1. 用「有旧数据」的那台设备/浏览器，打开你部署好的工作台页面
 *      （若旧数据在本地 HTML 文件里，就打开那个本地页面，同样按 F12）
 *   2. 确认已配置接口：AI 抽屉「配置接口」里的 API_KEY 有效
 *   3. F12 → Console → 粘贴本脚本全部内容 → 回车
 *   4. 看日志：每个集合分批写入，全部 ✓ 即完成
 *   5. 其他有旧数据的设备，重复以上步骤（后端按 id+updatedAt 合并，不会重复）
 *
 * 说明：
 *   - meta（单词目标、学习时长等设置项）按现有设计只存本机，不参与云端同步，脚本自动跳过
 *   - mistakes 含 base64 图片，已自动用更小批次（5 条/批）
 *   - 可重复执行：后端 upsert（新者胜），重复跑不会产生脏数据
 * ============================================================ */
(async () => {
  // ---- 配置（一般不用改：自动读取「配置接口」里已保存的值） ----
  const cfg  = JSON.parse(localStorage.getItem('ytwb_cfg') || '{}');
  const BASE = cfg.baseUrl || '';   // 页面与后端同源时留空即可；否则把后端地址填到引号里，如 'http://你的服务器:8000'
  const KEY  = cfg.apiKey  || '';   // 若没配置接口，把 Key 粘贴到引号里

  if (!KEY) { console.error('✗ 未找到 API_KEY：请先在「配置接口」填写并刷新页面，或把 Key 写进脚本第 21 行'); return; }

  const raw = localStorage.getItem('ytwb_v1');
  if (!raw) { console.warn('✗ 本机没有 ytwb_v1 数据，无需迁移'); return; }
  const data = JSON.parse(raw);

  // 与后端 ALLOWED_COLLECTIONS 对齐；meta 是对象不是数组，按设计跳过
  const COLS = ['todos','courses','wordBooks','wordLogs','progress','mistakes','notes','ddls','chatSessions'];
  const batchOf = col => col === 'mistakes' ? 5 : 20;   // base64 图片走小批次

  let ok = 0, fail = 0;
  for (const col of COLS) {
    const items = (Array.isArray(data[col]) ? data[col] : []).filter(x => x && typeof x === 'object');
    if (!items.length) { console.log(`— ${col}: 无数据，跳过`); continue; }
    const B = batchOf(col);
    for (let i = 0; i < items.length; i += B) {
      const chunk = items.slice(i, i + B);
      try {
        const r = await fetch(`${BASE}/api/data/${col}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY },
          body: JSON.stringify({ items: chunk })
        });
        if (!r.ok) {
          fail++;
          console.error(`✗ ${col} 第 ${i / B + 1} 批失败 HTTP ${r.status}:`, await r.text());
          if (r.status === 401) { console.error('  → Key 不对，中止。请核对「配置接口」里的 API_KEY 与服务器 .env 一致'); return; }
          break; // 同集合后续批次意义不大，跳到下一集合
        }
        const j = await r.json();
        ok += j.count || 0;
        console.log(`✓ ${col} 第 ${i / B + 1} 批：写入 ${j.count} 条`);
      } catch (e) {
        fail++;
        console.error(`✗ ${col} 第 ${i / B + 1} 批网络错误:`, e.message, '（服务没跑？跨域？）');
        return;
      }
    }
  }
  console.log(`──────────────────`);
  console.log(fail === 0
    ? `✅ 迁移完成，共写入 ${ok} 条。可执行下方「校验」代码比对条数`
    : `⚠️ 部分失败（成功 ${ok} 条），把上面的红色错误发给我排查`);

  // ---- 校验：拉云端快照，对比各集合条数 ----
  window.__checkMigrate = async () => {
    const r = await fetch(`${BASE}/api/data/snapshot`, { headers: { 'Authorization': 'Bearer ' + KEY } });
    const j = await r.json();
    console.table(COLS.map(col => ({
      集合: col,
      本地: Array.isArray(data[col]) ? data[col].length : 0,
      云端: (j.collections[col] || []).length
    })));
  };
  console.log('校验方法：控制台输入 __checkMigrate() 回车');
})();
