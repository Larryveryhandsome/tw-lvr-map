"""轉換器的容錯、規模、換算與座標快取測試（不連網）。跑法：python -m unittest discover -s tests"""
import csv
import json
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import convert_open_data as c  # noqa: E402
import make_sample  # noqa: E402
from test_convert import row, write_csv  # noqa: E402


def load_js(p: Path):
    s = p.read_text(encoding="utf-8")
    assert s.startswith("const LVR_DATA = ")
    return json.loads(s[len("const LVR_DATA = "):].rstrip().rstrip(";"))


class ConversionMathTest(unittest.TestCase):
    def test_ping_constant_and_roundtrip(self):
        self.assertEqual(c.SQM_PER_PING, 3.305785)
        t = c.convert_row(dict(zip(make_sample.HEAD_ZH, row(建物移轉總面積平方公尺="3.305785"))), 0)
        self.assertEqual(t["area"], 1.0)

    def test_price_rounding_examples(self):
        t = c.convert_row(dict(zip(make_sample.HEAD_ZH, row(總價元="12345678", 單價元平方公尺="123456"))), 0)
        self.assertEqual(t["totalPrice"], 1234.6)                         # 萬，一位小數
        self.assertEqual(t["unitPrice"], round(123456 * 3.305785 / 10000, 2))
        self.assertEqual(t["unitPrice"], 40.81)

    def test_missing_numbers_are_none_not_zero(self):
        t = c.convert_row(dict(zip(make_sample.HEAD_ZH, row(總價元="", 單價元平方公尺="abc", 建物移轉總面積平方公尺="0"))), 0)
        self.assertIsNone(t["totalPrice"])
        self.assertIsNone(t["unitPrice"])
        self.assertIsNone(t["area"])

    def test_commas_and_ad_dates(self):
        t = c.convert_row(dict(zip(make_sample.HEAD_ZH, row(總價元="15,000,000", 交易年月日="20240512"))), 0)
        self.assertEqual(t["totalPrice"], 1500)
        self.assertEqual(t["date"], "2024-05-12")        # 已是西元不再加 1911


