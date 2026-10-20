"""產生「虛構」的示範資料：格式和內政部實價登錄開放資料 CSV 一樣，內容全是亂數。

地址都是「示範○區示範路」這種不存在的地址，價格是隨機產生的，不代表任何真實行情。
用法：python tools/make_sample.py  → sample/demo_lvr_land_a.csv
"""
import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD_ZH = ["鄉鎮市區", "交易標的", "土地位置建物門牌", "土地移轉總面積平方公尺", "都市土地使用分區", "非都市土地使用分區",
           "非都市土地使用編定", "交易年月日", "交易筆棟數", "移轉層次", "總樓層數", "建物型態", "主要用途", "主要建材",
           "建築完成年月", "建物移轉總面積平方公尺", "建物現況格局-房", "建物現況格局-廳", "建物現況格局-衛",
           "建物現況格局-隔間", "有無管理組織", "總價元", "單價元平方公尺", "車位類別", "車位移轉總面積(平方公尺)",
           "車位總價元", "備註", "編號", "主建物面積", "附屬建物面積", "陽台面積", "電梯", "移轉編號"]
HEAD_EN = ["The villages and towns urban district", "transaction sign", "land sector position building sector house number plate",
           "land shifting total area square meter", "the use zoning or compiles and checks", "the non-metropolis land use district",
           "non-metropolis land use", "transaction year month and day", "transaction pen number", "shifting level",
           "total floor number", "building state", "main use", "main building materials", "construction to complete the years",
           "building shifting total area", "Building present situation pattern - room", "building present situation pattern - hall",
           "building present situation pattern - health", "building present situation pattern - compartmented",
           "Whether there is manages the organization", "total price NTD", "the unit price (NTD / square meter)",
           "the berth category", "berth shifting total area square meter", "the berth total price NTD", "the note",
           "serial number", "main building area", "auxiliary building area", "balcony area", "elevator", "transaction number"]
DISTRICTS = {"示範東區": 1.15, "示範西區": 1.0, "示範南區": 0.85, "示範北區": 1.05}
TYPES = [("住宅大樓(11層含以上有電梯)", 0.4, (11, 28)), ("華廈(10層含以下有電梯)", 0.25, (6, 10)),
         ("公寓(5樓含以下無電梯)", 0.15, (4, 5)), ("透天厝", 0.15, (2, 4)), ("套房(1房1廳1衛)", 0.05, (8, 15))]
ZH = "一二三四五六七八九"


def zh(n):
    if n < 10:
        return ZH[n - 1]
    return ("" if n < 20 else ZH[n // 10 - 1]) + "十" + (ZH[n % 10 - 1] if n % 10 else "")


def make(n=160, seed=20261020):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        dist = rnd.choice(list(DISTRICTS))
        btype, _, (fmin, fmax) = rnd.choices(TYPES, weights=[t[1] for t in TYPES])[0]
        total_floors = rnd.randint(fmin, fmax)
        floor = rnd.randint(1, total_floors)
        age = rnd.choice([0, 1, 2, 5, 8, 12, 18, 25, 32, 40])
        build_y = 114 - age
        m2 = round(rnd.uniform(25, 60) if "套房" in btype else rnd.uniform(70, 200), 2)
        unit = int(rnd.uniform(80000, 200000) * DISTRICTS[dist] * (1.15 if age <= 2 else 1 - min(age, 40) / 120))
        has_park = "大樓" in btype or "華廈" in btype and rnd.random() < 0.6
        park_m2 = round(rnd.uniform(30, 40), 2) if has_park else 0
        park_price = rnd.choice([1500000, 1800000, 2200000]) if has_park else 0
        total = int(unit * (m2 - park_m2) + park_price)
        rooms = 1 if "套房" in btype else rnd.choice([2, 3, 3, 4])
        mo, d = rnd.randint(1, 9), rnd.randint(1, 28)
        note = rnd.choice([""] * 12 + ["親友、員工、共有人或其他特殊關係間之交易。", "含增建或未登記建物。"])
        rows.append([
            dist, "房地(土地+建物)+車位" if has_park else "房地(土地+建物)",
            f"{dist}示範路{rnd.randint(1, 3)}段{rnd.randint(1, 300)}號" + ("" if "透天" in btype else f"{floor}樓"),
            round(m2 * rnd.uniform(0.08, 0.6), 2), "住", "", "", f"114{mo:02d}{d:02d}", "土地1建物1車位" + ("1" if has_park else "0"),
            "全" if "透天" in btype else f"{zh(floor)}層", f"{zh(total_floors)}層", btype, "住家用", "鋼筋混凝土造",
            f"{build_y:03d}{rnd.randint(1, 12):02d}{rnd.randint(1, 28):02d}", m2, rooms, rnd.choice([1, 2]),
            rnd.choice([1, 2]) if rooms > 1 else 1, "有", "有" if has_park or "華廈" in btype else "無", total,
            unit, "坡道平面" if has_park else "", park_m2 or "", park_price or "", note, f"DEMO{i + 1:05d}",
            round(m2 * 0.6, 2), round(m2 * 0.05, 2), round(m2 * 0.06, 2), "無" if "公寓" in btype or "透天" in btype else "有", ""])
    return rows


def main():
    out = ROOT / "sample" / "demo_lvr_land_a.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEAD_ZH)
        w.writerow(HEAD_EN)
        w.writerows(make())
    print(f"已產生虛構示範資料 → {out}")


if __name__ == "__main__":
    main()
