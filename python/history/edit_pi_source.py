from pathlib import Path

root = Path(__file__).resolve().parents[2]
p = root/'FOC_Migrated/config/foc_port.h'
b = p.read_bytes()
needle = b'#define FOC_CURRENT_BANDWIDTH_TEST     0U'
assert b.count(needle) == 1
addition = '''
/* 电流PI的R/L来源：0=电机参数，1=有效识别值；未识别完整时使用电机参数。 */
#ifndef FOC_CURRENT_PI_USE_IDENTIFIED_RL
#define FOC_CURRENT_PI_USE_IDENTIFIED_RL 0U
#endif
#if (FOC_CURRENT_PI_USE_IDENTIFIED_RL != 0U) && (FOC_CURRENT_PI_USE_IDENTIFIED_RL != 1U)
#error FOC_CURRENT_PI_USE_IDENTIFIED_RL_must_be_0_or_1
#endif
'''.replace('\n','\r\n').encode('gbk')
p.write_bytes(b.replace(needle, needle+addition))
p = root/'FOC_Migrated/foc_task.c'
s = p.read_bytes().decode('gbk')
needle = 'float g_current_loop_ki = 0.0f;'
assert s.count(needle)==1
s = s.replace(needle, needle+'\r\n/* 实际生效来源：0=电机参数，1=本次上电有效识别结果。 */\r\nvolatile uint32_t g_current_pi_parameter_source = 0U;')
start = s.index('static void MotorControl_CurrentLoopGains_Init(void)')
end = s.index('\r\n/**',start)
body = '''static void MotorControl_CurrentLoopGains_Init(void)
{
    static bool applied = false;
    static float last_r, last_ld, last_lq;
    float r = MotorControl.motor_phase_resistance;
    float ld = MotorControl.motor_d_inductance;
    float lq = MotorControl.motor_q_inductance;
    uint32_t source = 0U;
    float delay, wci, kp_d, ki_d, kp_q, ki_q;

#if (FOC_CURRENT_PI_USE_IDENTIFIED_RL == 1U)
    /* 只使用相参数；平均电感同时用于d/q轴，不覆盖电机参数或写Flash。 */
    if (g_foc_measure_r.status == FOC_MEASURE_R_SUCCESS &&
        g_foc_measure_l.status == FOC_MEASURE_L_SUCCESS &&
        g_foc_measure_l.result_valid == 1U &&
        isfinite(g_foc_measure_r.resistance_ohm) && g_foc_measure_r.resistance_ohm > 0.0f &&
        isfinite(g_foc_measure_l.inductance_h) && g_foc_measure_l.inductance_h > 0.0f) {
        r = g_foc_measure_r.resistance_ohm;
        ld = lq = g_foc_measure_l.inductance_h;
        source = 1U;
    }
#endif
    /* 相同来源和R/L不重复计算，以免覆盖Watch手动调节的PI。 */
    if (applied && source == g_current_pi_parameter_source &&
        r == last_r && ld == last_ld && lq == last_lq) return;
    delay = 1.5f * Current_Ts;
    if (!(isfinite(r) && r > 0.0f && isfinite(ld) && ld > 0.0f &&
          isfinite(lq) && lq > 0.0f && isfinite(delay) && delay > 0.0f &&
          isfinite(FOC_CURRENT_LOOP_KT) && FOC_CURRENT_LOOP_KT > 0.0f)) return;
    wci = FOC_CURRENT_LOOP_KT / delay;
    kp_d = ld * wci * MotorControl.current_loop_kp_scale;
    ki_d = r / ld * MotorControl.current_loop_ki_scale;
    kp_q = lq * wci * MotorControl.current_loop_kp_scale;
    ki_q = r / lq * MotorControl.current_loop_ki_scale;
    if (!(isfinite(wci) && isfinite(kp_d) && kp_d > 0.0f &&
          isfinite(ki_d) && ki_d > 0.0f && isfinite(kp_q) && kp_q > 0.0f &&
          isfinite(ki_q) && ki_q > 0.0f)) return;

    MotorControl.current_loop_model.equivalent_delay = delay;
    MotorControl.current_loop_model.bandwidth_wci = wci;
    MotorControl.current_loop_model.id_kp = MotorControl.id_Kp = kp_d;
    MotorControl.current_loop_model.id_ki = MotorControl.id_Ki = ki_d;
    MotorControl.current_loop_model.iq_kp = MotorControl.iq_Kp = kp_q;
    MotorControl.current_loop_model.iq_ki = MotorControl.iq_Ki = ki_q;
    g_current_loop_kp = kp_d;
    g_current_loop_ki = ki_d;
    MotorControl.current_loop_bandwidth = wci / _2PI;
    FOC.Id_int = FOC.Iq_int = 0.0f;
    last_r = r; last_ld = ld; last_lq = lq;
    g_current_pi_parameter_source = source;
    applied = true;
}
'''.replace('\n','\r\n')
s = s[:start]+body+s[end:]
needle='\t\tif(ModeNeedPwm(MotorControl.ModeNow))'
assert s.count(needle)==1
s=s.replace(needle,'        /* 从失能进入控制前完成参数切换，不能在PWM运行中改PI。 */\r\n        if (ModeLast == Motor_Disable) MotorControl_CurrentLoopGains_Init();\r\n'+needle)
needle='\t\tcase Motor_Disable:\r\n\t\t\tPWM_TurnOnHighSides();'
assert s.count(needle)==1
s=s.replace(needle,'\t\tcase Motor_Disable:\r\n            MotorControl_CurrentLoopGains_Init();\r\n\t\t\tPWM_TurnOnHighSides();')
p.write_bytes(s.encode('gbk'))
p=root/'FOC_Migrated/foc_task.h'
b=p.read_bytes();needle=b'void Loop_State_Reset(void);';assert b.count(needle)==1
p.write_bytes(b.replace(needle,needle+b'\r\nextern volatile uint32_t g_current_pi_parameter_source;'))
