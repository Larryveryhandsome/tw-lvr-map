/*
 * tw-lvr-map 純函式：篩選、統計、排序、CSV、網址分享參數。
 * 瀏覽器：window.Lvr；Node：require('./lvr.js')
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Lvr = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /** 建物型態簡稱（開放資料原文很長）。 */
  function shortType(t) {
    const s = String(t || '');
    if (s.includes('住宅大樓')) return '大樓';
    if (s.includes('華廈')) return '華廈';
    if (s.includes('公寓')) return '公寓';
    if (s.includes('透天')) return '透天';
    if (s.includes('套房')) return '套房';
    if (s.includes('店面') || s.includes('店舖')) return '店面';
    if (s.includes('辦公')) return '辦公';
    if (s.includes('工廠') || s.includes('廠辦')) return '廠房';
    return s ? '其他' : '土地/車位';
  }

  const inRange = (v, min, max) => (min == null || min === '' || (v != null && v >= +min)) &&
    (max == null || max === '' || (v != null && v <= +max));

  /**
   * f：{ districts:[], types:[], dateFrom, dateTo, priceMin, priceMax, unitMin, unitMax,
   *      areaMin, areaMax, ageMin, ageMax, keyword, hideSpecial, buildingsOnly }
   */
  function filter(list, f) {
    f = f || {};
    const kw = String(f.keyword || '').trim();
    return list.filter(t =>
      (!f.districts || !f.districts.length || f.districts.includes(t.district)) &&
      (!f.types || !f.types.length || f.types.includes(shortType(t.buildingType))) &&
      (!f.dateFrom || (t.date && t.date >= f.dateFrom)) &&
      (!f.dateTo || (t.date && t.date <= f.dateTo)) &&
      inRange(t.totalPrice, f.priceMin, f.priceMax) &&
      inRange(t.unitPrice, f.unitMin, f.unitMax) &&
      inRange(t.area, f.areaMin, f.areaMax) &&
      inRange(t.age, f.ageMin, f.ageMax) &&
      (!f.hideSpecial || !t.special) &&
      (!f.buildingsOnly || String(t.subject || '').includes('建物')) &&
      (!kw || [t.address, t.district, t.note, t.buildingType].join(' ').includes(kw)));
  }

  function median(nums) {
    const a = nums.filter(n => typeof n === 'number' && isFinite(n)).sort((x, y) => x - y);
    if (!a.length) return null;
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  const round = (n, d) => n == null ? null : Math.round(n * 10 ** d) / 10 ** d;

  /** 統計：筆數、單價中位數／平均（萬/坪）、總價中位數、各區單價中位數。 */
  function stats(list) {
    const units = list.map(t => t.unitPrice).filter(v => v != null);
    const byDistrict = {};
    list.forEach(t => { (byDistrict[t.district] = byDistrict[t.district] || []).push(t.unitPrice); });
    return {
      count: list.length,
      unitMedian: round(median(units), 2),
      unitAvg: units.length ? round(units.reduce((a, b) => a + b, 0) / units.length, 2) : null,
      totalMedian: round(median(list.map(t => t.totalPrice)), 1),
      byDistrict: Object.fromEntries(Object.entries(byDistrict)
        .map(([k, v]) => [k, { count: v.length, unitMedian: round(median(v), 2) }])
        .sort((a, b) => (b[1].unitMedian || 0) - (a[1].unitMedian || 0)))
    };
  }

  function sortBy(list, key, dir) {
    const s = dir === 'asc' ? 1 : -1;
    return list.slice().sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * s;
    });
  }

  /** 單價分級顏色（相對於目前資料的四分位數）。 */
  function priceBands(list) {
    const a = list.map(t => t.unitPrice).filter(v => v != null).sort((x, y) => x - y);
    if (!a.length) return [0, 0, 0];
    const q = p => a[Math.min(a.length - 1, Math.floor(p * a.length))];
    return [q(0.25), q(0.5), q(0.75)];
  }
  function bandOf(v, bands) {
    if (v == null) return 0;
    return v < bands[0] ? 1 : v < bands[1] ? 2 : v < bands[2] ? 3 : 4;
  }

  const COLUMNS = [
    ['date', '交易日期'], ['district', '行政區'], ['address', '地址'], ['buildingType', '建物型態'],
    ['totalPrice', '總價(萬)'], ['unitPrice', '單價(萬/坪)'], ['area', '建坪'], ['floor', '樓層'],
    ['totalFloors', '總樓層'], ['age', '屋齡'], ['layout', '格局'], ['parking', '車位'],
    ['parkingPrice', '車位價(萬)'], ['note', '備註']];

  function toCSV(list) {
    const cell = v => {
      const s = String(v == null ? '' : v);
      // 只有「文字」才防公式注入（= + - @ 與 Tab、CR 開頭）；數字（例如地下一層的 -1）維持數字，不加單引號
      const safe = typeof v === 'string' && /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
      return /[",\n\r\t]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
    };
    return '﻿' + [COLUMNS.map(c => c[1]).join(',')]
      .concat(list.map(t => COLUMNS.map(c => cell(t[c[0]])).join(','))).join('\r\n');
  }

  /** 篩選條件 ↔ 網址參數（分享連結用）。 */
  const ARRAY_KEYS = ['districts', 'types'];
  const BOOL_KEYS = ['hideSpecial', 'buildingsOnly'];
  function toQuery(f) {
    const p = new URLSearchParams();
    Object.entries(f || {}).forEach(([k, v]) => {
      if (ARRAY_KEYS.includes(k)) { if (v && v.length) p.set(k, v.join(',')); }
      else if (BOOL_KEYS.includes(k)) p.set(k, v ? '1' : '0');
      else if (v !== '' && v != null) p.set(k, v);
    });
    return p.toString();
  }
  function fromQuery(q) {
    const p = new URLSearchParams(q);
    const f = {};
    p.forEach((v, k) => {
      if (ARRAY_KEYS.includes(k)) f[k] = v.split(',').filter(Boolean);
      else if (BOOL_KEYS.includes(k)) f[k] = v === '1';
      else f[k] = v;
    });
    return f;
  }

  return { shortType, filter, median, stats, sortBy, priceBands, bandOf, toCSV, toQuery, fromQuery, COLUMNS };
});
