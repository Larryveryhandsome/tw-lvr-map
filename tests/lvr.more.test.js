const test = require('node:test');
const assert = require('node:assert');
const L = require('../js/lvr.js');

test('CSV 防公式：文字的 = + - @ Tab CR 開頭加單引號；數字（地下樓層 -1）維持數字', () => {
  const csv = L.toCSV([{ date: '2025-01-01', address: '+SUM(1)', note: '@cmd', layout: '-2+3', parking: '\t=1', buildingType: '\r=2', floor: -1, age: 0 }]);
  assert.ok(csv.includes("'+SUM(1)"));
  assert.ok(csv.includes("'@cmd"));
  assert.ok(csv.includes("'-2+3"));
  assert.ok(csv.includes('"\'\t=1"'), '開頭是 Tab 的也要處理');
  assert.ok(csv.includes('"\'\r=2"'), '開頭是 CR 的也要處理');
  const line = csv.split('\r\n')[1];
  assert.ok(/,-1,/.test(line) && !line.includes("'-1"), line);   // floor = -1 沒被加單引號
});

test('大量資料（20 萬筆）：篩選、統計、排序在合理時間內', () => {
  const big = Array.from({ length: 200000 }, (_, i) => ({
    district: 'D' + (i % 12), buildingType: '住宅大樓', subject: i % 5 ? '房地(土地+建物)' : '土地',
    date: '2025-0' + (1 + i % 9) + '-01', totalPrice: 500 + (i % 3000), unitPrice: 20 + (i % 80),
    area: 20 + (i % 60), age: i % 40, address: '路' + i, note: '', special: i % 17 === 0
  }));
  const t = Date.now();
  const cur = L.filter(big, { hideSpecial: true, buildingsOnly: true, keyword: '路1' });
  const s = L.stats(L.filter(big, { buildingsOnly: true }));
  L.sortBy(cur, 'date', 'desc');
  assert.ok(cur.length > 0 && s.count === 160000);
  assert.ok(Date.now() - t < 5000, `太慢：${Date.now() - t}ms`);
});

test('單價中位數：只看建物時不被純土地單價拉低（UI 預設即為只看建物）', () => {
  const rows = [
    { district: 'A', subject: '房地(土地+建物)', unitPrice: 50, totalPrice: 1500 },
    { district: 'A', subject: '房地(土地+建物)', unitPrice: 54, totalPrice: 1600 },
    { district: 'A', subject: '土地', unitPrice: 8, totalPrice: 800 },
    { district: 'A', subject: '土地', unitPrice: 9, totalPrice: 700 },
  ];
  assert.strictEqual(L.stats(L.filter(rows, {})).unitMedian, 29.5);
  assert.strictEqual(L.stats(L.filter(rows, { buildingsOnly: true })).unitMedian, 52);
});
