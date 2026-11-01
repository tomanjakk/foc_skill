"""按现场原参数记录 S 形切入及正反运动；只写位置和模式，结束失能。"""
import json
import math
from pathlib import Path
import sys
import time

CONFIG = Path(__file__).resolve().parents[1] / 'keil/config.json'
cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
sys.path.append(cfg['mklink_sdk_path'])
from mklink.runtime import request, selected_runtime

info = selected_runtime(cfg['mklink_probe'])
assert info is not None, '共享后台未连接'
out = Path(__file__).resolve().parents[2] / '.mklink/scurve_native'
out.mkdir(parents=True, exist_ok=True)


def api(method, tail, payload=None):
    return request(info, method, '/api/dash/superwatch/' + tail, payload)


symbols = request(info, 'GET', '/api/symbols/status')
assert symbols['loaded'] and not symbols['stale']
assert not (symbols.get('file_source_change') or {}).get('pending')
generation = symbols['generation']
original = api('GET', 'status')
assert original['state'] == 'stopped', '已有采集运行，保留现场并退出'
assert not api('GET', 'recording/status')['active']
expected = {'pos_Kp': 60., 'pos_Ki': 0., 'posAcc': 12.5663706,
            'posDec': 12.5663706, 'pos_maxspeed': 12.5663706,
            'pos_error_window': .01, 'speed_limit': 503.1156, 'current_limit': 30.02}
names = ['MotorControl.' + n for n in expected]
names += ['MotorControl.ModeNow', 'Encoder.theta_mech', 'Encoder.vel_mech',
          'FOC.Vbus_filt', 'eeprom_adc_calib_valid', 'eeprom_encoder_calib_valid',
          'ProtectParam.fault_code']
rows = request(info, 'POST', '/api/device/watch', {'names': names})['rows']
before = {r['name']: r['value'] for r in rows}
for key, value in expected.items():
    assert math.isclose(before['MotorControl.' + key], value, rel_tol=1e-5, abs_tol=1e-6), before
assert str(before['MotorControl.ModeNow']).split()[0] == '0'
assert str(before['ProtectParam.fault_code']).split()[0] == '0'
assert before['eeprom_adc_calib_valid'] == before['eeprom_encoder_calib_valid'] == 1
assert 18 < before['FOC.Vbus_filt'] < 40 and abs(before['Encoder.vel_mech']) < .5
channels = ['FOC.Vbus', 'FOC.Vbus_filt', 'Traj.Y', 'Traj.Yd', 'Traj.Ydd', 'Traj.Yddd',
            'Encoder.theta_mech', 'Encoder.vel_mech', 'PID_Speed.ref_value',
            'MotorControl.iqRef', 'FOC.Iq_filt', 'MotorControl.ModeNow',
            'g_position_encoder_error', 'Traj.profile_done', 'MotorControl.posRef']
added = []
events = []
started = False
recording = False


def put(path, value):
    result = api('POST', 'write', {'path': path, 'generation': generation, 'value': value})
    assert result.get('acknowledged'), result
    events.append(result)
    print(json.dumps(result), flush=True)


def wait_checked(seconds, moving):
    begin = time.monotonic()
    end = begin + seconds
    last = None
    while time.monotonic() < end:
        last = api('GET', 'latest')
        assert last['running'], last
        if last.get('age_seconds') is None:
            time.sleep(.05)
            continue
        assert last['age_seconds'] < 1, last
        sample = last['sample']
        values = {c['name']: v for c, v in zip(sample['channels'], sample['values'])}
        assert all(math.isfinite(float(v)) for v in values.values()), values
        assert 18 < values['FOC.Vbus_filt'] < 40, values
        # 原参数不变；异常大电流或反馈故障时中止本次实测。
        assert abs(values['MotorControl.iqRef']) < 5, values
        assert values['g_position_encoder_error'] == 0, values
        # 共享批次有发送延迟，切入后给最新模式值一个批次的更新时间。
        if moving and time.monotonic() - begin > .2:
            assert values['MotorControl.ModeNow'] == 4, values
        time.sleep(.1)
    assert last.get('sample'), last
    events.append({'elapsed_seconds': seconds, 'snapshot': last})
    print('snapshot', json.dumps(values), flush=True)
    return values


try:
    old_names = {item['name'] for item in original['items']}
    assert old_names <= set(channels), '已有其他观察项，保留现场并退出'
    for name in channels:
        if name not in old_names:
            api('POST', 'add', {'name': name})
            added.append(name)
    api('POST', 'recording/start', {'directory': str(out)})
    recording = True
    api('POST', 'start', {'interval': .001})
    started = True
    wait_checked(.5, False)
    put('MotorControl.posRef', -before['Encoder.theta_mech'])
    put('MotorControl.ModeNow', 4)
    wait_checked(3, True)
    for target in [10., -10., 0., 10., 0.]:
        put('MotorControl.posRef', target)
        values = wait_checked(5, True)
        assert values['Traj.profile_done'] and abs(values['Encoder.theta_mech'] + target) < .025, values
    put('MotorControl.ModeNow', 0)
    wait_checked(.5, False)
    put('MotorControl.posRef', 10.)
    put('MotorControl.ModeNow', 4)
    values = wait_checked(5, True)
    assert values['Traj.profile_done'] and abs(values['Encoder.theta_mech'] + 10) < .025, values
finally:
    try:
        if started:
            put('MotorControl.ModeNow', 0)
            time.sleep(.2)
    finally:
        if recording:
            events.append({'recording': api('POST', 'recording/stop', {})})
        if started:
            api('POST', 'stop', {})
        for name in added:
            api('POST', 'remove', {'name': name})
        api('POST', 'interval', {'interval': original['interval']})
        final_names = names + ['MotorControl.iqRef', 'MotorControl.idRef']
        final_rows = []
        for start in range(0, len(final_names), 16):
            final_rows += request(info, 'POST', '/api/device/watch',
                                  {'names': final_names[start:start + 16]})['rows']
        after = {r['name']: r['value'] for r in final_rows}
        if str(after['MotorControl.ModeNow']).split()[0] == '0':
            put('MotorControl.posRef', -after['Encoder.theta_mech'])
        (out / 'events.json').write_text(json.dumps({'before': before, 'events': events, 'after': after}, indent=2), encoding='utf-8')
        print('final', json.dumps(after), flush=True)
