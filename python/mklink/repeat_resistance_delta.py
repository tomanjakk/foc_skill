from mklink import connect_shared
from pathlib import Path
import time,json
r=(Path(__file__).resolve().parents[2] / '.mklink')
out=[]
names=['status','resistance_ohm','line_resistance_ohm','low_current_avg_a','low_voltage_command_avg_v','current_avg_a','voltage_command_avg_v','delta_current_a','delta_voltage_v','voltage_offset_v','sample_count','level']
with connect_shared(probe='Tomcat_mklink',axf=str(r.parent/'MDK-ARM/Objects_ResistanceDelta/STM32g474vet6.axf'),name='Resistance differential repeats') as d:
    v=d.watch(['FOC.Vbus_filt','MotorControl.ModeNow'])
    assert 18<v[0]['value']<40 and v[1]['value'].startswith('0 '), v
    try:
        for i in range(3):
            d.call('write_variable',{'name':'MotorControl.ModeNow','value':24})
            time.sleep(2.7)
            rows=d.watch(['g_foc_measure_r.'+n for n in names]+['MotorControl.ModeNow','FOC.Vbus_filt'])
            result={x['name']:x['value'] for x in rows};out.append(result);print(json.dumps(result),flush=True)
            assert result['g_foc_measure_r.status'].startswith('2 '),result
            assert result['MotorControl.ModeNow'].startswith('0 ')
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        print('stop',d.watch(['MotorControl.ModeNow']))
        (r/'resistance_delta_repeats.json').write_text(json.dumps(out,indent=2))
