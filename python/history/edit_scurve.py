from pathlib import Path

root = Path(__file__).resolve().parents[2] / 'FOC_Migrated'

def edit(path, changes):
    data = path.read_bytes()
    for old, new in changes:
        old, new = old.encode('gbk'), new.encode('gbk')
        assert data.count(old) == 1, (str(path), old[:90], data.count(old))
        data = data.replace(old, new, 1)
    assert data.decode('gbk').encode('gbk') == data
    path.write_bytes(data)

port = root / 'config/foc_port.h'
edit(port, [('/* PWM 死区补偿：1=启用，0=关闭。 */', '''/* 普通位置轨迹：0=梯形，1=七段S形；带宽测试不使用此规划器。 */
#ifndef FOC_POSITION_TRAJECTORY_TYPE
#define FOC_POSITION_TRAJECTORY_TYPE  1U
#endif
#if (FOC_POSITION_TRAJECTORY_TYPE != 0U) && (FOC_POSITION_TRAJECTORY_TYPE != 1U)
#error FOC_POSITION_TRAJECTORY_TYPE_must_be_0_or_1
#endif
/* S形加速度过渡时间，单位s；jerk上限=min(posAcc,posDec)/此时间。 */
#define FOC_POSITION_SCURVE_ACCEL_TIME_S 0.1f

/* PWM 死区补偿：1=启用，0=关闭。 */'''.replace('\n', '\r\n'))])

header = root / 'foc_traptraj.h'
edit(header, [
    ('    float Ydd;\n', '    float Ydd;\n    float Yddd;                  /* 当前规划jerk，rad/s^3；梯形填0，段切换不连续。 */\n'),
    ('    float t_total;\n', '    float t_total;\n    float t_jerk;                /* S形单段jerk作用时间，单位s。 */\n'),
    ('void TRAJ_plan(', 'void TRAJ_Reset(float position);\nvoid TRAJ_plan('),
])

