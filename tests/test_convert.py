"""開放資料轉換器測試（不連網）。跑法：python -m unittest discover -s tests"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import convert_open_data as c  # noqa: E402
import make_sample  # noqa: E402


def write_csv(path, rows, english=True):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(make_sample.HEAD_ZH)
        if english:
            w.writerow(make_sample.HEAD_EN)
        w.writerows(rows)


def row(**kw):
    base = dict(zip(make_sample.HEAD_ZH, [""] * len(make_sample.HEAD_ZH)))
    base.update({"鄉鎮市區": "示範區", "交易標的": "房地(土地+建物)+車位", "土地位置建物門牌": "示範區示範路１００號５樓",
                 "交易年月日": "1130512", "移轉層次": "五層", "總樓層數": "十二層", "建物型態": "住宅大樓(11層含以上有電梯)",
                 "建築完成年月": "1000301", "建物移轉總面積平方公尺": "132.23", "建物現況格局-房": "3",
                 "建物現況格局-廳": "2", "建物現況格局-衛": "2", "總價元": "15000000", "單價元平方公尺": "120000",
                 "車位類別": "坡道平面", "車位移轉總面積(平方公尺)": "33.06", "車位總價元": "1500000", "編號": "X1"})
    base.update(kw)
    return [base[h] for h in make_sample.HEAD_ZH]


class ConvertTest(unittest.TestCase):
    def test_units_and_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a_lvr_land_a.csv"
            write_csv(p, [row()])
            t = c.convert_row(c.read_csv(p)[0], 0)
        self.assertEqual(t["date"], "2024-05-12")
        self.assertEqual(t["totalPrice"], 1500)                 # 萬
        self.assertEqual(t["unitPrice"], 39.67)                 # 120000 元/m² × 3.305785 ÷ 10000
        self.assertEqual(t["area"], 40.0)                        # 132.23 m² → 坪
        self.assertEqual((t["floor"], t["totalFloors"]), (5, 12))
        self.assertEqual(t["age"], 13.2)
        self.assertEqual(t["layout"], "3房2廳2衛")
        self.assertEqual((t["parkingPrice"], t["parkingArea"]), (150, 10.0))
        self.assertFalse(t["special"])

    def test_special_note_and_no_english_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"
            write_csv(p, [row(備註="親友、員工、共有人或其他特殊關係間之交易。"), row(編號="X2")], english=False)
            rows = c.read_csv(p)
        self.assertEqual(len(rows), 2)
        self.assertTrue(c.convert_row(rows[0], 0)["special"])

    def test_helpers(self):
        self.assertEqual([c.zh_floor(x) for x in ("十二層", "地下一層", "全", "三層，四層", "二十三層")], [12, -1, None, 3, 23])
        self.assertIsNone(c.roc_date("123"))
        self.assertIsNone(c.age_at("", "2024-01-01"))
        self.assertEqual(c.Geocoder.candidates("示範路１２號３樓", "示範區", "示範市"),
                         ["示範市示範區示範路12號", "示範市示範區示範路"])

    def test_geocoder_cache_and_rate_limit(self):
        calls, sleeps = [], []
        fake = lambda q: calls.append(q) or ([{"lat": "24.1", "lon": "120.6"}] if "號" in q else [])
        with tempfile.TemporaryDirectory() as d:
            g = c.Geocoder(Path(d) / "cache.json", "demo@example.invalid", "示範市", sleep=sleeps.append, fetch=fake)
            self.assertEqual(g.lookup("示範路1號", "示範區"), [24.1, 120.6])
            self.assertEqual(g.lookup("示範路1號", "示範區"), [24.1, 120.6])
            self.assertEqual(len(calls), 1)                      # 第二次走快取
            self.assertEqual(sleeps, [1.1])
            self.assertIsNone(g.lookup("示範大道", "示範區"))
            g.save()
            self.assertTrue((Path(d) / "cache.json").exists())

    def test_place_and_write(self):
        rows = [c.convert_row(dict(zip(make_sample.HEAD_ZH, row(鄉鎮市區=k))), i) for i, k in enumerate(["甲區", "乙區"])]
        c.place(rows, {"甲區": [24.0, 120.0]})
        self.assertAlmostEqual(rows[0]["lat"], 24.0, delta=0.005)
        self.assertIsNone(rows[1]["lat"])
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "data.js"
            c.write_data_js(rows, out, "測試")
            s = out.read_text(encoding="utf-8")
            data = json.loads(s[len("const LVR_DATA = "):].rstrip().rstrip(";"))
        self.assertEqual((data["total"], data["districts"]), (2, ["乙區", "甲區"]))
        self.assertIn("政府資料開放授權條款", data["source"])

    def test_sample_is_fictional_and_reproducible(self):
        a, b = make_sample.make(20), make_sample.make(20)
        self.assertEqual(a, b)
        for r in a:
            self.assertTrue(r[2].startswith("示範"))


if __name__ == "__main__":
    unittest.main()
