"""两点差分电阻的偏置抵消和状态流程检查。"""
import math
import unittest
from pathlib import Path


def resistance(i1, u1, i2, u2):
    di, du = i2-i1, u2-u1
    if not all(map(math.isfinite, (di, du))) or di <= 1 or du <= 0:
        return None
    result = du/di
    return result if math.isfinite(result) else None


class ResistanceDelta(unittest.TestCase):
    def test_constant_voltage_offset_cancels(self):
        for offset in (0, .2, .4):
            r = resistance(1.5, 1.5*.07+offset, 3, 3*.07+offset)
            self.assertAlmostEqual(r, .07)
            self.assertAlmostEqual(2*r, .14)

    def test_uses_actual_current_and_includes_series_resistance(self):
        r = .07+.006
        self.assertAlmostEqual(resistance(1.47, r*1.47+.3, 2.96, r*2.96+.3), r)

    def test_invalid_difference(self):
        for args in [(1.5, .4, 1.5, .5), (1.5, .4, 3, .3), (1.5, math.nan, 3, .5)]:
            self.assertIsNone(resistance(*args))

    def test_plateau_and_result_wiring(self):
        p=Path(__file__).resolve().parents[2]/'FOC_Migrated/foc_measure.c'
        s=p.read_bytes().decode('gbk')
        self.assertIn('measure_r_targets[8] = {1.5f, 2.0f, 2.5f, 3.0f, 2.5f, 2.0f, 1.5f, 2.25f}', s)
        self.assertIn('g_foc_measure_r.level = measure_level;', s)
        self.assertIn('g_foc_measure_r.fit_resistance_ohm;', s)
        self.assertIn('g_foc_measure_r.line_resistance_ohm = 2.0f * g_foc_measure_r.resistance_ohm;', s)


if __name__ == '__main__':
    unittest.main()