planner = '''void TRAJ_Reset(float position)
{
    Traj = (Traj_TypeDef){0};
    Traj.Y = isfinite(position) ? position : 0.0f;
    Traj.start_position = Traj.Y;
    Traj.end_position = Traj.Y;
    Traj.profile_done = true;
}

#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
/* shortcut: 仅支持零初速和零初加速度，需不断速换目标时应改为在线规划器。 */
static void TRAJ_SCurvePlan(float position, float start_position, float start_velocity,
                           float Vmax, float Amax, float Dmax)
{
    float distance, acceleration, jerk, tj, ta, tv, velocity, sign;
    TRAJ_Reset(start_position);
    if (!(isfinite(position) && isfinite(start_position) && isfinite(start_velocity) &&
          isfinite(Vmax) && isfinite(Amax) && isfinite(Dmax) &&
          Vmax > 0.0f && Amax > 0.0f && Dmax > 0.0f &&
          FOC_POSITION_SCURVE_ACCEL_TIME_S > 0.0f && fabsf(start_velocity) < 1e-6f)) {
        return;
    }
    distance = fabsf(position - start_position);
    if (!isfinite(distance)) return;
    if (distance == 0.0f) return;
    sign = position > start_position ? 1.0f : -1.0f;
    acceleration = fast_min(Amax, Dmax);
    jerk = acceleration / FOC_POSITION_SCURVE_ACCEL_TIME_S;
    tj = fast_min(FOC_POSITION_SCURVE_ACCEL_TIME_S, sqrtf(Vmax / jerk));
    ta = fast_max(0.0f, Vmax / (jerk * tj) - tj);
    tv = 0.0f;
    /* 加减速所需距离=峰值速度乘单侧加速时间；短行程降低峰值。 */
    if (distance >= Vmax * (2.0f * tj + ta)) {
        tv = (distance - Vmax * (2.0f * tj + ta)) / Vmax;
    } else if (distance < 2.0f * jerk * tj * tj * tj) {
        tj = cbrtf(distance / (2.0f * jerk));
        ta = 0.0f;
    } else {
        ta = fast_max(0.0f, 0.5f * (sqrtf(tj * tj + 4.0f * distance / (jerk * tj)) - 3.0f * tj));
    }
    velocity = jerk * tj * (tj + ta);
    if (!(isfinite(jerk) && isfinite(velocity) && isfinite(tv) &&
          isfinite(4.0f * tj + 2.0f * ta + tv) && tj > 0.0f)) return;
    Traj.end_position = position;
    Traj.acc = sign * jerk * tj;
    Traj.dec = -Traj.acc;
    Traj.vel = sign * velocity;
    Traj.t_jerk = tj;
    Traj.t_acc = 2.0f * tj + ta;
    Traj.t_dec = Traj.t_acc;
    Traj.t_vel = tv;
    Traj.t_total = 2.0f * Traj.t_acc + tv;
    Traj.acc_distance = start_position + 0.5f * Traj.vel * Traj.t_acc;
    Traj.profile_done = false;
}

static void TRAJ_SCurveEval(float t)
{
    float tj = Traj.t_jerk;
    float ta = fast_max(0.0f, Traj.t_acc - 2.0f * tj);
    const float durations[7] = {tj, ta, tj, Traj.t_vel, tj, ta, tj};
    const int8_t signs[7] = {1, 0, -1, 0, -1, 0, 1};
    float jerk = Traj.acc / tj;
    float x = 0.0f, v = 0.0f, a = 0.0f;
    if (t >= Traj.t_total) {
        Traj.Y = Traj.end_position;
        Traj.Yd = Traj.Ydd = Traj.Yddd = 0.0f;
        Traj.profile_done = true;
        return;
    }
    /* 每次从段起点解析积分，不累计位置环逐拍积分的漂移。 */
    for (uint32_t i = 0U; i < 7U; ++i) {
        float dt = fast_min(t, durations[i]);
        float j = (float)signs[i] * jerk;
        x += v * dt + 0.5f * a * dt * dt + j * dt * dt * dt / 6.0f;
        v += a * dt + 0.5f * j * dt * dt;
        a += j * dt;
        t -= dt;
        if (dt < durations[i]) {
            Traj.Yddd = j;
            break;
        }
    }
    Traj.Y = Traj.start_position + x;
    Traj.Yd = v;
    Traj.Ydd = a;
}
#endif

'''
cfile = root / 'foc_traptraj.c'
edit(cfile, [
    ('Traj_TypeDef Traj;\n', 'Traj_TypeDef Traj;\n\n' + planner),
    ('void TRAJ_plan(float position, float start_position, float start_velocity, float Vmax, float Amax, float Dmax)\n{',
     '''void TRAJ_plan(float position, float start_position, float start_velocity, float Vmax, float Amax, float Dmax)
{
#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
    TRAJ_SCurvePlan(position, start_position, start_velocity, Vmax, Amax, Dmax);
#else
    Traj.Yddd = 0.0f;'''),
    ('    Traj.profile_done = false;              /* 标记轨迹进行中 */\n}',
     '    Traj.profile_done = false;              /* 标记轨迹进行中 */\n#endif\n}'),
    ('    float t = Traj.tick * Position_Ts;\n',
     '    float t = Traj.tick * Position_Ts;\n#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)\n    TRAJ_SCurveEval(t);\n#else\n'),
    ('        Traj.profile_done = true;\n    }\n}\n\nfloat TRAJ_Get_Y',
     '        Traj.profile_done = true;\n    }\n#endif\n}\n\nfloat TRAJ_Get_Y'),
])

run = root / 'foc_run.c'
edit(run, [
    ('        if (MotorControl->posRefUpdated == true)\r\n', '''#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
        /* 运动中只保留最新命令，当前S形结束后再规划下一段。 */
        if (MotorControl->posRefUpdated && Traj.profile_done)
#else
        if (MotorControl->posRefUpdated == true)
#endif
'''.replace('\n','\r\n')),
    ('            MotorControl->posShadow = theta_mech;\r\n', '''#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
            MotorControl->posShadow = Traj.Y;
#else
            MotorControl->posShadow = theta_mech;
#endif
'''.replace('\n','\r\n')),
    ('        float pos_error_abs = fast_abs(theta_mech - position_ref_internal);', '''#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
        /* 排队目标尚未执行，到位判断只看当前轨迹终点。 */
        position_ref_internal = Traj.end_position;
#endif
        float pos_error_abs = fast_abs(theta_mech - position_ref_internal);'''.replace('\n','\r\n')),
    ('        extern Traj_TypeDef Traj;\r\n', '''        extern Traj_TypeDef Traj;
#if (FOC_POSITION_TRAJECTORY_TYPE == 1U)
        /* 速度环频率独立于位置环，不能用待执行目标提前拉动电机。 */
        position_ref_internal = Traj.end_position;
#endif
'''.replace('\n','\r\n')),
])

task = root / 'foc_task.c'
data = task.read_bytes()
begin = data.index(b'\textern Traj_TypeDef Traj;')
end = data.index(b'\r\n', data.index(b'\tTraj.profile_done ', begin)) + 2
old = data[begin:end].decode('gbk')
edit(task, [(old, '\tTRAJ_Reset(MotorControl.posShadow);  /* 清除上一段轨迹及S形求值状态。 */\r\n')])
print('S形接入完成，保留源文件编码与既有换行。')
