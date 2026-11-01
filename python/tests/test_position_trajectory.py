"""编译实际轨迹C及位置任务函数；硬件相关函数仅使用测试桩。"""
import ctypes
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
FOC = ROOT / 'FOC_Migrated'
BUILD = ROOT / '.mklink/trajectory_host'
DT = 1.0 / 5000.0


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


STUB = r'''
#include <math.h>
#include <string.h>
#include "foc_port.h"
#include "foc_utils.h"
#include "foc_traptraj.h"
typedef struct {float Id_int,Iq_int;} FOC_TypeDef;
typedef struct {
 float posRef,posShadow,speedShadow,pos_maxspeed,speed_limit,posAcc,posDec;
 float pos_error_window,pos_Kp,current_limit,idRef,iqRef,vf_phase,if_phase;
 int ModeNow;
 bool posRefUpdated,isReachTargetPos;
} MotorControl_TypeDef;
typedef struct {float error_sum,ref_value,fbk_value,error,error_last,output;} PID_TypeDef;
typedef struct {float theta_mech,theta_elec,vel_mech,vel_elec;} TestEncoder;
extern FOC_TypeDef FOC;
extern MotorControl_TypeDef MotorControl;
extern PID_TypeDef PID_Speed;
extern TestEncoder Encoder;
extern int speedloop_count,positionloop_count;
extern float pos_ref_last;
enum {VF_Mode=1,Position_Mode=4,MIT_Mode=8,Cogging_Calibration=9};
void VF_Mode_Reset(void);
void IF_Mode_Reset(void);
void MIT_SteerTrajectory_Reset(void);
void Cogging_ModeReset(void);
void Run_External_Speed_Loop(MotorControl_TypeDef*,PID_TypeDef*,float,float,float);
void FOC_Current(FOC_TypeDef*,MotorControl_TypeDef*,float,float);
'''

WRAPPER = r'''
FOC_TypeDef FOC;
MotorControl_TypeDef MotorControl;
PID_TypeDef PID_Speed;
TestEncoder Encoder;
int speedloop_count,positionloop_count;
float pos_ref_last;
float feedback_bias;
void VF_Mode_Reset(void) {}
void IF_Mode_Reset(void) {}
void MIT_SteerTrajectory_Reset(void) {}
void Cogging_ModeReset(void) {}
void FOC_Current(FOC_TypeDef *f,MotorControl_TypeDef *m,float a,float b) {}
void Run_External_Speed_Loop(MotorControl_TypeDef *m,PID_TypeDef *p,float r,float f,float l) {p->ref_value=r;}
void host_plan(float end,float start,float velocity,float vmax,float amax,float dmax) {
 TRAJ_plan(end,start,velocity,vmax,amax,dmax);
}
void host_sample(unsigned tick,float *out) {
 Traj.tick=tick; TRAJ_eval();
 out[0]=Traj.Y;out[1]=Traj.Yd;out[2]=Traj.Ydd;out[3]=Traj.Yddd;
 out[4]=Traj.t_total;out[5]=Traj.end_position;out[6]=(float)Traj.profile_done;
 out[7]=Traj.t_jerk;out[8]=Traj.t_acc;out[9]=Traj.t_vel;
}
void host_reset(float x) {
 feedback_bias=0.0f;
 memset(&MotorControl,0,sizeof(MotorControl));
 Encoder.theta_mech=x; MotorControl.ModeNow=Position_Mode;
 MotorControl.posRef=x/(float)MOTOR_POSITION_COMMAND_SIGN;
 MotorControl.pos_maxspeed=0.5f;MotorControl.speed_limit=100.0f;
 MotorControl.posAcc=2.0f;MotorControl.posDec=3.0f;
 MotorControl.current_limit=1.0f;MotorControl.pos_Kp=8.0f;
 MotorControl.pos_error_window=0.0001f;
 Loop_State_Reset();
}
void host_target(float internal) {MotorControl.posRef=internal/(float)MOTOR_POSITION_COMMAND_SIGN;}
void host_bias(float bias) {feedback_bias=bias;}
void host_set_integral(float value) {PID_Speed.error_sum=value;}
float host_get_integral(void) {return PID_Speed.error_sum;}
void host_control_tick(float *out) {
 for (unsigned i=0;i<POSITION_LOOP_DIVIDER;++i) {
  Encoder.theta_mech=Traj.Y+feedback_bias;
  Task_Position_Mode(&FOC,&MotorControl,&PID_Speed);
 }
 out[0]=Traj.Y;out[1]=Traj.Yd;out[2]=Traj.Ydd;out[3]=Traj.Yddd;
 out[4]=Traj.end_position;out[5]=(float)Traj.profile_done;
 out[6]=(float)MotorControl.posRefUpdated;out[7]=PID_Speed.ref_value;
 out[8]=MotorControl.posShadow;out[9]=MotorControl.speedShadow;
}
'''


