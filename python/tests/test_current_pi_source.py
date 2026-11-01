"""参数来源与切换边界的离线模型；不替代MCU执行验证。"""
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def choose(enabled, r_status=0, l_status=0, valid=0, r=0, l=0):
    if (enabled and r_status == l_status == 2 and valid == 1
            and math.isfinite(r) and r > 0 and math.isfinite(l) and l > 0):
        return 1, r, l, l
    return 0, .07, 50e-6, 50e-6


class CurrentPiSource(unittest.TestCase):
    def test_default_and_partial_results(self):
        self.assertEqual(choose(False, 2, 2, 1, .061, 54e-6)[0], 0)
        for r_status, l_status, valid in [(0, 0, 0), (2, 0, 0), (0, 2, 1), (2, 3, 0), (2, 2, 0)]:
            self.assertEqual(choose(True, r_status, l_status, valid, .061, 54e-6)[0], 0)

    def test_valid_and_invalid_results(self):
        self.assertEqual(choose(True, 2, 2, 1, .061, 54e-6), (1, .061, 54e-6, 54e-6))
        for bad in [0, -1, math.nan, math.inf, -math.inf]:
            self.assertEqual(choose(True, 2, 2, 1, bad, 54e-6)[0], 0)
            self.assertEqual(choose(True, 2, 2, 1, .061, bad)[0], 0)

    def test_formula_units(self):
        for enabled in [False, True]:
            _, r, ld, lq = choose(enabled, 2, 2, 1, .061, 54e-6)
            kp = ld * (.5 / (1.5 / 20000)) * 1.8
            ki = r / ld * (5 / 14)
            self.assertEqual(ld, lq)
            self.assertAlmostEqual(kp, .648 if enabled else .6)
            self.assertAlmostEqual(ki, .061 / 54e-6 * (5/14) if enabled else 500)

    def test_integration_guards_and_no_motor_parameter_write(self):
        s = (ROOT/'FOC_Migrated/foc_task.c').read_bytes().decode('gbk')
        fn = s[s.index('static void MotorControl_CurrentLoopGains_Init(void)'):s.index('static void MotorControl_SpeedLoopGains_Init(void)')]
        self.assertIn('source == g_current_pi_parameter_source', fn)
        self.assertIn('r == last_r && ld == last_ld && lq == last_lq', fn)
        self.assertIn('FOC.Id_int = FOC.Iq_int = 0.0f;', fn)
        self.assertNotIn('line_resistance_ohm', fn)
        self.assertNotIn('inductance_uh', fn)
        for name in ['motor_phase_resistance', 'motor_d_inductance', 'motor_q_inductance']:
            self.assertNotIn('MotorControl.'+name+' =', fn)
        self.assertNotIn('EEPROM_', fn)
        run = s[s.index('void FOC_Run(void)'):]
        self.assertLess(run.index('if (ModeLast == Motor_Disable) MotorControl_CurrentLoopGains_Init();'), run.index('FOC_Port_PwmEnable();'))
        self.assertIn('case Motor_Disable:\r\n            MotorControl_CurrentLoopGains_Init();', run)


if __name__ == '__main__':
    unittest.main()
