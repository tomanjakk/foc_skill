"""模式25离线事件/电机模型；不运行 MCU，不验证功率板死区和 ADC 实际波形。"""
import math
import random
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARR, CCR4, CLOCK = 4249, 3707, 170_000_000
MASK = 0xFFFFFFFF


def clarke(a, b, c):
    return (2*a-b-c)/3, (b-c)/math.sqrt(3)


def pulse(angle, bus=31):
    co, si = math.cos(angle), math.sin(angle)
    phases = [co, -.5*co+math.sqrt(3)/2*si, -.5*co-math.sqrt(3)/2*si]
    neutral = ARR//2
    compare = [int(neutral-.03*ARR*x) for x in phases]
    alpha, beta = clarke(*(neutral-x for x in compare))
    return compare, bus*(alpha*co+beta*si)/CLOCK


def integrate_switches(compare, angle, bus):
    # 独立按上数半周期的实际开关区间积分，并使用本工程的采样电流符号。
    boundaries = sorted(set([0, CCR4] + compare))
    result = 0.0
    for lo, hi in zip(boundaries, boundaries[1:]):
        mid = (lo+hi)/2
        level = [int(mid < x) for x in compare]
        alpha, beta = clarke(*level)
        result -= bus*(alpha*math.cos(angle)+beta*math.sin(angle))*(hi-lo)/CLOCK
    return result


def harmonic_average(inverse):
    if len(inverse) != 32 or any(not math.isfinite(x) or x <= 0 for x in inverse):
        return None
    dc = sum(inverse)/32
    cosine = sum(x*math.cos(4*math.pi*i/32) for i, x in enumerate(inverse))/32
    sine = sum(x*math.sin(4*math.pi*i/32) for i, x in enumerate(inverse))/32
    amplitude = 2*math.hypot(cosine, sine)
    if dc <= amplitude:
        return None
    return .5*(1/(dc+amplitude)+1/(dc-amplitude))


def check_ticket(seq, write_seq, elapsed, counter, before, up=True, update=True):
    phase = counter if up else 2*ARR-counter
    expected = before+phase
    return ((seq-write_seq)&MASK) == 1 and counter <= ARR and CCR4 <= phase <= 2*ARR-512 and update and expected-64 <= elapsed <= expected+64


