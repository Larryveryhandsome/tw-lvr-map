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
import codecs
import csv
import os
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
    if y >= 1900:   # 已經是西元（例如 20240512）就不要再加 1911
        y -= 1911
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


REQUIRED = ["鄉鎮市區", "交易年月日", "總價元", "土地位置建物門牌"]
IMPORTANT = ["交易標的", "單價元平方公尺", "建物移轉總面積平方公尺", "編號"]
ALIASES = {  # 欄名改版／寫法不同時對回標準欄名（比對前先去空白、全形括號轉半形）
    "單價元/平方公尺": "單價元平方公尺", "單價(元/平方公尺)": "單價元平方公尺", "單價元每平方公尺": "單價元平方公尺",
    "車位移轉總面積(平方公尺)": "車位移轉總面積平方公尺", "車位移轉總面積(m2)": "車位移轉總面積平方公尺",
    "建物移轉總面積(平方公尺)": "建物移轉總面積平方公尺", "土地移轉總面積(平方公尺)": "土地移轉總面積平方公尺",
    "建物現況格局-房": "建物現況格局-房", "建物現況格局－房": "建物現況格局-房",
    "建物現況格局-廳": "建物現況格局-廳", "建物現況格局－廳": "建物現況格局-廳",
    "建物現況格局-衛": "建物現況格局-衛", "建物現況格局－衛": "建物現況格局-衛",
    "總價(元)": "總價元", "交易年月日(民國)": "交易年月日", "鄉鎮市區名稱": "鄉鎮市區",
}


def norm_header(h: str) -> str:
    h = re.sub(r"\s+", "", str(h or "")).replace("（", "(").replace("）", ")").replace("／", "/")
    return ALIASES.get(h, h)


class CsvFormatError(ValueError):
    pass


def detect_encoding(path: Path) -> str:
    """開放資料通常是 UTF-8（可能有 BOM）；舊檔或另存過的可能是 Big5（cp950）。取檔頭 2MB 試解。"""
    with open(path, "rb") as f:
        sample = f.read(2 * 1024 * 1024)
    try:
        codecs.getincrementaldecoder("utf-8-sig")().decode(sample, final=False)
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp950"


def check_columns(head, name=""):
    """必要欄位缺了就明確報錯（不要默默轉出一堆空資料）；次要欄位缺了只警告。"""
    have = set(head)
    miss = [c for c in REQUIRED if c not in have]
    if miss:
        raise CsvFormatError(
            f"{name} 缺少必要欄位：{'、'.join(miss)}。這可能不是「不動產買賣」CSV（預售屋、租賃的欄位不同），"
            f"或政府改版了欄名。檔案的欄位開頭是：{'、'.join(head[:8])}…")
    weak = [c for c in IMPORTANT if c not in have]
    if weak:
        print(f"  警告：{name} 找不到欄位 {'、'.join(weak)}，對應的資料會是空的", file=sys.stderr)


def iter_csv(path: Path):
    """逐列讀開放資料 CSV（不把整個檔案載進記憶體）：第 1 列中文欄名、第 2 列英文欄名（略過）。"""
    enc = detect_encoding(path)
    if enc != "utf-8-sig":
        print(f"  {path.name} 不是 UTF-8，改用 Big5 讀取", file=sys.stderr)
    with open(path, encoding=enc, errors="replace", newline="") as f:
        reader = csv.reader(f)
        first = next(reader, None)
        if not first:
            return
        head = [norm_header(h) for h in first]
        check_columns(head, path.name)
        second = True
        for r in reader:
            if second:
                second = False
                if r and re.match(r"^[A-Za-z ]", r[0] or ""):
                    continue   # 英文欄名那一列
            if any(c.strip() for c in r):
                yield dict(zip(head, r))


def read_csv(path: Path):
    """相容舊介面：整份讀成 list（小檔、測試用；大檔請用 iter_csv）。"""
    return list(iter_csv(path))


class Geocoder:
    """Nominatim：每秒最多 1 筆、要帶可聯絡的 User-Agent、結果快取，避免重複查。"""

    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, cache_path: Path, email: str, county: str = "", sleep=time.sleep, fetch=None):
        self.cache_path = cache_path
        self.cache = self._load(cache_path)
        self.fail_streak = 0
        self.ua = f"tw-lvr-map/1.0 ({email})"
        self.county = county
        self.sleep = sleep
        self.fetch = fetch or self._fetch

    @staticmethod
    def _load(path: Path) -> dict:
        """快取壞了（例如寫到一半被中斷）不要讓整個轉換掛掉：壞檔改名保留，重新開始。"""
        if not path.exists():
            return {}
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
        try:
            os.replace(path, path.with_name(path.name + f".bad{int(time.time())}"))
        except OSError:
            pass
        print(f"  座標快取 {path.name} 損毀，已改名保留並重新開始", file=sys.stderr)
        return {}

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
                # 網路錯誤、429 被限流：不寫進快取（否則這個地址永遠被當成「查無」），並退避；連續失敗就中止
                self.fail_streak += 1
                print(f"  查詢失敗（連續第 {self.fail_streak} 次）：{e}", file=sys.stderr)
                if self.fail_streak >= 5:
                    raise RuntimeError("Nominatim 連續失敗 5 次（可能被限流或沒網路），已中止；已查到的座標都在快取裡，稍後重跑會接著做")
                self.sleep(min(60, 5 * 2 ** self.fail_streak))
                return None
            self.fail_streak = 0
            self.sleep(1.1)
            self.cache[q] = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
            if self.cache[q]:
                return self.cache[q]
        return None

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_name(self.cache_path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.cache_path)   # 原子寫入：中途被中斷也不會留下半個檔


