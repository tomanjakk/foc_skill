from mklink import connect_shared
from pathlib import Path
import time,json,math
r=(Path(__file__).resolve().parents[2] / '.mklink')
out={}
names=['g_current_pi_parameter_source','MotorControl.id_Kp','MotorControl.id_Ki','MotorControl.iq_Kp','MotorControl.iq_Ki','MotorControl.motor_phase_resistance','MotorControl.motor_d_inductance','MotorControl.motor_q_inductance','g_foc_measure_r.status','g_foc_measure_r.resistance_ohm','g_foc_measure_l.status','g_foc_measure_l.inductance_h','MotorControl.ModeNow']
with connect_shared(probe='Tomcat_mklink',axf=str(r.parent/'MDK-ARM/Objects_ResistanceDelta1/STM32g474vet6.axf'),name='PI source validation') as d:
    def snap(label):
        rows=d.watch(names);v={x['name']:x['value'] for x in rows};out[label]=v;print(label,json.dumps(v),flush=True);return v
    try:
        v=snap('startup');assert v['g_current_pi_parameter_source']==0
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':24});time.sleep(2.7)
        v=snap('resistance_only');assert v['MotorControl.ModeNow'].startswith('0 ')
        assert v['g_foc_measure_r.status'].startswith('2 ') and v['g_current_pi_parameter_source']==0
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':25});time.sleep(1.1)
        v=snap('both_identified');assert v['MotorControl.ModeNow'].startswith('0 ')
        assert v['g_current_pi_parameter_source']==1 and v['g_foc_measure_l.status']==2
        rr=v['g_foc_measure_r.resistance_ohm'];ll=v['g_foc_measure_l.inductance_h']
        assert math.isclose(v['MotorControl.id_Kp'],ll*(.5/(1.5/20000))*1.8,rel_tol=1e-5)
        assert math.isclose(v['MotorControl.id_Ki'],rr/ll*(5/14),rel_tol=1e-5)
        for n in ['MotorControl.motor_phase_resistance','MotorControl.motor_d_inductance','MotorControl.motor_q_inductance']:assert v[n]==out['startup'][n]
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        (r/'pi_source_board.json').write_text(json.dumps(out,indent=2))
        print('stop',d.watch(['MotorControl.ModeNow']))
