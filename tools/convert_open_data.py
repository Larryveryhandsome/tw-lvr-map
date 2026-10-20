"""把內政部「實價登錄開放資料」CSV 轉成地圖網頁用的 data.js。

資料來源：內政部不動產交易實價查詢服務網 → 開放資料下載
  https://plvr.land.moi.gov.tw/DownloadOpenData
  選「本期（或歷史）」→ 縣市 →「不動產買賣」→ CSV，例如臺北市是 a_lvr_land_a.csv。
授權：政府資料開放授權條款－第 1 版（可自由利用，需標示出處）。

用法：
  python tools/convert_open_data.py 下載的.csv [更多.csv ...] --out data.js
  python tools/convert_open_data.py a_lvr_land_a.csv --geocode --email 你的信箱 --out data.js

--geocode 會用 OpenStreetMap Nominatim 把門牌轉座標（每秒最多 1 筆、結果快取在 data/geocode_cache.json）。
沒加 --geocode 時，有在 districts.json 設定行政區中心點的，會放在中心點附近；都沒有就只出現在列表、不上地圖。
"""
import argparse
import csv
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQM_PER_PING = 3.305785
ATTRIBUTION = "資料來源：內政部不動產交易實價查詢服務網（政府資料開放授權條款－第 1 版）"


def roc_date(s: str):
    """'1130512' 或 '113/05/12' → '2024-05-12'；看不懂回 None。"""
    s = re.sub(r"\D", "", str(s or ""))
    if len(s) < 6:
        return None
    y, m, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
    try:
        return date(y + 1911, m, d).isoformat()
    except ValueError:
        return None


def age_at(build: str, deal_iso: str):
    """建築完成年月（民國）到交易日的屋齡（年，一位小數）。"""
    s = re.sub(r"\D", "", str(build or ""))
    if len(s) < 5 or not deal_iso:
        return None
    y, m = int(s[:-4]) + 1911, int(s[-4:-2]) or 1
    dy, dm = int(deal_iso[:4]), int(deal_iso[5:7])
    months = (dy - y) * 12 + (dm - m)
    return round(months / 12, 1) if 0 <= months < 12 * 150 else None


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


ZH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def zh_floor(s: str):
    """'十二層' → 12、'地下一層' → -1、'全' → None。有好幾層時只取第一個。"""
    s = re.split(r"[，,、]", str(s or ""))[0]
    neg = s.startswith("地下")
    s = s.replace("地下", "").replace("層", "").strip()
    if s.isdigit():
        n = int(s)
    else:
        m = re.fullmatch(r"(?:([一二三四五六七八九])?(十))?([一二三四五六七八九])?", s)
        if not s or not m:
            return None
        n = ((ZH[m.group(1)] if m.group(1) else 1) * 10 if m.group(2) else 0) + ZH.get(m.group(3), 0)
    if not n:
        return None
    return -n if neg else n


def convert_row(r: dict, idx: int):
    """一列開放資料 → 網頁用的一筆交易。不是房地交易（純土地、純車位）也保留，地圖可以篩。"""
    deal = roc_date(r.get("交易年月日"))
    total = num(r.get("總價元"))
    unit_m2 = num(r.get("單價元平方公尺"))
    area_m2 = num(r.get("建物移轉總面積平方公尺"))
    land_m2 = num(r.get("土地移轉總面積平方公尺"))
    park_price = num(r.get("車位總價元")) or 0
    park_m2 = num(r.get("車位移轉總面積平方公尺")) or num(r.get("車位移轉總面積(平方公尺)")) or 0
    rooms = [r.get("建物現況格局-房"), r.get("建物現況格局-廳"), r.get("建物現況格局-衛")]
    note = (r.get("備註") or "").strip()
    return {
        "id": r.get("編號") or f"row-{idx}",
        "district": (r.get("鄉鎮市區") or "").strip(),
        "address": (r.get("土地位置建物門牌") or "").strip(),
        "subject": (r.get("交易標的") or "").strip(),
        "date": deal,
        "buildingType": re.sub(r"\(.*\)", "", r.get("建物型態") or "").strip(),
        "mainUse": (r.get("主要用途") or "").strip(),
        "totalPrice": round(total / 10000, 1) if total else None,               # 萬元
        # 單價：開放資料的單價已扣車位；換成每坪幾萬
        "unitPrice": round(unit_m2 * SQM_PER_PING / 10000, 2) if unit_m2 else None,
        "area": round(area_m2 / SQM_PER_PING, 2) if area_m2 else None,          # 建坪
        "landArea": round(land_m2 / SQM_PER_PING, 2) if land_m2 else None,
        "floor": zh_floor(r.get("移轉層次")),
        "totalFloors": zh_floor(r.get("總樓層數")),
        "age": age_at(r.get("建築完成年月"), deal),
        "layout": "{}房{}廳{}衛".format(*[(x or "0").strip() for x in rooms]) if any(rooms) else "",
        "parking": (r.get("車位類別") or "").strip(),
        "parkingPrice": round(park_price / 10000, 1) if park_price else None,
        "parkingArea": round(park_m2 / SQM_PER_PING, 2) if park_m2 else None,
        "elevator": (r.get("電梯") or "").strip(),
        "note": note,
        # 備註有親友、特殊關係、瑕疵等字眼的，通常不適合拿來比價
        "special": bool(re.search(r"親友|員工|特殊關係|瑕疵|凶宅|債權|急買|急賣|含裝潢|政府機關|法拍", note)),
        "lat": None, "lng": None, "geocoded": False,
    }