def build_library(kind, baseline=False):
    compiler = os.environ.get('TRAJECTORY_TEST_CC') or shutil.which('gcc')
    if not compiler:
        compiler = 'D:/my_exe/msys2/mingw64/bin/gcc.exe'
    if not Path(compiler).is_file():
        raise RuntimeError('需要本机GCC，请设置TRAJECTORY_TEST_CC。')
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'common_inc.h').write_text(STUB, encoding='gbk')
    task = FOC.joinpath('foc_task.c').read_bytes().decode('gbk')
    run = FOC.joinpath('foc_run.c').read_bytes().decode('gbk')
    utils = FOC.joinpath('config/foc_utils.c').read_bytes().decode('gbk')
    wrapper = '#include "common_inc.h"\n'
    for name in ['fast_abs', 'fast_sq', 'fast_min', 'fast_max', 'fast_sqrt', 'copy_sign', 'sign_hard']:
        wrapper += function(utils, 'float ' + name + '(') + '\n'
    wrapper += function(task, 'void Loop_State_Reset(void)') + '\n'
    wrapper += function(run, 'void Task_Position_Mode(') + '\n' + WRAPPER
    path = BUILD / ('host_baseline.c' if baseline else f'host_{kind}.c')
    path.write_text(wrapper, encoding='gbk')
    cfile = FOC / 'foc_traptraj.c'
    if baseline:
        # 本轮修改前快照用于验证宏0逐点结果；缺快照时不伪造基准。
        with ZipFile(ROOT / '.mklink/scurve_before.zip') as z:
            original = z.read('P50w_Bootloader/FOC_Migrated/foc_traptraj.c').decode('gbk')
        reset = function(cfile.read_bytes().decode('gbk'), 'void TRAJ_Reset(')
        cfile = BUILD / 'baseline_traptraj.c'
        cfile.write_text(original + '\n' + reset, encoding='gbk')
    dll = BUILD / ('baseline.dll' if baseline else f'trajectory_{kind}.dll')
    build_env = os.environ.copy()
    build_env['PATH'] = str(Path(compiler).parent) + os.pathsep + build_env.get('PATH', '')
    subprocess.run([compiler, '-shared', '-O2', '-std=c99', '-fno-strict-aliasing',
                    '-finput-charset=GBK', '-Werror=implicit-function-declaration',
                    f'-DFOC_POSITION_TRAJECTORY_TYPE={kind}',
                    '-I' + str(BUILD), '-I' + str(FOC), '-I' + str(FOC / 'config'),
                    str(cfile), str(path), '-lm', '-o', str(dll)], check=True, env=build_env)
    lib = ctypes.CDLL(str(dll))
    lib.host_plan.argtypes = [ctypes.c_float] * 6
    lib.host_sample.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_float)]
    lib.host_reset.argtypes = [ctypes.c_float]
    lib.host_target.argtypes = [ctypes.c_float]
    lib.host_bias.argtypes = [ctypes.c_float]
    lib.host_set_integral.argtypes = [ctypes.c_float]
    lib.host_get_integral.restype = ctypes.c_float
    lib.host_control_tick.argtypes = [ctypes.POINTER(ctypes.c_float)]
    return lib


def sample(lib, tick=0):
    out = (ctypes.c_float * 10)()
    lib.host_sample(tick, out)
    return list(out)


def control(lib):
    out = (ctypes.c_float * 10)()
    lib.host_control_tick(out)
    return list(out)


