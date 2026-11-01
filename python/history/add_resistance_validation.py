from pathlib import Path
r=Path(__file__).resolve().parents[2]
p=r/'FOC_Migrated/foc_measure.c';s=p.read_bytes().decode('gbk')
a='measure_r_targets[7] = {1.5f, 2.0f, 2.5f, 3.0f, 2.5f, 2.0f, 1.5f}'
assert s.count(a)==1
s=s.replace(a,'measure_r_targets[8] = {1.5f, 2.0f, 2.5f, 3.0f, 2.5f, 2.0f, 1.5f, 2.25f}')
a='    measure_level = 0U;';assert s.count(a)==1
s=s.replace(a,a+'''\r\n    g_foc_measure_r.validation_passed = 0U;
    g_foc_measure_r.validation_current_a = 0.0f;
    g_foc_measure_r.validation_voltage_v = 0.0f;
    g_foc_measure_r.validation_error_v = 0.0f;'''.replace('\n','\r\n'))
start=s.index('                g_foc_measure_r.current_points_a[measure_level] =')
end=s.index('                measure_ticks = 0U;\r\n                measure_phase = MEASURE_R_RAMP_DOWN;',start)
s=s[:start]+'''                if (measure_level < 7U) {
                    g_foc_measure_r.current_points_a[measure_level] = g_foc_measure_r.current_avg_a;
                    g_foc_measure_r.voltage_points_v[measure_level] = g_foc_measure_r.voltage_command_avg_v;
                }
                if (measure_level == 0U) {
                    g_foc_measure_r.low_current_avg_a = g_foc_measure_r.current_avg_a;
                    g_foc_measure_r.low_voltage_command_avg_v = g_foc_measure_r.voltage_command_avg_v;
                }
                if (measure_level == 6U) {
                    g_foc_measure_r.delta_current_a = g_foc_measure_r.current_points_a[3] - g_foc_measure_r.current_points_a[0];
                    g_foc_measure_r.delta_voltage_v = g_foc_measure_r.voltage_points_v[3] - g_foc_measure_r.voltage_points_v[0];
                    if (!(g_foc_measure_r.delta_current_a > 1.0f) || !MeasureR_Fit()) {
                        MeasureR_Stop(MotorControl, FOC_MEASURE_R_UNSTABLE);
                        return;
                    }
                }
                if (measure_level < 7U) {
                    ++measure_level;
                    g_foc_measure_r.level = measure_level;
                    measure_ticks = measure_stable_ticks = 0U;
                    current_sum = voltage_sum = voltage_command_sum = iq_abs_sum = 0.0f;
                    g_foc_measure_r.sample_count = 0U;
                    measure_phase = MEASURE_R_RAMP_UP;
                    break;
                }
                /* 冻结七点拟合参数，用未参与拟合的2.25 A平台独立验证。 */
                g_foc_measure_r.validation_current_a = g_foc_measure_r.current_avg_a;
                g_foc_measure_r.validation_voltage_v = g_foc_measure_r.voltage_command_avg_v;
                g_foc_measure_r.validation_error_v = g_foc_measure_r.validation_voltage_v -
                    (g_foc_measure_r.fit_resistance_ohm * g_foc_measure_r.validation_current_a + g_foc_measure_r.voltage_offset_v);
                if (!(isfinite(g_foc_measure_r.validation_error_v) && fabsf(g_foc_measure_r.validation_error_v) <= 0.005f)) {
                    MeasureR_Stop(MotorControl, FOC_MEASURE_R_UNSTABLE);
                    return;
                }
                g_foc_measure_r.validation_passed = 1U;
'''.replace('\n','\r\n')+s[end:]
p.write_bytes(s.encode('gbk'))
p=r/'FOC_Migrated/foc_measure.h';b=p.read_bytes();needle=b'} FOC_MeasureRResult_TypeDef;';assert b.count(needle)==1
b=b.replace(needle,'''    /* 独立验证不参与拟合；通过只表示当前模型预测一致，并非精度标定。 */
    float validation_current_a, validation_voltage_v, validation_error_v;
    uint32_t validation_passed;
} FOC_MeasureRResult_TypeDef;'''.replace('\n','\r\n').encode('gbk'));p.write_bytes(b)
folder=r/'MDK-ARM';b=(folder/'codex_resistance_fit.uvprojx').read_bytes().replace(b'Objects_ResistanceFit',b'Objects_ResistanceValidated')
(folder/'codex_resistance_validated.uvprojx').write_bytes(b)
(folder/'codex_resistance_validated.uvoptx').write_bytes((folder/'codex_resistance_fit.uvoptx').read_bytes())