def read_csv(path: Path):
    """開放資料 CSV：第 1 列中文欄名、第 2 列英文欄名（略過）。UTF-8（可能有 BOM）。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    body = rows[2:] if len(rows) > 1 and rows[1] and re.match(r"^[A-Za-z ]", rows[1][0] or "") else rows[1:]
    return [dict(zip(head, r)) for r in body if any(c.strip() for c in r)]


class Geocoder:
    """Nominatim：每秒最多 1 筆、要帶可聯絡的 User-Agent、結果快取，避免重複查。"""

    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, cache_path: Path, email: str, county: str = "", sleep=time.sleep, fetch=None):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.ua = f"tw-lvr-map/1.0 ({email})"
        self.county = county
        self.sleep = sleep
        self.fetch = fetch or self._fetch

    def _fetch(self, query):
        url = f"{self.URL}?{urllib.parse.urlencode({'q': query, 'format': 'json', 'countrycodes': 'tw', 'limit': 1})}"
        req = urllib.request.Request(url, headers={"User-Agent": self.ua})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    @staticmethod
    def candidates(address: str, district: str, county: str):
        a = address.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        a = re.sub(r"\d+樓.*$|地下.*$", "", a).strip()
        if county and county not in a:
            a = county + (district if district and district not in a else "") + a
        out = [a]
        road = re.sub(r"\d+(號|弄|巷).*$", "", a)
        if road != a:
            out.append(road)
        return out

    def lookup(self, address, district):
        for q in self.candidates(address, district, self.county):
            if q in self.cache:
                if self.cache[q]:
                    return self.cache[q]
                continue
            try:
                res = self.fetch(q)
            except Exception as e:
                print(f"  查詢失敗：{e}", file=sys.stderr)
                res = None
            self.sleep(1.1)
            self.cache[q] = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
            if self.cache[q]:
                return self.cache[q]
        return None

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def place(rows, centers: dict, geocoder=None, seed=1):
    """有座標就用；沒有就放在行政區中心點附近（隨機偏移，地圖上標成「約略位置」）。"""
    rnd = random.Random(seed)
    for i, t in enumerate(rows):
        if geocoder and t["address"] and "地號" not in t["address"]:
            hit = geocoder.lookup(t["address"], t["district"])
            if hit:
                t["lat"], t["lng"], t["geocoded"] = round(hit[0], 6), round(hit[1], 6), True
                continue
        c = centers.get(t["district"])
        if c:
            t["lat"] = round(c[0] + rnd.uniform(-0.004, 0.004), 6)
            t["lng"] = round(c[1] + rnd.uniform(-0.004, 0.004), 6)
        if geocoder and (i + 1) % 20 == 0:
            geocoder.save()
            print(f"  {i + 1}/{len(rows)}")
    return rows


def write_data_js(rows, out: Path, title: str, source: str = ATTRIBUTION):
    districts = sorted({t["district"] for t in rows if t["district"]})
    payload = {"title": title, "generated": date.today().isoformat(), "source": source,
               "districts": districts, "total": len(rows), "transactions": rows}
    out.write_text("const LVR_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="實價登錄開放資料 CSV → data.js")
    ap.add_argument("csv", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data.js")
    ap.add_argument("--title", default="實價登錄地圖")
    ap.add_argument("--source", default=ATTRIBUTION, help="頁面上顯示的資料來源說明")
    ap.add_argument("--centers", type=Path, default=ROOT / "districts.json", help="行政區中心點設定")
    ap.add_argument("--geocode", action="store_true", help="用 Nominatim 把門牌轉座標（慢，每秒 1 筆）")
    ap.add_argument("--email", default="", help="--geocode 時必填，Nominatim 規定要能聯絡到你")
    ap.add_argument("--county", default="", help="縣市名稱，例如 臺北市（幫助門牌定位）")
    ap.add_argument("--only-buildings", action="store_true", help="只留房地交易（排除純土地、純車位）")
    a = ap.parse_args(argv)

    rows = []
    for p in a.csv:
        raw = read_csv(p)
        rows += [convert_row(r, len(rows) + i) for i, r in enumerate(raw)]
        print(f"{p.name}：{len(raw)} 筆")
    if a.only_buildings:
        rows = [t for t in rows if "建物" in t["subject"]]
    centers = json.loads(a.centers.read_text(encoding="utf-8")).get("centers", {}) if a.centers.exists() else {}
    geo = None
    if a.geocode:
        if "@" not in a.email:
            ap.error("--geocode 需要 --email（Nominatim 使用規範要求可聯絡的 User-Agent）")
        geo = Geocoder(ROOT / "data" / "geocode_cache.json", a.email, a.county)
    place(rows, centers, geo)
    if geo:
        geo.save()
    write_data_js(rows, a.out, a.title, a.source)
    on_map = sum(1 for t in rows if t["lat"] is not None)
    print(f"完成：{len(rows)} 筆，地圖上 {on_map} 筆（精確 {sum(t['geocoded'] for t in rows)}）→ {a.out}")


if __name__ == "__main__":
    main()