class PositionTrajectory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = build_library(1)
        cls.trap = build_library(0)

    def check_profile(self, end, start, vmax, amax, dmax):
        self.s.host_plan(end, start, 0, vmax, amax, dmax)
        first = sample(self.s)
        total = first[4]
        if total == 0:
            self.assertEqual(first[6], 1)
            return
        acceleration = min(amax, dmax)
        jerk = acceleration / 0.1
        n = math.ceil(total / DT)
        previous = [start, 0, 0]
        sign = 1 if end > start else -1
        for tick in range(n):
            s = sample(self.s, tick)
            self.assertTrue(all(math.isfinite(x) for x in s))
            self.assertLessEqual(abs(s[1]), vmax * 1.00005 + 1e-6)
            self.assertLessEqual(abs(s[2]), acceleration * 1.0001 + 1e-5)
            self.assertLessEqual(abs(s[3]), jerk * 1.0001 + 1e-4)
            self.assertGreaterEqual(sign * (s[0] - previous[0]), -3e-5)
            self.assertLessEqual(abs(s[0] - previous[0]), vmax * DT + 3e-5)
            self.assertLessEqual(abs(s[1] - previous[1]), acceleration * DT + 3e-5)
            self.assertLessEqual(abs(s[2] - previous[2]), jerk * DT + 5e-4)
            previous = s[:3]
        s = sample(self.s, n)
        self.assertAlmostEqual(s[0], end, delta=1e-6 + abs(end) * 1e-7)
        self.assertEqual(s[1:4], [0, 0, 0])
        self.assertEqual(s[6], 1)
        # 最后一步不能靠强行钳位掩盖位置、速度或加速度跳变。
        self.assertLessEqual(abs(s[0] - previous[0]), vmax * DT + 3e-5)
        self.assertLessEqual(abs(previous[1]), acceleration * DT + 3e-5)
        self.assertLessEqual(abs(previous[2]), jerk * DT + 5e-4)

    def test_long_short_and_reverse(self):
        for args in [(2, 0, .5, 2, 3), (-2, 0, .5, 2, 3),
                     (.001, 0, 10, 3, 2), (.4, .3, 10, 2, 3),
                     (1, 0, .02, 2, 3), (0, 0, .5, 2, 3),
                     (10.00001, 10, .5, 2, 3)]:
            with self.subTest(args=args):
                self.check_profile(*args)

    def test_random_boundaries(self):
        rng = random.Random(474)
        for _ in range(35):
            start = rng.uniform(-4, 4)
            self.check_profile(start + rng.uniform(-.2, .2), start,
                               rng.uniform(.1, 2), rng.uniform(.5, 8), rng.uniform(.5, 8))

    def test_invalid_inputs_hold(self):
        for end, start, v0, vmax, amax, dmax in [
            (1, 0, 0, 0, 2, 3), (1, 0, 0, 1, -1, 3),
            (1, 0, 0, 1, 2, 0), (float('nan'), 0, 0, 1, 2, 3),
            (1, 0, 0, float('inf'), 2, 3), (1, 0, .1, 1, 2, 3)]:
            self.s.host_plan(end, start, v0, vmax, amax, dmax)
            s = sample(self.s)
            self.assertEqual(s[:4], [start, 0, 0, 0])
            self.assertEqual(s[6], 1)

    def test_latest_target_waits_for_current_end(self):
        self.s.host_reset(0)
        self.s.host_target(.2)
        for _ in range(250):
            control(self.s)
        self.s.host_target(-.1)
        for _ in range(100):
            control(self.s)
        self.s.host_target(.35)
        seen_first_done = False
        first_next = None
        for _ in range(10000):
            s = control(self.s)
            if abs(s[4] - .35) < 1e-6:
                first_next = s
                break
            self.assertAlmostEqual(s[4], .2, places=6)
            seen_first_done |= bool(s[5])
        self.assertTrue(seen_first_done)
        self.assertIsNotNone(first_next)
        self.assertAlmostEqual(first_next[0], .2, delta=1e-5)
        self.assertLess(abs(first_next[1]), .001)
        for _ in range(10000):
            s = control(self.s)
            if s[5]:
                break
        self.assertEqual(s[5:7], [1, 0])
        self.assertAlmostEqual(s[0], .35, places=6)

    def test_mode_reset_discards_previous_trajectory(self):
        self.s.host_reset(0)
        self.s.host_target(1)
        for _ in range(100):
            control(self.s)
        self.s.host_target(-1)
        self.s.host_reset(.3)
        s = control(self.s)
        self.assertAlmostEqual(s[0], .3, places=6)
        self.assertEqual(s[1:4], [0, 0, 0])
        self.assertAlmostEqual(s[4], .3, places=6)
        self.assertEqual(s[5:7], [1, 0])

    def test_trapezoid_still_replans_immediately(self):
        self.trap.host_reset(0)
        self.trap.host_target(1)
        for _ in range(100):
            control(self.trap)
        self.trap.host_target(-1)
        self.assertAlmostEqual(control(self.trap)[4], -1, places=6)

    def test_retarget_keeps_planned_position_and_integral(self):
        self.trap.host_reset(0)
        self.trap.host_target(.2)
        for _ in range(500):
            old = control(self.trap)
        self.trap.host_bias(-.03)
        self.trap.host_set_integral(.4)
        self.trap.host_target(-30)
        new = control(self.trap)
        self.assertAlmostEqual(new[4], -30, places=5)
        self.assertLess(abs(new[0] - old[0]), .001)
        self.assertLess(abs(new[1] - old[1]), .001)
        self.assertAlmostEqual(self.trap.host_get_integral(), .4, places=6)

    def test_macro_zero_matches_before_change(self):
        if not (ROOT / '.mklink/scurve_before.zip').is_file():
            self.skipTest('缺少本轮修改前快照，无法执行逐点基准比较。')
        baseline = build_library(0, baseline=True)
        for args in [(2, 0, 0, .5, 2, 3), (-2, 0, .3, .5, 2, 3),
                     (.001, 0, .7, .5, 2, 3), (0, 0, 0, .5, 2, 3)]:
            self.trap.host_plan(*args)
            baseline.host_plan(*args)
            total = sample(self.trap)[4]
            for tick in range(math.ceil(total / DT) + 2):
                self.assertEqual(sample(self.trap, tick)[:3], sample(baseline, tick)[:3])


if __name__ == '__main__':
    unittest.main()
