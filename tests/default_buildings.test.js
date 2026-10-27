// 決策 #9：實價登錄統計「預設只算有建物的交易」。這支測試防止日後被悄悄改回去。
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const L = require('../js/lvr.js');
const root = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(root, f), 'utf8');

test('頁面上的「只看有建物」勾選預設是勾起來的', () => {
  assert.match(read('index.html'), /<input[^>]*id="buildingsOnly"[^>]*\bchecked\b/);
});

test('程式：網址沒指定時，預設為只看有建物', () => {
  assert.match(read('js/app.js'), /buildingsOnly'\)\.checked\s*=\s*f\.buildingsOnly\s*===\s*undefined\s*\?\s*true/);
  assert.strictEqual(L.fromQuery('').buildingsOnly, undefined); // 沒指定 → 交給預設（true）
  assert.strictEqual(L.fromQuery('buildingsOnly=0').buildingsOnly, false); // 使用者主動取消要尊重
});

test('預設開啟時，純土地、純車位不進統計；取消後才進', () => {
  const rows = [
    { subject: '房地(土地+建物)', unitPrice: 50, date: '2025-01-01' },
    { subject: '房地(土地+建物)+車位', unitPrice: 52, date: '2025-01-02' },
    { subject: '土地', unitPrice: 5, date: '2025-01-03' },
    { subject: '車位', unitPrice: 1, date: '2025-01-04' },
  ];
  assert.strictEqual(L.filter(rows, { buildingsOnly: true }).length, 2);
  assert.strictEqual(L.filter(rows, { buildingsOnly: false }).length, 4);
  assert.strictEqual(L.stats(L.filter(rows, { buildingsOnly: true })).unitMedian, 51);
});

test('README 有寫預設只統計建物、以及怎麼取消', () => {
  const md = read('README.md');
  assert.match(md, /網頁預設只統計「有建物」的交易/);
  assert.match(md, /取消勾選/);
});
