from pathlib import Path
r=Path(__file__).resolve().parents[2]
p=r/'FOC_Migrated/foc_measure.c'
s=p.read_bytes().decode('gbk')
def sub(a,b):
    global s
    assert s.count(a)==1,(a[:70],s.count(a))
    s=s.replace(a,b)
sub('#define MEASURE_R_CURRENT_A       3.0f','#define MEASURE_R_CURRENT_A       3.0f\r\n#define MEASURE_R_LOW_CURRENT_A   1.5f')
sub('static float iq_abs_sum;','static float iq_abs_sum;\r\nstatic uint32_t measure_level;\r\n\r\nstatic float MeasureR_Target(void)\r\n{\r\n    return measure_level == 0U ? MEASURE_R_LOW_CURRENT_A : MEASURE_R_CURRENT_A;\r\n}')
sub('fabsf(FOC->Id_filt - MEASURE_R_CURRENT_A) <= 0.15f','fabsf(FOC->Id_filt - MeasureR_Target()) <= 0.15f')
sub('    measure_phase = MEASURE_R_PRECHECK;','    measure_phase = MEASURE_R_PRECHECK;\r\n    measure_level = 0U;\r\n    g_foc_measure_r.level = 0U;\r\n    g_foc_measure_r.low_current_avg_a = 0.0f;\r\n    g_foc_measure_r.low_voltage_command_avg_v = 0.0f;\r\n    g_foc_measure_r.delta_current_a = 0.0f;\r\n    g_foc_measure_r.delta_voltage_v = 0.0f;\r\n    g_foc_measure_r.voltage_offset_v = 0.0f;')
sub('            MotorControl->idRef = MEASURE_R_CURRENT_A *\r\n                                  (float)(measure_ticks + 1U) / (float)MEASURE_R_RAMP_TICKS;', '            MotorControl->idRef = (measure_level == 0U ? 0.0f : MEASURE_R_LOW_CURRENT_A) +\r\n                (MeasureR_Target() - (measure_level == 0U ? 0.0f : MEASURE_R_LOW_CURRENT_A)) *\r\n                (float)(measure_ticks + 1U) / (float)MEASURE_R_RAMP_TICKS;')
assert s.count('MotorControl->idRef = MEASURE_R_CURRENT_A;')==2
s=s.replace('MotorControl->idRef = MEASURE_R_CURRENT_A;','MotorControl->idRef = MeasureR_Target();')
sub('fabsf(g_foc_measure_r.current_avg_a - MEASURE_R_CURRENT_A) <= 0.15f','fabsf(g_foc_measure_r.current_avg_a - MeasureR_Target()) <= 0.15f')
sub('                      g_foc_measure_r.voltage_avg_v > 0.0f &&\r\n                      isfinite(g_foc_measure_r.voltage_avg_v)', '                      isfinite(g_foc_measure_r.current_avg_a) &&\r\n                      g_foc_measure_r.voltage_command_avg_v > 0.0f &&\r\n                      isfinite(g_foc_measure_r.voltage_command_avg_v)')
needle='                measure_ticks = 0U;\r\n                measure_phase = MEASURE_R_RAMP_DOWN;'
block='''                if (measure_level == 0U) {
                    g_foc_measure_r.low_current_avg_a = g_foc_measure_r.current_avg_a;
                    g_foc_measure_r.low_voltage_command_avg_v = g_foc_measure_r.voltage_command_avg_v;
                    measure_level = g_foc_measure_r.level = 1U;
                    measure_ticks = measure_stable_ticks = 0U;
                    current_sum = voltage_sum = voltage_command_sum = iq_abs_sum = 0.0f;
                    g_foc_measure_r.sample_count = 0U;
                    measure_phase = MEASURE_R_RAMP_UP;
                    break;
                }
                /* 同向两电流点作差，抵消近似不随电流变化的死区压降。 */
                g_foc_measure_r.delta_current_a = g_foc_measure_r.current_avg_a - g_foc_measure_r.low_current_avg_a;
                g_foc_measure_r.delta_voltage_v = g_foc_measure_r.voltage_command_avg_v - g_foc_measure_r.low_voltage_command_avg_v;
                if (!(isfinite(g_foc_measure_r.delta_current_a) && g_foc_measure_r.delta_current_a > 1.0f &&
                      isfinite(g_foc_measure_r.delta_voltage_v) && g_foc_measure_r.delta_voltage_v > 0.0f &&
                      isfinite(g_foc_measure_r.delta_voltage_v / g_foc_measure_r.delta_current_a))) {
                    MeasureR_Stop(MotorControl, FOC_MEASURE_R_UNSTABLE);
                    return;
                }
                g_foc_measure_r.voltage_offset_v = g_foc_measure_r.low_voltage_command_avg_v -
                    g_foc_measure_r.low_current_avg_a * g_foc_measure_r.delta_voltage_v / g_foc_measure_r.delta_current_a;
                measure_ticks = 0U;
                measure_phase = MEASURE_R_RAMP_DOWN;'''.replace('\n','\r\n')
sub(needle,block)
sub('                    g_foc_measure_r.voltage_avg_v / g_foc_measure_r.current_avg_a;', '                    g_foc_measure_r.delta_voltage_v / g_foc_measure_r.delta_current_a;')
p.write_bytes(s.encode('gbk'))
p=r/'FOC_Migrated/foc_measure.h';b=p.read_bytes();needle=b'} FOC_MeasureRResult_TypeDef;';assert b.count(needle)==1
b=b.replace(needle,'''    /* 两点差分诊断：低电流点、高低点差值及估计的固定压降。 */
    uint32_t level;
    float low_current_avg_a, low_voltage_command_avg_v;
    float delta_current_a, delta_voltage_v, voltage_offset_v;
} FOC_MeasureRResult_TypeDef;'''.replace('\n','\r\n').encode('gbk'));p.write_bytes(b)
