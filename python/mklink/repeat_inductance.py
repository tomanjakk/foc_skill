from mklink import connect_shared
from pathlib import Path
import time,json
r=(Path(__file__).resolve().parents[2] / '.mklink')
out=[]
with connect_shared(probe='Tomcat_mklink',axf=str(r.parent/'MDK-ARM/Objects_Inductance3/STM32g474vet6.axf'),name='Inductance repeats') as d:
    assert d.watch(['MotorControl.ModeNow'])[0]['value'].startswith('0 ')
    try:
        for i in range(3):
            d.call('write_variable',{'name':'MotorControl.ModeNow','value':25})
            time.sleep(1.1)
            rows=d.watch(['g_foc_measure_l.'+n for n in ['status','reason','result_valid','valid_samples','inductance_uh','rotor_error_deg','rotor_speed_rad_s']]+['MotorControl.ModeNow'])
            item={x['name']:x['value'] for x in rows};out.append(item);print(json.dumps(item),flush=True)
            assert item['g_foc_measure_l.status']==2 and item['g_foc_measure_l.result_valid']==1
            assert item['g_foc_measure_l.valid_samples']==256
            assert item['MotorControl.ModeNow'].startswith('0 ')
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        (r/'inductance_repeats.json').write_text(json.dumps(out,indent=2))
        print('stopped',d.watch(['MotorControl.ModeNow']))