class RobustReadTest(unittest.TestCase):
    def test_big5_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "big5.csv"
            with open(p, "w", encoding="cp950", newline="") as f:
                w = csv.writer(f)
                w.writerow(make_sample.HEAD_ZH)
                w.writerow(make_sample.HEAD_EN)
                w.writerow(row(鄉鎮市區="北區"))
            rows = c.read_csv(p)
        self.assertEqual(rows[0]["鄉鎮市區"], "北區")

    def test_renamed_columns_are_aliased(self):
        head = [h.replace("單價元平方公尺", "單價元/平方公尺").replace("車位移轉總面積(平方公尺)", "車位移轉總面積（平方公尺）")
                for h in make_sample.HEAD_ZH]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(head)
                w.writerow(row())
            t = c.convert_row(c.read_csv(p)[0], 0)
        self.assertEqual(t["unitPrice"], 39.67)
        self.assertEqual(t["parkingArea"], 10.0)

    def test_wrong_file_type_is_clear_error_not_empty_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rent.csv"
            p.write_text("鄉鎮市區,交易標的,租賃年月日,總額元\n北區,房地,1130101,20000\n", encoding="utf-8")
            out = Path(d) / "data.js"
            self.assertEqual(c.main([str(p), "--out", str(out), "--centers", str(Path(d) / "none.json")]), 2)
            self.assertFalse(out.exists())               # 不產生一份空資料蓋掉舊的
            with self.assertRaises(c.CsvFormatError) as e:
                c.read_csv(p)
            self.assertIn("總價元", str(e.exception))

    def test_failed_run_keeps_previous_data_js(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "data.js"
            out.write_text("const LVR_DATA = {old:true};\n", encoding="utf-8")
            bad = Path(d) / "bad.csv"
            bad.write_text("a,b\n1,2\n", encoding="utf-8")
            self.assertEqual(c.main([str(bad), "--out", str(out), "--centers", str(Path(d) / "x.json")]), 2)
            self.assertIn("old:true", out.read_text(encoding="utf-8"))

    def test_empty_and_header_only_files(self):
        with tempfile.TemporaryDirectory() as d:
            e = Path(d) / "empty.csv"
            e.write_text("", encoding="utf-8")
            self.assertEqual(c.read_csv(e), [])
            h = Path(d) / "head.csv"
            write_csv(h, [])
            out = Path(d) / "o.js"
            self.assertEqual(c.main([str(h), "--out", str(out), "--centers", str(Path(d) / "x.json")]), 0)
            self.assertEqual(load_js(out)["total"], 0)

    def test_duplicates_across_files_and_since_filter(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.csv", Path(d) / "b.csv"
            write_csv(a, [row(編號="X1"), row(編號="X2", 交易年月日="1100101")])
            write_csv(b, [row(編號="X1"), row(編號="X3", 交易標的="土地")])      # X1 重疊
            out = Path(d) / "o.js"
            args = ["--out", str(out), "--centers", str(Path(d) / "x.json")]
            self.assertEqual(c.main([str(a), str(b)] + args), 0)
            self.assertEqual(sorted(t["id"] for t in load_js(out)["transactions"]), ["X1", "X2", "X3"])
            self.assertEqual(c.main([str(a), str(b), "--since", "2024-01-01", "--only-buildings"] + args), 0)
            self.assertEqual([t["id"] for t in load_js(out)["transactions"]], ["X1"])
            self.assertEqual(c.main([str(a), "--since", "1130101"] + args), 0)
            self.assertEqual([t["id"] for t in load_js(out)["transactions"]], ["X1"])

    def test_streaming_memory_is_flat(self):
        """3 萬列轉換的記憶體尖峰要很小（修前整份讀進記憶體：50 萬列實測尖峰 2.5GB）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "big.csv"
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(make_sample.HEAD_ZH)
                w.writerow(make_sample.HEAD_EN)
                for i in range(30000):
                    w.writerow(row(編號=f"B{i}", 備註="x" * 40))
            out = Path(d) / "o.js"
            tracemalloc.start()
            self.assertEqual(c.main([str(p), "--out", str(out), "--centers", str(Path(d) / "x.json")]), 0)
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            self.assertEqual(load_js(out)["total"], 30000)
            self.assertLess(peak / 1024 ** 2, 25, f"記憶體尖峰 {peak / 1024 ** 2:.0f}MB")


class GeocoderRobustTest(unittest.TestCase):
    def test_network_error_not_cached_and_aborts_after_5(self):
        sleeps = []

        def boom(q):
            raise OSError("429 Too Many Requests")
        with tempfile.TemporaryDirectory() as d:
            g = c.Geocoder(Path(d) / "cache.json", "a@b.invalid", "示範市", sleep=sleeps.append, fetch=boom)
            self.assertIsNone(g.lookup("示範路1號", "示範區"))
            self.assertEqual(g.cache, {})                    # 暫時性錯誤不能記成「查無此地址」
            self.assertGreater(sleeps[0], 1.1)               # 有退避
            with self.assertRaises(RuntimeError):
                for i in range(6):
                    g.lookup(f"示範路{i}號", "示範區")

    def test_corrupt_cache_quarantined_and_save_is_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cache.json"
            p.write_text('{"a": [1, 2', encoding="utf-8")        # 寫到一半被中斷
            g = c.Geocoder(p, "a@b.invalid", "", sleep=lambda s: None, fetch=lambda q: [])
            self.assertEqual(g.cache, {})
            self.assertTrue(list(Path(d).glob("cache.json.bad*")))
            g.cache["k"] = [1.0, 2.0]
            g.save()
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"k": [1.0, 2.0]})
            self.assertFalse(list(Path(d).glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
