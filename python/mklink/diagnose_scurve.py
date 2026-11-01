"""S 形正常位置模式实测；限流、采集，结束时失能并恢复参数。"""
import json
import math
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.mklink/scurve_diagnosis'
OUT.mkdir(parents=True, exist_ok=True)
CLI = 'D:/exe/Mklink-AI-Probe/mklink-sidecar.exe'


def call(name, args=None):
    r = subprocess.run([CLI, 'runtime', 'call', name, '--arguments', json.dumps(args or {}),
                        '--probe', 'Tomcat_mklink'], capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode: raise RuntimeError(r.stdout + r.stderr)
    return json.loads(r.stdout)


def watch(names): return call('watch', {'names': names})['rows']


params = ['current_limit', 'speed_limit', 'pos_maxspeed', 'posAcc', 'posDec']
rows = watch(['MotorControl.ModeNow', 'FOC.Vbus_filt', 'Encoder.theta_mech', 'Encoder.vel_mech',
              'eeprom_adc_calib_valid', 'eeprom_encoder_calib_valid', 'ProtectParam.fault_code',
              'MotorControl.posRef'] + ['MotorControl.' + n for n in params])
initial = {r['name']: r['value'] for r in rows}
addresses = {r['name']: int(r['address'], 16) for r in rows}
assert str(initial['MotorControl.ModeNow']).startswith('0 '), initial
assert 18 < initial['FOC.Vbus_filt'] < 40, initial
assert abs(initial['Encoder.vel_mech']) < .5, initial
assert initial['eeprom_adc_calib_valid'] == initial['eeprom_encoder_calib_valid'] == 1
assert str(initial['ProtectParam.fault_code']).split()[0] == '0'
center = initial['Encoder.theta_mech']
assert math.isfinite(center)
result = {'initial': initial, 'captures': []}
layout = watch(['Traj.Y', 'Encoder.theta_mech', 'Encoder.vel_mech', 'PID_Speed.ref_value',
                'PID_Speed.fbk_value', 'MotorControl.iqRef', 'FOC.Iq_filt', 'FOC.Vbus_filt',
                'adc_complete_sample_sequence', 'g_encoder_read_success_count'])
regions = [{'address': int(r['address'], 16), 'size': 16 if i == 0 else 4} for i, r in enumerate(layout)]
result['regions'] = regions


def put(name, value):
    response = call('write_memory', {'address': hex(addresses[name]),
                                    'data_hex': struct.pack('<f', value).hex(), 'verify': True})
    assert response.get('verified'), response


def move(label, offset, duration):
    put('MotorControl.posRef', -(center + offset))
    cap = call('capture_dump', {'regions': regions, 'period': .001,
                               'frames': int(duration * 1000), 'duration': duration + .5})
    (OUT / (label + '.json')).write_text(json.dumps(cap), encoding='utf-8')
    state = {r['name']: r['value'] for r in watch(['MotorControl.ModeNow', 'Traj.Y', 'Traj.Yd',
             'Traj.Ydd', 'Traj.Yddd', 'Traj.profile_done', 'Encoder.theta_mech',
             'g_position_encoder_error', 'adc_sync_error_count', 'FOC.Vbus_filt'])}
    peaks = [0.] * 5
    for sample in cap['samples']:
        b = [bytes.fromhex(r['data_hex']) for r in sample['regions']]
        y, yd, ydd, jerk = struct.unpack('<4f', b[0])
        values = [struct.unpack('<f', v)[0] for v in b[1:8]]
        pos, vel, ref, fbk, iq, iqf, bus = values
        assert all(math.isfinite(v) for v in [y, yd, ydd, jerk] + values)
        for i, v in enumerate([abs(y-pos), abs(vel), abs(ref), abs(iq), abs(iqf)]): peaks[i] = max(peaks[i], v)
    record = {'label': label, 'offset_rad': offset, 'samples': cap['sample_count'],
              'peaks_error_vel_ref_iq_iqf': peaks, 'stats': cap['stats'], 'state': state}
    result['captures'].append(record)
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(record), flush=True)
    assert str(state['MotorControl.ModeNow']).startswith('4 '), state
    assert state['g_position_encoder_error'] == 0 and state['adc_sync_error_count'] == 0, state
    assert state['Traj.profile_done'] and abs(state['Encoder.theta_mech']-(center+offset)) < .025, state
    assert peaks[0] < .1 and peaks[3] <= 2.01 and 18 < state['FOC.Vbus_filt'] < 40, record


try:
    for n, v in [('current_limit', 1.), ('speed_limit', 5.45), ('pos_maxspeed', .5)]: put('MotorControl.'+n, v)
    put('MotorControl.posRef', -center)
    call('write_variable', {'name': 'MotorControl.ModeNow', 'value': 4})
    move('entry_hold', 0, 3)
    move('small_positive', .1, 3)
    move('small_negative', -.1, 3)
    for n, v in [('current_limit', 2.), ('speed_limit', 21.8), ('pos_maxspeed', 2.)]: put('MotorControl.'+n, v)
    move('one_rad_positive', 1, 3)
    move('one_rad_negative', -1, 3)
    put('MotorControl.speed_limit', initial['MotorControl.speed_limit'])
    put('MotorControl.pos_maxspeed', initial['MotorControl.pos_maxspeed'])
    move('ten_rad_positive', 10, 5)
    move('ten_rad_negative', -10, 5)
    move('return', 0, 5)
    result['passed'] = True
finally:
    call('write_variable', {'name': 'MotorControl.ModeNow', 'value': 0})
    for n in params: put('MotorControl.'+n, initial['MotorControl.'+n])
    pos = watch(['Encoder.theta_mech'])[0]['value']
    put('MotorControl.posRef', -pos)
    result['final'] = {r['name']: r['value'] for r in watch(['MotorControl.ModeNow', 'MotorControl.iqRef', 'MotorControl.idRef'])}
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('disabled', json.dumps(result['final']), flush=True)
