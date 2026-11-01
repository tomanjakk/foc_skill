from mklink import connect_shared
import json,time
from pathlib import Path
r=(Path(__file__).resolve().parents[2] / '.mklink')
with connect_shared(probe='Tomcat_mklink',axf=str(r.parent/'MDK-ARM/Objects_Inductance3/STM32g474vet6.axf'),name='Inductance diagnosis') as d:
    print(d.watch(['MotorControl.ModeNow','FOC.Vbus_filt']))
    try:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':25})
        time.sleep(1.2)
        names=['status','reason','phase','valid_samples','timing_detail','direction','round','inductance_uh','result_valid','current_before_a','current_after_a','current_delta_a','voltage_time_vs','rotor_error_deg','rotor_speed_rad_s','bus_voltage_v']
        rows=d.watch(['g_foc_measure_l.'+n for n in names]); print(json.dumps(rows)); (r/'inductance_latest.json').write_text(json.dumps(rows),encoding='utf-8')
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        print('stop',d.watch(['MotorControl.ModeNow']))
