"""位置环带宽计算的离线模型和源码约束检查；不编译、不运行固件。"""

import math
import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_C = (ROOT / "FOC_Migrated/foc_test.c").read_bytes().decode("gbk")
TEST_H = (ROOT / "FOC_Migrated/foc_test.h").read_bytes().decode("gbk")
PORT_H = (ROOT / "FOC_Migrated/config/foc_port.h").read_bytes().decode("gbk")
TASK_C = (ROOT / "FOC_Migrated/foc_task.c").read_bytes().decode("gbk")
RUN_C = (ROOT / "FOC_Migrated/foc_run.c").read_bytes().decode("gbk")
ALGORITHM_C = (ROOT / "FOC_Migrated/foc_algorithm.c").read_bytes().decode("gbk")
ENCODER_C = (ROOT / "FOC_Migrated/encoder/foc_encoder.c").read_bytes().decode("gbk")


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def phase_ticks(frequency):
    """按固件单精度相位累加检查 15 个周期所需采样点。"""
    full_turn = f32(math.tau)
    step = f32(f32(full_turn * f32(frequency)) * f32(1.0 / 5000.0))
    phase = correction = 0.0
    cycles = ticks = 0
    while cycles < 15:
        adjusted = f32(step - correction)
        next_phase = f32(phase + adjusted)
        correction = f32(f32(next_phase - phase) - adjusted)
        phase = next_phase
        if phase >= full_turn:
            phase = f32(phase - full_turn)
            cycles += 1
        ticks += 1
    return ticks


def lock_in(frequency, gain, phase_degrees):
    """输入已知正弦及带直流偏置的反馈，检查 5+10 周期同步解调。"""
    phase_shift = math.radians(phase_degrees)
    step = math.tau * frequency / 5000.0
    phase = 0.0
    cycles = 0
    center = 50.0
    input_s = input_c = output_s = output_c = 0.0
    while cycles < 15:
        sine, cosine = math.sin(phase), math.cos(phase)
        if cycles >= 5:
            position_ref = center + math.tau * sine
            position_feedback = center + 0.35 + math.tau * gain * math.sin(phase + phase_shift)
            reference = position_ref - center
            response = position_feedback - center
            input_s += reference * sine
            input_c += reference * cosine
            output_s += response * sine
            output_c += response * cosine
        phase += step
        if phase >= math.tau:
            phase -= math.tau
            cycles += 1
    magnitude = math.hypot(output_s, output_c) / math.hypot(input_s, input_c)
    phase = math.degrees(math.atan2(output_c, output_s) - math.atan2(input_c, input_s))
    return magnitude, (phase + 180.0) % 360.0 - 180.0


def scan(coarse, response, fine_response=None):
    """独立模拟粗扫首个穿越、重新测量下界和 0.1 Hz 细扫。"""
    previous = (coarse[0], response(coarse[0]))
    for frequency in coarse[1:]:
        current = (frequency, response(frequency))
        if previous[1] > -3.0 >= current[1]:
            lower, upper = previous[0], current[0]
            measure = fine_response or response
            previous = (lower, measure(lower))
            if previous[1] <= -3.0:
                return "inconsistent", 0.0
            while lower < upper:
                lower = min(lower + 0.1, upper)
                current = (lower, measure(lower))
                if previous[1] > -3.0 >= current[1]:
                    fraction = (-3.0 - previous[1]) / (current[1] - previous[1])
                    return "success", previous[0] * (current[0] / previous[0]) ** fraction
                previous = current
            return "inconsistent", 0.0
        previous = current
    return "no_cross", 0.0


