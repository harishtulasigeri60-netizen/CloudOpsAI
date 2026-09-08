import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recommendation import anomaly_score, get_health_score, get_operations_score


class CloudOpsAILogicTests(unittest.TestCase):
    def test_anomaly_detects_spike(self):
        self.assertTrue(anomaly_score([10, 11, 10, 9, 10, 45])["anomaly"])

    def test_health_empty(self):
        self.assertEqual(get_health_score([])[0], 0)

    def test_health_stopped_penalty(self):
        self.assertEqual(get_health_score([{"State": "stopped", "CPU": 0, "Name": "x"}])[0], 92)

    def test_operations_score_range(self):
        score, _ = get_operations_score([{"State": "running", "CPU": 5}], 100)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
