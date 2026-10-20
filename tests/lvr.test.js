const test = require('node:test');
const assert = require('node:assert');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const L = require('../js/lvr.js');

const ctx = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'data.js'), 'utf8') + ';this.D=LVR_DATA;', ctx);
const D = ctx.D;

const T = [
  { district: '甲區', buildingType: '住宅大樓(11層含以上有電梯)', subject: '房地(土地+建物)', date: '2025-03-01', totalPrice: 1200, unitPrice: 40, area: 30, age: 5, address: '示範路1號', note: '' },
  { district: '乙區', buildingType: '公寓(5樓含以下無電梯)', subject: '房地(土地+建物)', date: '2025-06-01', totalPrice: 800, unitPrice: 25, area: 32, age: 35, address: '測試街2號', note: '親友間交易', special: true },
  { district: '甲區', buildingType: '透天厝', subject: '房地(土地+建物)', date: '2024-12-01', totalPrice: 2000, unitPrice: null, area: 60, age: 20, address: '示範路9號', note: '' },
  { district: '乙區', buildingType: '', subject: '土地', date: '2025-01-01', totalPrice: 500, unitPrice: null, area: null, age: null, address: '某段1地號', note: '' }
];

test('示範資料：格式正確、明確標示虛構', () => {
  assert.ok(D.transactions.length >= 100);
  assert.match(D.source, /虛構/);
  for (const t of D.transactions) {
    assert.ok(t.address.startsWith('示範'), t.address);
    assert.ok(t.lat > 20 && t.lat < 27 && t.lng > 118 && t.lng < 123);
  }
});

test('建物型態簡稱', () => {
  assert.deepStrictEqual(T.map(t => L.shortType(t.buildingType)), ['大樓', '公寓', '透天', '土地/車位']);
  assert.strictEqual(L.shortType('店面(店鋪)'), '店面');
});

test('篩選：區、型態、日期、價格範圍、關鍵字、特殊交易', () => {
  assert.strictEqual(L.filter(T, {}).length, 4);
  assert.strictEqual(L.filter(T, { districts: ['甲區'] }).length, 2);
  assert.strictEqual(L.filter(T, { types: ['公寓', '透天'] }).length, 2);
  assert.strictEqual(L.filter(T, { dateFrom: '2025-01-01', dateTo: '2025-05-31' }).length, 2);
  assert.strictEqual(L.filter(T, { priceMin: '900', priceMax: '1500' }).length, 1);
  assert.strictEqual(L.filter(T, { unitMin: 30 }).length, 1);
  assert.strictEqual(L.filter(T, { keyword: '示範路' }).length, 2);
  assert.strictEqual(L.filter(T, { hideSpecial: true }).length, 3);
  assert.strictEqual(L.filter(T, { buildingsOnly: true }).length, 3);
});

test('統計：中位數、平均、各區', () => {
  assert.strictEqual(L.median([3, 1, 2]), 2);
  assert.strictEqual(L.median([4, 1, 3, 2]), 2.5);
  assert.strictEqual(L.median([null, undefined]), null);
  const s = L.stats(T);
  assert.deepStrictEqual([s.count, s.unitMedian, s.unitAvg, s.totalMedian], [4, 32.5, 32.5, 1000]);
  assert.deepStrictEqual(Object.keys(s.byDistrict), ['甲區', '乙區']);
  assert.strictEqual(s.byDistrict['甲區'].count, 2);
});

test('排序：空值永遠排最後', () => {
  assert.deepStrictEqual(L.sortBy(T, 'unitPrice', 'desc').map(t => t.unitPrice), [40, 25, null, null]);
  assert.deepStrictEqual(L.sortBy(T, 'unitPrice', 'asc').map(t => t.unitPrice), [25, 40, null, null]);
  assert.strictEqual(L.sortBy(T, 'date', 'desc')[0].date, '2025-06-01');
});

test('單價分級', () => {
  const b = L.priceBands(D.transactions);
  assert.ok(b[0] <= b[1] && b[1] <= b[2]);
  assert.strictEqual(L.bandOf(null, b), 0);
  assert.strictEqual(L.bandOf(-1, b), 1);
  assert.strictEqual(L.bandOf(1e9, b), 4);
});

test('CSV：BOM、欄名、引號、防公式', () => {
  const csv = L.toCSV([{ date: '2025-01-01', address: '甲,乙', note: '=1+1' }]);
  assert.ok(csv.startsWith('﻿交易日期,'));
  assert.ok(csv.includes('"甲,乙"'));
  assert.ok(csv.includes("'=1+1"));
});

test('網址參數來回轉換（含關閉的勾選）', () => {
  const f = { districts: ['甲區', '乙區'], types: [], priceMin: '500', keyword: '', hideSpecial: false, buildingsOnly: true };
  const back = L.fromQuery(L.toQuery(f));
  assert.deepStrictEqual(back, { districts: ['甲區', '乙區'], priceMin: '500', hideSpecial: false, buildingsOnly: true });
});