class InductanceModel(unittest.TestCase):
    def test_opposite_direction_pairs(self):
        axes = [(i >> 1) + (i & 1)*16 for i in range(32)]
        self.assertEqual(sorted(axes), list(range(32)))
        for i in range(0, 32, 2):
            self.assertEqual(axes[i+1]-axes[i], 16)

    def test_half_cycle_voltage_integral_and_units(self):
        for i in range(32):
            angle = math.tau*i/32
            compare, area = pulse(angle)
            self.assertGreater(area, 0)
            self.assertLess(max(compare), CCR4-170)
            self.assertAlmostEqual(area, integrate_switches(compare, angle, 31), places=12)
            # 不能按整个周期的平均电压积分，否则结果恰好大一倍。
            alpha, beta = clarke(*[(ARR//2-x)/ARR for x in compare])
            full_cycle_area = 31*(alpha*math.cos(angle)+beta*math.sin(angle))*(2*ARR/CLOCK)
            self.assertAlmostEqual(full_cycle_area, 2*area, places=12)

    def test_known_motor_32_directions_eight_rounds(self):
        ld, lq, rotation = 40e-6, 60e-6, .37
        random.seed(13)
        inverse = [0.0]*32
        for _ in range(8):
            for i in range(32):
                angle = math.tau*i/32
                _, area = pulse(angle)
                gain = math.cos(angle-rotation)**2/ld + math.sin(angle-rotation)**2/lq
                di = area*gain + random.uniform(-.002, .002)
                self.assertGreater(di, .08)
                inverse[i] += di/area/8
        measured = harmonic_average(inverse)
        self.assertAlmostEqual(measured, (ld+lq)/2, delta=.1e-6)
        self.assertAlmostEqual(measured*1e6, 50, delta=.1)
        self.assertAlmostEqual(2 * measured * 1e6, 100, delta=.2)
        self.assertIsNone(harmonic_average([0.0]*32))
        self.assertIsNone(harmonic_average([math.nan]*32))

    def test_line_result_is_published_and_cleared(self):
        source = (ROOT / 'FOC_Migrated/foc_measure.c').read_bytes().decode('gbk')
        header = (ROOT / 'FOC_Migrated/foc_measure.h').read_bytes().decode('gbk')
        self.assertIn('float line_inductance_uh;', header)
        self.assertIn('g_foc_measure_l.line_inductance_uh = 2.0f * g_foc_measure_l.inductance_uh;', source)
        self.assertIn('g_foc_measure_l.line_inductance_uh = 0.0f;', source)
        self.assertIn('memset((void *)&g_foc_measure_l, 0, sizeof(g_foc_measure_l));', source)

    def test_update_and_adc_order(self):
        self.assertTrue(check_ticket(11, 10, 7400, 4000, 3400))
        self.assertTrue(check_ticket(0, MASK, 7400, 4000, 3400))
        self.assertFalse(check_ticket(12, 10, 2*ARR+7400, 4000, 3400))
        self.assertFalse(check_ticket(10, 10, 7400, 4000, 3400))
        self.assertFalse(check_ticket(9, 10, 7400, 4000, 3400))
        self.assertFalse(check_ticket(11, 10, 7400, 4000, 3400, up=False))
        self.assertFalse(check_ticket(11, 10, 7400, 4000, 3400, update=False))
        self.assertFalse(check_ticket(11, 10, 7400+100, 4000, 3400))
        # 写入跨底点时写入函数会因方向翻转或 UIF 置位而关闭 MOE。
        self.assertFalse(check_ticket(11, 10, 7400, 3000, 4400))

    def test_adc_completion_may_cross_timer_top(self):
        # ADC 在上数 CCR4 触发，回调允许延迟到顶点后的下数阶段。
        timer = (ROOT/'Core/Src/tim.c').read_bytes().decode('gbk')
        source = (ROOT/'FOC_Migrated/foc_measure.c').read_bytes().decode('gbk')
        check = timer[timer.index('bool MotorPwm_MeasurementCheck(void)'):timer.index('bool MotorPwm_SetCompareForMeasurement(')]
        self.assertNotIn('(s->cr1 & TIM_CR1_DIR) != 0U ||', check)
        self.assertNotIn('(sample.cr1 & TIM_CR1_DIR) != 0U ||', source)
        self.assertIn('2U * TIM1->ARR - s->counter', check)
        self.assertTrue(check_ticket(11, 10, 3400+2*ARR-3506, 3506, 3400, up=False))
        # 同一触发延迟跨顶点，采样序号仍连续；底点余量不足、漏采样仍拒绝。
        self.assertTrue(check_ticket(11, 10, 3400+2*ARR-4000, 4000, 3400, up=False))
        self.assertFalse(check_ticket(12, 10, 3400+2*ARR-4000, 4000, 3400, up=False))
        self.assertFalse(check_ticket(11, 10, 3400+2*ARR-500, 500, 3400, up=False))

    def test_mode_and_fail_closed_paths(self):
        enum = (ROOT/'FOC_Migrated/config/data_type.h').read_bytes().decode('gbk')
        task = (ROOT/'FOC_Migrated/foc_task.c').read_bytes().decode('gbk')
        source = (ROOT/'FOC_Migrated/foc_measure.c').read_bytes().decode('gbk')
        timer = (ROOT/'Core/Src/tim.c').read_bytes().decode('gbk')
        self.assertRegex(enum, r'Measure_Resistance\s*= 24')
        self.assertRegex(enum, r'Measure_Inductance\s*= 25')
        self.assertRegex(enum, r'MODE_NUM\s*= 26')
        pwm_modes = task[task.index('static bool ModeNeedPwm'):task.index('void Loop_State_Reset')]
        self.assertNotIn('Measure_Inductance', pwm_modes)
        self.assertIn('FOC_MeasureInductance_Cancel(&MotorControl)', task)
        self.assertIn('FOC_MeasureInductance_Run(&FOC, &MotorControl)', task)
        self.assertIn('MotorPwm_MeasurementCheck()', source)
        self.assertIn('sample.sequence - l_sequence != 1U', source)
        self.assertIn('adc_sync_error_count != l_adc_errors', source)
        self.assertIn('motor->ModeNow = Motor_Disable', source)
        self.assertIn('MotorPwm_MeasurementStop();', source)
        self.assertIn('TIM1->BDTR &= ~TIM_BDTR_MOE', timer)
        self.assertIn('!measurement_pending && SystemCoreClock == PWM_TIM_CLOCK', timer)


if __name__ == '__main__':
    unittest.main()
