"""母线批采样模型及源码约束；不代替 ADC 时序和实机波形验证。"""
from pathlib import Path
import unittest


def batch(previous, samples):
    for value in samples:
        if value is None:
            return previous, False
    return (sum(samples[1:]) + 2) // 4, True


class VbusSampling(unittest.TestCase):
    def test_channel_switch_first_sample_not_published(self):
        self.assertEqual(batch(0, [700, 942, 943, 941, 942]), (942, True))

    def test_persistent_voltage_step_not_clipped(self):
        # 真实降压和升压均立即传入后续原有低通，不做异常值剔除。
        self.assertEqual(batch(942, [600] * 5), (600, True))
        self.assertEqual(batch(600, [1300] * 5), (1300, True))
        self.assertEqual(batch(942, [0] * 5), (0, True))

    def test_failure_does_not_publish_partial_batch(self):
        for failed in range(5):
            values = [600] * 5
            values[failed] = None
            self.assertEqual(batch(942, values), (942, False))

    def test_rounding_and_full_scale(self):
        self.assertEqual(batch(0, [0, 942, 943, 942, 943]), (943, True))
        self.assertEqual(batch(0, [4095] * 5), (4095, True))

    def test_source_scope(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / 'Core/Src/adc.c').read_bytes().decode('gbk')
        self.assertIn('(channel == ADC_CHANNEL_8) ?', source)
        self.assertIn('ADC_SAMPLETIME_640CYCLES_5 : ADC_SAMPLETIME_47CYCLES_5', source)
        self.assertIn('if (i != 0U) bus_sum += bus_samples[i];', source)
        self.assertIn('value = (uint16_t)((bus_sum + 2U) / 4U);', source)
        self.assertLess(source.index('++g_vbus_adc.read_errors;'), source.index('slow_input.bus_voltage_adc = value;'))
        self.assertNotIn('HAL_ADC_Stop(', source.replace('HAL_ADC_Stop()',''))


if __name__ == '__main__':
    unittest.main()
