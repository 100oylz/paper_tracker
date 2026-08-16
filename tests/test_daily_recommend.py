import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import daily_recommend as dr


class NormalizeTests(unittest.TestCase):
    def test_lowercases_strips_punctuation(self) -> None:
        self.assertEqual(dr.normalize_title("The Quick: Fox!"), "thequickfox")

    def test_preserves_chinese(self) -> None:
        self.assertEqual(dr.normalize_title("隐私 保护"), "隐私保护")


class VenuePrestigeTests(unittest.TestCase):
    def test_ccf_a_is_one(self) -> None:
        self.assertEqual(dr.venue_prestige("AAAI"), 1.0)
        self.assertEqual(dr.venue_prestige("NeurIPS"), 1.0)

    def test_ccf_b_is_07(self) -> None:
        self.assertEqual(dr.venue_prestige("IJCAI"), 0.7)

    def test_unknown_venue_defaults(self) -> None:
        self.assertEqual(dr.venue_prestige("Some Unknown"), 0.3)
        self.assertEqual(dr.venue_prestige(""), 0.3)


class RecencyTests(unittest.TestCase):
    def test_current_year_full_score(self) -> None:
        self.assertEqual(dr.recency(2026, current_year=2026), 1.0)

    def test_linear_decay(self) -> None:
        self.assertEqual(dr.recency(2021, current_year=2026), 0.0)
        self.assertAlmostEqual(dr.recency(2024, current_year=2026), 0.6)

    def test_invalid_year_zero(self) -> None:
        self.assertEqual(dr.recency("NoYear", current_year=2026), 0.0)


class ScoreTests(unittest.TestCase):
    def test_full_score_perfect_paper(self) -> None:
        item = {
            "triage_score": 5,
            "related_code": "https://github.com/x",
            "venue": "AAAI",
            "year": 2026,
        }
        s, triage, has_code = dr.score(item)
        self.assertAlmostEqual(s, 1.0, places=2)
        self.assertEqual(triage, 5)
        self.assertEqual(has_code, 1.0)

    def test_negative_triage_clamped_to_zero(self) -> None:
        item = {"triage_score": -3, "venue": "ICSE", "year": 2020}
        s, triage, _ = dr.score(item)
        self.assertEqual(triage, 0)


class LabelTests(unittest.TestCase):
    def test_same_direction_and_code(self) -> None:
        lbl = dr.label_of("federated-graph-learning", True, {"federated-graph-learning"})
        self.assertIn("🔁 同方向", lbl)
        self.assertIn("📦 有代码", lbl)

    def test_new_direction(self) -> None:
        lbl = dr.label_of("federated-unlearning", False, {"other"})
        self.assertIn("🆕 新方向", lbl)

    def test_no_label(self) -> None:
        self.assertEqual(dr.label_of("other", False, set()), "—")


class RecommendTests(unittest.TestCase):
    def test_excludes_read_titles(self) -> None:
        cache = {"FL:venue:AAAI:": [
            {"title": "Read Paper", "triage_score": 5, "venue": "AAAI", "year": 2026},
            {"title": "New Paper", "triage_score": 2, "venue": "AAAI", "year": 2026},
        ]}
        read = {"readpaper"}
        cands, _ = dr.recommend(cache, read, top_n=5)
        titles = [c["title"] for c in cands]
        self.assertIn("New Paper", titles)
        self.assertNotIn("Read Paper", titles)

    def test_sorts_by_score_desc(self) -> None:
        cache = {"FL:venue:AAAI:": [
            {"title": "Low", "triage_score": 1, "venue": "UAI", "year": 2020},
            {"title": "High", "triage_score": 5, "venue": "AAAI", "year": 2026},
        ]}
        cands, _ = dr.recommend(cache, set(), top_n=5)
        self.assertEqual(cands[0]["title"], "High")
        self.assertGreaterEqual(cands[0]["score"], cands[1]["score"])


class FlPapersTests(unittest.TestCase):
    def test_only_fl_keys(self) -> None:
        cache = {
            "FL:venue:AAAI:": [{"title": "A"}],
            "DP:venue:ICDAR:": [{"title": "B"}],
        }
        papers = list(dr.fl_papers(cache, dedup=False))
        self.assertEqual([p["title"] for p in papers], ["A"])

    def test_dedup_by_title(self) -> None:
        cache = {
            "FL:venue:AAAI:": [{"title": "Same", "ee": "a"}],
            "FL:venue:ICML:": [{"title": "Same", "ee": "b"}],
        }
        papers = list(dr.fl_papers(cache, dedup=True))
        self.assertEqual(len(papers), 1)


if __name__ == "__main__":
    unittest.main()
