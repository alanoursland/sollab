import unittest

from kinopulse.analysis.nonautonomous.parametric_resonance import MathieuAnalyzer


class ResonanceLabTests(unittest.TestCase):
    def test_principal_mathieu_tongue_is_detected(self):
        analyzer = MathieuAnalyzer(delta=0.25, epsilon=0.2)
        self.assertFalse(analyzer.is_stable())
        self.assertEqual(analyzer.identify_resonance_tongue(), 1)

    def test_nearby_point_is_stable(self):
        self.assertTrue(MathieuAnalyzer(delta=0.5, epsilon=0.2).is_stable())


if __name__ == "__main__":
    unittest.main()
