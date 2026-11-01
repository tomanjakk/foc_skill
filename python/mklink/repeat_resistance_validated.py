from mklink import connect_shared
from pathlib import Path
import time,json
r=(Path(__file__).resolve().parents[2] / '.mklink')
out=[]
names=['status','resistance_ohm','line_resistance_ohm','fit_resistance_ohm','fit_max_error_v','fit_r_squared','hysteresis_v','voltage_offset_v','sample_count','level','validation_current_a','validation_voltage_v','validation_error_v','validation_passed']
with connect_shared(probe='Tomcat_mklink',axf=str(r.parent/'MDK-ARM/Objects_ResistanceValidated/STM32g474vet6.axf'),name='Resistance independent validation') as d:
    rows=d.watch(['FOC.Vbus_filt','MotorControl.ModeNow'])
    assert 18<rows[0]['value']<40 and rows[1]['value'].startswith('0 '),rows
    try:
        for trial in range(3):
            d.call('write_variable',{'name':'MotorControl.ModeNow','value':24})
            time.sleep(4)
            rows=d.watch(['g_foc_measure_r.'+n for n in names]+['MotorControl.ModeNow','FOC.Vbus_filt'])
            v={x['name']:x['value'] for x in rows}
            points=d.watch(['g_foc_measure_r.'+name+'['+str(i)+']' for name in ['current_points_a','voltage_points_v'] for i in range(7)])
            v['points']={x['name']:x['value'] for x in points};out.append(v);print(json.dumps(v),flush=True)
            if not v['g_foc_measure_r.status'].startswith('2 '):break
            assert v['MotorControl.ModeNow'].startswith('0 ')
            assert v['g_foc_measure_r.validation_passed']==1
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        print('stop',d.watch(['MotorControl.ModeNow']))
        (r/'resistance_validated_repeats.json').write_text(json.dumps(out,indent=2))
