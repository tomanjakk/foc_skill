from pathlib import Path
r=Path(__file__).resolve().parents[2]
p=r/'FOC_Migrated/foc_measure.c'
s=p.read_bytes().decode('gbk')
def sub(a,b):
    global s
    assert s.count(a)==1,(a[:70],s.count(a))
    s=s.replace(a,b)
sub('static uint32_t measure_level;', 'static uint32_t measure_level;\r\nstatic const float measure_r_targets[7] = {1.5f, 2.0f, 2.5f, 3.0f, 2.5f, 2.0f, 1.5f};')
sub('    return measure_level == 0U ? MEASURE_R_LOW_CURRENT_A : MEASURE_R_CURRENT_A;', '    return measure_r_targets[measure_level];')
helper='''/* 多点拟合同时估计斜率和固定压降；不使用铭牌阻值修正结果。 */
static bool MeasureR_Fit(void)
{
    float mi = 0.0f, mu = 0.0f, xx = 0.0f, xy = 0.0f, yy = 0.0f;
    float slope, offset, max_error = 0.0f, sse = 0.0f, hysteresis = 0.0f;
    for (uint32_t i = 0U; i < 7U; ++i) {
        float x = g_foc_measure_r.current_points_a[i], y = g_foc_measure_r.voltage_points_v[i];
        if (!isfinite(x) || !isfinite(y)) return false;
        mi += x / 7.0f; mu += y / 7.0f;
    }
    for (uint32_t i = 0U; i < 7U; ++i) {
        float x = g_foc_measure_r.current_points_a[i] - mi;
        float y = g_foc_measure_r.voltage_points_v[i] - mu;
        xx += x*x; xy += x*y; yy += y*y;
    }
    if (!(xx > 1.0f && yy > 0.0f)) return false;
    slope = xy / xx; offset = mu - slope * mi;
    if (!(isfinite(slope) && slope > 0.0f && isfinite(offset))) return false;
    for (uint32_t i = 0U; i < 7U; ++i) {
        float e = g_foc_measure_r.voltage_points_v[i] - slope * g_foc_measure_r.current_points_a[i] - offset;
        if (fabsf(e) > max_error) max_error = fabsf(e);
        sse += e*e;
        if (i < 3U) {
            float h = fabsf((g_foc_measure_r.voltage_points_v[i] - slope * g_foc_measure_r.current_points_a[i]) -
                           (g_foc_measure_r.voltage_points_v[6U-i] - slope * g_foc_measure_r.current_points_a[6U-i]));
            if (h > hysteresis) hysteresis = h;
        }
    }
    g_foc_measure_r.fit_resistance_ohm = slope;
    g_foc_measure_r.voltage_offset_v = offset;
    g_foc_measure_r.fit_max_error_v = max_error;
    g_foc_measure_r.fit_r_squared = 1.0f - sse / yy;
    g_foc_measure_r.hysteresis_v = hysteresis;
    return max_error <= 0.005f && hysteresis <= 0.010f && g_foc_measure_r.fit_r_squared >= 0.98f;
}

'''.replace('\n','\r\n')
sub('static void MeasureR_Stop(',helper+'static void MeasureR_Stop(')
sub('    measure_level = 0U;', '''    measure_level = 0U;
    g_foc_measure_r.fit_resistance_ohm = 0.0f;
    g_foc_measure_r.fit_max_error_v = g_foc_measure_r.fit_r_squared = g_foc_measure_r.hysteresis_v = 0.0f;
    for (uint32_t i = 0U; i < 7U; ++i) {
        g_foc_measure_r.current_points_a[i] = g_foc_measure_r.voltage_points_v[i] = 0.0f;
    }'''.replace('\n','\r\n'))
s=s.replace('(measure_level == 0U ? 0.0f : MEASURE_R_LOW_CURRENT_A)', '(measure_level == 0U ? 0.0f : measure_r_targets[measure_level-1U])')
start=s.index('                if (measure_level == 0U) {')
end=s.index('                measure_ticks = 0U;\r\n                measure_phase = MEASURE_R_RAMP_DOWN;',start)
block='''                g_foc_measure_r.current_points_a[measure_level] = g_foc_measure_r.current_avg_a;
                g_foc_measure_r.voltage_points_v[measure_level] = g_foc_measure_r.voltage_command_avg_v;
                if (measure_level == 0U) {
                    g_foc_measure_r.low_current_avg_a = g_foc_measure_r.current_avg_a;
                    g_foc_measure_r.low_voltage_command_avg_v = g_foc_measure_r.voltage_command_avg_v;
                }
                if (measure_level < 6U) {
                    ++measure_level;
                    g_foc_measure_r.level = measure_level;
                    measure_ticks = measure_stable_ticks = 0U;
                    current_sum = voltage_sum = voltage_command_sum = iq_abs_sum = 0.0f;
                    g_foc_measure_r.sample_count = 0U;
                    measure_phase = MEASURE_R_RAMP_UP;
                    break;
                }
                g_foc_measure_r.delta_current_a = g_foc_measure_r.current_points_a[3] - g_foc_measure_r.current_points_a[0];
                g_foc_measure_r.delta_voltage_v = g_foc_measure_r.voltage_points_v[3] - g_foc_measure_r.voltage_points_v[0];
                if (!(g_foc_measure_r.delta_current_a > 1.0f) || !MeasureR_Fit()) {
                    MeasureR_Stop(MotorControl, FOC_MEASURE_R_UNSTABLE);
                    return;
                }
'''.replace('\n','\r\n')
s=s[:start]+block+s[end:]
sub('            MotorControl->idRef = MEASURE_R_CURRENT_A *', '            MotorControl->idRef = MeasureR_Target() *')
sub('                    g_foc_measure_r.delta_voltage_v / g_foc_measure_r.delta_current_a;', '                    g_foc_measure_r.fit_resistance_ohm;')
p.write_bytes(s.encode('gbk'))
p=r/'FOC_Migrated/foc_measure.h';b=p.read_bytes();needle=b'} FOC_MeasureRResult_TypeDef;';assert b.count(needle)==1
b=b.replace(needle,'''    /* 升降扫描的实际电流、电压及拟合质量，单位A、V、欧。 */
    float current_points_a[7], voltage_points_v[7];
    float fit_resistance_ohm, fit_max_error_v, fit_r_squared, hysteresis_v;
} FOC_MeasureRResult_TypeDef;'''.replace('\n','\r\n').encode('gbk'));p.write_bytes(b)
