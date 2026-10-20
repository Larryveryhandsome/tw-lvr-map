/* tw-lvr-map 畫面：篩選、地圖、統計、列表。計算都在 lvr.js，資料在 data.js。 */
(function () {
  'use strict';
  const L_ = window.Lvr;
  // data.js 用 const 宣告，不會掛在 window 上，所以用 typeof 檢查
  const D = (typeof LVR_DATA !== 'undefined' && LVR_DATA) || { transactions: [], districts: [] };
  const ALL = D.transactions;
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d) => v == null ? '—' : Number(v).toLocaleString('zh-TW', { maximumFractionDigits: d == null ? 2 : d });
  const COLORS = ['#9aa5ad', '#2c7bb6', '#7fbf7b', '#fdae61', '#d7191c'];
  let sortKey = 'date', sortDir = 'desc', current = [];

  document.title = D.title || document.title;
  $('title').textContent = D.title || '實價登錄地圖';
  $('source').textContent = D.source || '';
  $('generated').textContent = D.generated ? `資料整理日：${D.generated}` : '';

  // ── 篩選欄 ─────────────────────────────────────────────
  const types = [...new Set(ALL.map(t => L_.shortType(t.buildingType)))].sort();
  const checks = (box, items, name) => {
    $(box).innerHTML = items.map(v => `<label class="chip"><input type="checkbox" name="${name}" value="${esc(v)}"> ${esc(v)}</label>`).join('');
  };
  checks('districtBox', D.districts, 'districts');
  checks('typeBox', types, 'types');

  function readFilters() {
    const val = id => $(id).value.trim();
    const picked = name => [...document.querySelectorAll(`input[name=${name}]:checked`)].map(i => i.value);
    return {
      districts: picked('districts'), types: picked('types'),
      dateFrom: val('dateFrom'), dateTo: val('dateTo'),
      priceMin: val('priceMin'), priceMax: val('priceMax'), unitMin: val('unitMin'), unitMax: val('unitMax'),
      areaMin: val('areaMin'), areaMax: val('areaMax'), ageMin: val('ageMin'), ageMax: val('ageMax'),
      keyword: val('keyword'), hideSpecial: $('hideSpecial').checked, buildingsOnly: $('buildingsOnly').checked
    };
  }
  function writeFilters(f) {
    document.querySelectorAll('input[name=districts]').forEach(i => { i.checked = (f.districts || []).includes(i.value); });
    document.querySelectorAll('input[name=types]').forEach(i => { i.checked = (f.types || []).includes(i.value); });
    ['dateFrom', 'dateTo', 'priceMin', 'priceMax', 'unitMin', 'unitMax', 'areaMin', 'areaMax', 'ageMin', 'ageMax', 'keyword']
      .forEach(k => { $(k).value = f[k] || ''; });
    $('hideSpecial').checked = f.hideSpecial === undefined ? true : !!f.hideSpecial;
    $('buildingsOnly').checked = !!f.buildingsOnly;
  }

  // ── 地圖 ───────────────────────────────────────────────
  const map = L.map('map', { preferCanvas: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  const cluster = L.markerClusterGroup({ maxClusterRadius: 45, showCoverageOnHover: false });
  map.addLayer(cluster);
  const pts = ALL.filter(t => t.lat != null);
  if (pts.length) map.fitBounds(pts.map(t => [t.lat, t.lng]), { padding: [30, 30] });
  else map.setView([23.7, 121], 7);

  function popup(t) {
    return `<b>${esc(t.address || '（無門牌）')}</b><br>${esc(t.date)}・${esc(L_.shortType(t.buildingType))}
      <br>總價 <b>${fmt(t.totalPrice, 1)}</b> 萬・單價 <b>${fmt(t.unitPrice)}</b> 萬/坪
      <br>建坪 ${fmt(t.area)}・${t.floor != null ? `${t.floor}/${t.totalFloors ?? '—'} 樓・` : ''}屋齡 ${fmt(t.age, 1)} 年
      ${t.layout ? `<br>${esc(t.layout)}` : ''}${t.parking ? `<br>車位：${esc(t.parking)} ${t.parkingPrice ? fmt(t.parkingPrice, 1) + ' 萬' : ''}` : ''}
      ${t.note ? `<br><span class="note">備註：${esc(t.note)}</span>` : ''}
      ${t.geocoded ? '' : '<br><span class="note">📍 約略位置（行政區中心附近）</span>'}`;
  }

  function renderMap(list) {
    cluster.clearLayers();
    const bands = L_.priceBands(list);
    const markers = list.filter(t => t.lat != null).map(t => L.circleMarker([t.lat, t.lng], {
      radius: 7, weight: t.geocoded ? 1.5 : 1, dashArray: t.geocoded ? null : '2,2', color: '#fff',
      fillColor: COLORS[L_.bandOf(t.unitPrice, bands)], fillOpacity: t.special ? 0.35 : 0.9
    }).bindPopup(popup(t)));
    cluster.addLayers(markers);
    $('legend').innerHTML = `單價（萬/坪）：<i style="background:${COLORS[1]}"></i>&lt;${fmt(bands[0])}
      <i style="background:${COLORS[2]}"></i>&lt;${fmt(bands[1])} <i style="background:${COLORS[3]}"></i>&lt;${fmt(bands[2])}
      <i style="background:${COLORS[4]}"></i>≥${fmt(bands[2])}　虛線＝約略位置`;
    $('offMap').textContent = list.length - markers.length ? `（${list.length - markers.length} 筆沒有座標，只在列表）` : '';
  }

  // ── 統計與列表 ─────────────────────────────────────────
  function renderStats(list) {
    const s = L_.stats(list);
    $('stats').innerHTML = `<div><b>${s.count}</b><span>筆交易</span></div><div><b>${fmt(s.unitMedian)}</b><span>單價中位數（萬/坪）</span></div>
      <div><b>${fmt(s.unitAvg)}</b><span>單價平均</span></div><div><b>${fmt(s.totalMedian, 1)}</b><span>總價中位數（萬）</span></div>`;
    $('byDistrict').innerHTML = Object.entries(s.byDistrict).map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${v.count}</td><td>${fmt(v.unitMedian)}</td></tr>`).join('');
  }

  function renderTable(list) {
    const rows = L_.sortBy(list, sortKey, sortDir).slice(0, 500);
    $('tableHead').innerHTML = L_.COLUMNS.slice(0, 11).map(([k, label]) =>
      `<th data-k="${k}" class="${k === sortKey ? sortDir : ''}">${esc(label)}</th>`).join('');
    $('tableBody').innerHTML = rows.map(t => `<tr${t.special ? ' class="special"' : ''}>${L_.COLUMNS.slice(0, 11).map(([k]) => {
      let v = t[k];
      if (k === 'buildingType') v = L_.shortType(v);
      return `<td>${typeof v === 'number' ? fmt(v) : esc(v || '—')}</td>`;
    }).join('')}</tr>`).join('');
    $('tableNote').textContent = list.length > 500 ? `只顯示前 500 筆（共 ${list.length} 筆），完整資料請匯出 CSV。` : '';
    document.querySelectorAll('#tableHead th').forEach(th => th.addEventListener('click', () => {
      sortDir = sortKey === th.dataset.k && sortDir === 'desc' ? 'asc' : 'desc';
      sortKey = th.dataset.k;
      renderTable(current);
    }));
  }

  function apply(pushUrl) {
    const f = readFilters();
    current = L_.filter(ALL, f);
    renderMap(current); renderStats(current); renderTable(current);
    if (pushUrl) history.replaceState(null, '', '#' + L_.toQuery(f));
  }

  document.querySelectorAll('#filters input').forEach(el => el.addEventListener(el.type === 'checkbox' ? 'change' : 'input', () => apply(true)));
  $('resetBtn').addEventListener('click', () => { writeFilters({ hideSpecial: true }); apply(true); });
  $('csvBtn').addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([L_.toCSV(current)], { type: 'text/csv;charset=utf-8' }));
    a.download = `實價登錄_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
  });
  $('shareBtn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(location.href); $('shareBtn').textContent = '已複製連結 ✓'; }
    catch (e) { prompt('複製這個連結：', location.href); }
    setTimeout(() => { $('shareBtn').textContent = '複製分享連結'; }, 2000);
  });
  $('toggleFilters').addEventListener('click', () => document.body.classList.toggle('show-filters'));

  writeFilters(location.hash.length > 1 ? L_.fromQuery(location.hash.slice(1)) : { hideSpecial: true });
  apply(false);
})();
