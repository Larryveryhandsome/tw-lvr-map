// 用假的 DOM 跑 js/app.js：資料（來自 CSV，可能被惡意填寫）不能變成 HTML 標籤。不需要瀏覽器或額外套件。
const test = require('node:test');
const assert = require('node:assert');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const L = require('../js/lvr.js');

const PAYLOADS = [
  '<img src=x onerror="window.__pwned=1">',
  '<script>window.__pwned=1</script>',
  '"><svg onload=alert(1)>',
  "' onfocus='alert(1)' autofocus='",
  '</td><td><iframe src=javascript:alert(1)>',
];

function run(transactions, districts) {
  const els = {};
  const popups = [];
  const el = id => (els[id] = els[id] || {
    id, value: '', checked: false, textContent: '', innerHTML: '', dataset: {}, classList: { toggle() {} },
    addEventListener() {}, appendChild() {}, click() {}, remove() {},
  });
  els.hideSpecial = { checked: true, value: '', addEventListener() {} };
  const marker = { bindPopup(h) { popups.push(h); return marker; } };
  const layerGroup = { clearLayers() {}, addLayers() {} };
  const ctx = {
    console, setTimeout, clearTimeout, Number, String, Object, Array, Set, Math, Date, URL: { createObjectURL: () => '' },
    Blob: function () {}, prompt() {}, navigator: {},
    document: { title: '', getElementById: el, querySelectorAll: () => [], createElement: () => el('a'), body: el('body') },
    location: { hash: '', href: 'http://x/' }, history: { replaceState() {} },
    L: {
      map: () => ({ addLayer() {}, fitBounds() {}, setView() {} }),
      tileLayer: () => ({ addTo() {} }), markerClusterGroup: () => layerGroup, circleMarker: () => marker,
    },
    LVR_DATA: { title: PAYLOADS[0], source: PAYLOADS[1], generated: '2025-01-01', districts, transactions },
  };
  ctx.window = ctx;
  ctx.Lvr = L;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'js', 'app.js'), 'utf8'), ctx);
  return { els, popups, ctx };
}

test('惡意 CSV 內容：欄位、列表、勾選項、彈窗都被跳脫，不會長出標籤', () => {
  const tx = PAYLOADS.map((p, i) => ({
    id: 'T' + i, district: p, address: p, subject: '房地(土地+建物)', date: p, buildingType: p, mainUse: p,
    totalPrice: 1000, unitPrice: 30, area: 30, floor: p, totalFloors: p, age: 5, layout: p, parking: p,
    parkingPrice: 10, note: p, special: false, lat: 24, lng: 121, geocoded: true,
  }));
  const { els, popups, ctx } = run(tx, PAYLOADS);
  const htmlOut = [els.districtBox.innerHTML, els.typeBox.innerHTML, els.tableBody.innerHTML, els.tableHead.innerHTML,
    els.byDistrict.innerHTML, els.stats.innerHTML, els.legend.innerHTML, ...popups];
  assert.ok(popups.length === PAYLOADS.length, '應該有彈窗內容');
  assert.ok(els.tableBody.innerHTML.length > 0 && els.districtBox.innerHTML.length > 0);
  for (const h of htmlOut) {
    assert.doesNotMatch(h, /<\s*(img|script|svg|iframe)/i, h.slice(0, 200));
    assert.doesNotMatch(h, /["']\s+on\w+\s*=/i, h.slice(0, 200));   // 沒有屬性被跳出來
  }
  assert.strictEqual(ctx.__pwned, undefined);
  // 標題與來源用 textContent（不是 innerHTML）
  assert.strictEqual(els.title.textContent, PAYLOADS[0]);
  assert.strictEqual(els.title.innerHTML, '');
});

test('資料多時地圖最多畫 5000 個點，並提示', () => {
  const tx = Array.from({ length: 6000 }, (_, i) => ({
    id: 'N' + i, district: '甲', address: 'a', subject: '房地(土地+建物)', date: '2025-01-01', buildingType: '公寓',
    totalPrice: 1, unitPrice: 1, area: 1, lat: 24, lng: 121, geocoded: true, special: false,
  }));
  const { els, popups } = run(tx, ['甲']);
  assert.strictEqual(popups.length, 5000);
  assert.match(els.offMap.textContent, /5000/);
  assert.match(els.tableNote.textContent, /500/);
});