def place_iter(rows, centers: dict, geocoder=None, seed=1):
    """有座標就用；沒有就放在行政區中心點附近（隨機偏移，地圖上標成「約略位置」）。逐筆處理，可吃產生器。"""
    rnd = random.Random(seed)
    for i, t in enumerate(rows):
        placed = False
        if geocoder and t["address"] and "地號" not in t["address"]:
            hit = geocoder.lookup(t["address"], t["district"])
            if hit:
                t["lat"], t["lng"], t["geocoded"] = round(hit[0], 6), round(hit[1], 6), True
                placed = True
        if not placed:
            c = centers.get(t["district"])
            if c:
                t["lat"] = round(c[0] + rnd.uniform(-0.004, 0.004), 6)
                t["lng"] = round(c[1] + rnd.uniform(-0.004, 0.004), 6)
        if geocoder and (i + 1) % 20 == 0:
            geocoder.save()
            print(f"  {i + 1} 筆")
        yield t


def place(rows, centers: dict, geocoder=None, seed=1):
    """相容舊介面：就地處理一份 list。"""
    for _ in place_iter(rows, centers, geocoder, seed):
        pass
    return rows


def write_data_js(rows, out: Path, title: str, source: str = ATTRIBUTION):
    """串流寫出 data.js（rows 可以是 list 或產生器，不會把全部資料組成一個大字串）；先寫暫存檔再取代。回傳筆數。"""
    tmp = out.with_name(out.name + f".{os.getpid()}.tmp")
    districts, n = set(), 0
    head = {"title": title, "generated": date.today().isoformat(), "source": source}
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("const LVR_DATA = " + json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1] + ',"transactions":[')
        for t in rows:
            f.write(("," if n else "") + json.dumps(t, ensure_ascii=False, separators=(",", ":")))
            n += 1
            if t.get("district"):
                districts.add(t["district"])
        f.write('],"districts":' + json.dumps(sorted(districts), ensure_ascii=False) + f',"total":{n}' + "};\n")
    os.replace(tmp, out)
    return n


def parse_since(v: str):
    iso = roc_date(v) if re.fullmatch(r"\d{6,7}", v or "") else (v or None)
    if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso or ""):
        raise argparse.ArgumentTypeError("--since 請用 2024-01-01 或民國 1130101 的格式")
    return iso


def rows_from(paths, only_buildings=False, since=None, stats=None):
    """逐列讀取 → 轉換 → 去重（同一個編號只留一筆；多份 CSV 的期間重疊時不會重複計算）→ 篩選。"""
    seen, idx = set(), 0
    stats = stats if stats is not None else {}
    for p in paths:
        n = 0
        for r in iter_csv(p):
            n += 1
            t = convert_row(r, idx)
            idx += 1
            if t["id"] in seen:
                stats["dup"] = stats.get("dup", 0) + 1
                continue
            seen.add(t["id"])
            if only_buildings and "建物" not in t["subject"]:
                continue
            if since and not (t["date"] and t["date"] >= since):
                continue
            yield t
        print(f"{p.name}：{n} 筆")


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
    ap.add_argument("--since", type=parse_since, default=None, help="只留這個日期之後的交易，例如 2024-01-01 或 1130101")
    a = ap.parse_args(argv)

    centers = json.loads(a.centers.read_text(encoding="utf-8")).get("centers", {}) if a.centers.exists() else {}
    geo = None
    if a.geocode:
        if "@" not in a.email:
            ap.error("--geocode 需要 --email（Nominatim 使用規範要求可聯絡的 User-Agent）")
        geo = Geocoder(ROOT / "data" / "geocode_cache.json", a.email, a.county)
    counts = {"rows": 0, "on_map": 0, "exact": 0}
    stats = {}

    def counted(it):
        for t in it:
            counts["rows"] += 1
            counts["on_map"] += t["lat"] is not None
            counts["exact"] += bool(t["geocoded"])
            yield t
    try:
        write_data_js(counted(place_iter(rows_from(a.csv, a.only_buildings, a.since, stats), centers, geo)),
                      a.out, a.title, a.source)
    except CsvFormatError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    finally:
        if geo:
            geo.save()
    if stats.get("dup"):
        print(f"略過重複編號 {stats['dup']} 筆")
    size_mb = a.out.stat().st_size / 1024 ** 2
    print(f"完成：{counts['rows']} 筆，地圖上 {counts['on_map']} 筆（精確 {counts['exact']}）→ {a.out}（{size_mb:.1f} MB）")
    if counts["rows"] > 100_000 or size_mb > 40:
        print(f"注意：資料很大（{counts['rows']} 筆、{size_mb:.0f} MB），瀏覽器會載入很慢甚至當掉。"
              "建議加 --only-buildings、--since（例如只留最近兩年）或分縣市／分區各做一份。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