def main():
    assert re.search(r"#define\s+FOC_POSITION_BANDWIDTH_TEST\s+[01]U", PORT_H)
    assert re.search(r"#define\s+POSITION_LOOP_FREQ\s+5000U", PORT_H)
    assert "POSITION_BW_IQ_LIMIT_A" not in TEST_H
    assert re.search(r"#define\s+POSITION_BW_PHASE_LIMIT_A\s+10\.0f", TEST_H)
    frequencies = re.search(r"position_bw_frequencies\[POSITION_BW_COARSE_COUNT\]\s*=\s*\{([^}]+)", TEST_C).group(1)
    coarse = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)f", frequencies)]
    assert coarse == [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9] + [10]
    assert "POSITION_BW_FINE_STEP_HZ  0.1f" in TEST_C
    assert "position_bw_cycles >= 5U" in TEST_C and "position_bw_cycles < 15U" in TEST_C
    assert "g_position_bandwidth.pos_ref_rad - Encoder.pos * _2PI" in RUN_C
    assert "speed_ref, Encoder.vel_mech, MotorControl->current_limit" in RUN_C
    assert "fabsf(MotorControl->iqRef) >= MotorControl->current_limit" in RUN_C
    assert "fabsf(FOC.Ia) <= trip_limit" in TEST_C and "fabsf(FOC.Ic) <= trip_limit" in TEST_C
    assert re.search(r"/\* 暂时关闭运行中位置跟踪误差超限中止。.*?fabsf\(Encoder\.pos \* _2PI - g_position_bandwidth\.pos_ref_rad\) > POSITION_BW_TRAVEL_RAD.*?\*/", TEST_C, re.S)
    assert re.search(r"/\* 暂时关闭位置带宽测试的母线电压检查。.*?FOC\.Vbus >= ProtectParam\.undervoltage_threshold.*?FOC\.Vbus <= ProtectParam\.overvoltage_threshold.*?\*/", TEST_C, re.S)
    assert "adc_complete_sample_sequence - position_bw_sample_sequence != 1U" in TEST_C
    assert "adc_sync_error_count != position_bw_adc_errors" in TEST_C
    assert "position_bw_pwm_wait_ticks = 2U" in TEST_C
    assert "if (!PositionBandwidth_PreparePwm()) return;" in RUN_C
    assert "TIM1->RCR != 0U" in TEST_C and "TIM_CR1_UDIS" in TEST_C
    assert TASK_C.index("uint32_t reason = PositionBandwidth_Check()") < TASK_C.index("PositionBandwidth_Begin();")
    assert "MotorControl->ModeNow == Position_Mode" in ALGORITHM_C and "POSITION_BW_REASON_SATURATION" in ALGORITHM_C
    assert "FOC->dtc_a < PWM_DUTY_MIN" in ALGORITHM_C and "FOC->dtc_c > PWM_DUTY_MAX" in ALGORITHM_C
    assert "g_pos_bw_enc_delta_raw = delta_count;" in ENCODER_C
    assert "g_pos_bw_enc_delta_accepted = delta_count;" in ENCODER_C
    assert "++g_pos_bw_enc_reject_count" in ENCODER_C
    assert "g_pos_bw_enc_reject_count = 0U;" in TEST_C

    # 重复帧不累加，下一帧按帧间隔判断；累计位移不能丢失。
    frame_rate = 0.0
    accepted_position = 0
    elapsed = 0
    for fresh, raw_delta in ((False, 0), (True, 100), (False, 0), (True, 100)):
        elapsed += 1
        if fresh:
            assert abs(raw_delta / elapsed - frame_rate) <= 50
            frame_rate = raw_delta / elapsed
            accepted_position += raw_delta
            elapsed = 0
    assert accepted_position == 200
    assert 'sequence - frame_sequence != 1U' not in ENCODER_C
    assert 'frame_ticks > 10U' in ENCODER_C
    assert 'g_pos_bw_enc_fault != 0U' in TEST_C
    assert 'POSITION_BW_REASON_ENCODER' in TEST_C

    for voltage in (18.0, 40.0):
        assert 18.0 <= voltage <= 40.0
    assert not (18.0 <= 17.99 <= 40.0) and not (18.0 <= 40.01 <= 40.0)
    assert max(abs(value) for value in (10.0, -10.0, 0.0)) <= 10.0
    assert max(abs(value) for value in (10.001, 0.0, 0.0)) > 10.0
    assert abs(math.radians(3.0)) <= math.radians(3.0)
    assert abs(math.radians(3.001)) > math.radians(3.0)
    assert ((0 - 0xFFFFFFFF) & 0xFFFFFFFF) == 1
    assert ((102 - 100) & 0xFFFFFFFF) != 1

    for frequency in (1.0, 1.5, 2.0, 2.5, 3.0):
        assert abs(phase_ticks(frequency) - 15.0 * 5000.0 / frequency) <= 2.0
    for frequency in (1.0, 1.5, 3.0):
        gain, phase = lock_in(frequency, 0.72, -63.0)
        assert abs(gain - 0.72) < 0.001, (frequency, gain)
        assert abs(phase + 63.0) < 0.1, (frequency, phase)

    # 电机轴峰值为一圈，正弦位置有正、反两个方向；检查电机轴速度峰值。
    assert "#define POSITION_BW_AMPLITUDE_RAD (_2PI)" in TEST_C
    assert "g_position_bandwidth.center_rad = Encoder.pos * _2PI" in TEST_C
    assert "float feedback = Encoder.pos * _2PI - g_position_bandwidth.center_rad" in TEST_C
    assert "position_bw_base" not in TEST_C and "POSITION_BW_RAMP_TICKS" not in TEST_C
    assert "speed_ref = MotorControl->speedShadow +" not in RUN_C
    for frequency in coarse:
        swing_rpm = 60.0 * math.tau * frequency
        assert swing_rpm > 0
        assert math.sin(math.pi / 2) > 0 and math.sin(3 * math.pi / 2) < 0
        assert math.cos(0) > 0 and math.cos(math.pi) < 0

    response = lambda f: -3.0 * (f - 1.0) / (2.35 - 1.0)
    status, bandwidth = scan(coarse, response)
    assert status == "success" and abs(bandwidth - 2.35) < 0.01
    assert scan(coarse, lambda f: 0.0) == ("no_cross", 0.0)
    assert scan(coarse, response, lambda f: 0.0) == ("inconsistent", 0.0)
    assert scan(coarse, response, lambda f: -4.0) == ("inconsistent", 0.0)
    print("position bandwidth: static checks and offline signal model passed")


if __name__ == "__main__":
    main()
