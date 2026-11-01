"""小行程轨迹实测：共享MKLink，测试结束恢复限值并失能。"""
from pathlib import Path
import json
import math
import struct
import sys
import time
import subprocess

class SharedCLI:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def call(self, capability, arguments=None):
        result = subprocess.run(['D:/exe/Mklink-AI-Probe/mklink-sidecar.exe', 'runtime', 'call',
            capability, '--arguments', json.dumps(arguments or {}), '--probe', 'Tomcat_mklink'],
            capture_output=True, encoding='utf-8', errors='replace', check=False)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result.stdout)
    def watch(self, names): return self.call('watch', {'names':names})['rows']
    def write_memory(self, address, data):
        result = self.call('write_memory', {'address':hex(address), 'data_hex':data.hex(), 'verify':True})
        assert result.get('verified'), result
connect_shared = SharedCLI

root = Path(__file__).resolve().parents[2] / '.mklink'
kind = sys.argv[1]
assert kind in ('trap', 'scurve')
folder = 'Objects_SCurve' if kind == 'scurve' else 'Objects_TrapRegression'
source = str(root.parent / 'MDK-ARM' / 'STM32g474vet6' / 'STM32g474vet6.axf')
parameters = ['posAcc', 'posDec', 'pos_maxspeed', 'speed_limit', 'current_limit']
out = {'kind': kind, 'axf': source, 'captures': []}

with connect_shared(probe='Tomcat_mklink', axf=source, name='Position trajectory verification') as d:
    rows = d.watch(['MotorControl.ModeNow', 'FOC.Vbus_filt', 'Encoder.theta_mech',
                    'Encoder.vel_mech', 'eeprom_adc_calib_valid', 'eeprom_encoder_calib_valid',
                    'ProtectParam.fault_code', 'MotorControl.posRef',
                    'MotorControl.pos_Kp'] + ['MotorControl.' + x for x in parameters])
    values = {x['name']: x['value'] for x in rows}
    addresses = {x['name']: int(x['address'], 16) for x in rows}
    out['before'] = values
    print('preflight', json.dumps(values), flush=True)
    assert str(values['MotorControl.ModeNow']).startswith('0 '), values
    assert 18 < values['FOC.Vbus_filt'] < 40, values
    assert abs(values['Encoder.vel_mech']) < .5, values
    assert values['eeprom_adc_calib_valid'] == values['eeprom_encoder_calib_valid'] == 1, values
    assert str(values['ProtectParam.fault_code']).split()[0] == '0', values
    center = values['Encoder.theta_mech']
    assert math.isfinite(center)
    watch = d.watch(['Traj.Y', 'Encoder.theta_mech', 'Encoder.vel_mech', 'MotorControl.ModeNow',
                     'MotorControl.iqRef', 'FOC.Ia', 'FOC.Iq_filt', 'FOC.Vbus_filt',
                     'MotorControl.posShadow', 'MotorControl.speedShadow', 'PID_Speed.ref_value'])
    # Traj布局由同一AXF成员地址核对，不沿用其他固件的偏移。
    layout = d.watch(['Traj.Yddd', 'Traj.start_position', 'Traj.end_position',
                      'Traj.t_jerk', 'Traj.tick', 'Traj.profile_done'])
    base = int(watch[0]['address'], 16)
    offsets = {x['name']: int(x['address'], 16) - base for x in layout}
    assert offsets == {'Traj.Yddd': 12, 'Traj.start_position': 16, 'Traj.end_position': 24,
                       'Traj.t_jerk': 60, 'Traj.tick': 64, 'Traj.profile_done': 68}, offsets
    sizes = [72, 4, 4, 4, 4, 12, 4, 4, 4, 4, 4]
    regions = [{'address': int(x['address'], 16), 'size': size} for x, size in zip(watch, sizes)]
    watch = watch[:2] + watch[6:8]
    regions = regions[:2] + regions[6:8]
    out['regions'] = [{'name': x['name'], **region} for x, region in zip(watch, regions)]

    def put(name, value):
        d.write_memory(addresses[name], struct.pack('<f', value))

    def target(internal):
        # foc_port.h当前外部位置方向为-1，普通位置仍使用输出轴连续rad。
        put('MotorControl.posRef', -internal)

    def snapshot():
        return {x['name']: x['value'] for x in d.watch(
            ['MotorControl.ModeNow', 'Traj.profile_done', 'Traj.end_position',
             'Traj.Y', 'Traj.Yd', 'Traj.Ydd', 'Traj.Yddd', 'Traj.t_jerk',
             'Encoder.theta_mech', 'MotorControl.posRefUpdated', 'FOC.Vbus_filt', 'g_position_encoder_error', 'g_position_encoder_fault_delta', 'g_position_encoder_fault_ticks', 'g_position_encoder_fault_limit'])}

    def capture(label, expected):
        frames = 3500
        result = d.call('capture_dump', {'regions': regions, 'period': .002,
                                        'frames': frames, 'duration': frames * .002 + .5})
        path = root / (kind + '_30deg_' + label + '.json')
        path.write_text(json.dumps(result), encoding='utf-8')
        state = snapshot()
        out['captures'].append({'label': label, 'path': str(path), 'after': state})
        print(label, json.dumps(state), flush=True)
        assert str(state['MotorControl.ModeNow']).startswith('4 '), state
        assert bool(state['Traj.profile_done']), state
        assert abs(state['Encoder.theta_mech'] - expected) < .025, state
        assert 18 < state['FOC.Vbus_filt'] < 40, state
        return state

    try:
        for name, value in [('posAcc', .2), ('posDec', .2), ('pos_maxspeed', .5),
                            ('speed_limit', .5 * 10.9), ('current_limit', 1.)]:
            put('MotorControl.' + name, value)
        target(center)
        d.call('write_variable', {'name': 'MotorControl.ModeNow', 'value': 4})
        time.sleep(.15)
        amplitude = math.radians(30)
        target(center + amplitude)
        state = capture('positive_5deg', center + amplitude)
        assert (state['Traj.t_jerk'] > 0) == (kind == 'scurve'), state
        target(center - amplitude)
        capture('negative_5deg', center - amplitude)
        put('MotorControl.pos_maxspeed', .5)
        target(center + amplitude)
        time.sleep(.15)
        target(center + amplitude * .5)
        target(center)
        queued = snapshot()
        out['queued'] = queued
        if kind == 'scurve':
            assert abs(queued['Traj.end_position'] - (center + amplitude)) < 1e-5, queued
            assert bool(queued['MotorControl.posRefUpdated']), queued
        capture('latest_target', center)
    finally:
        d.call('write_variable', {'name': 'MotorControl.ModeNow', 'value': 0})
        for name in parameters:
            put('MotorControl.' + name, values['MotorControl.' + name])
        latest = d.watch(['Encoder.theta_mech'])[0]['value']
        target(latest)
        out['final'] = {x['name']: x['value'] for x in d.watch(
            ['MotorControl.ModeNow', 'MotorControl.iqRef', 'MotorControl.idRef'] +
            ['MotorControl.' + x for x in parameters])}
        (root / (kind + '_30deg_board_summary.json')).write_text(json.dumps(out, indent=2), encoding='utf-8')
        print('restored and disabled', json.dumps(out['final']), flush=True)
