from mklink import connect_shared
import json, sys, struct
from pathlib import Path
root=(Path(__file__).resolve().parents[2] / '.mklink')
with connect_shared(probe='Tomcat_mklink', axf=str(root.parent/'MDK-ARM/Objects_Deadzone/STM32g474vet6.axf'),name='Deadzone comparison') as d:
    rows=d.watch(['MotorControl.ModeNow','MotorControl.idRef','MotorControl.iqRef','FOC.Id','FOC.Iq','FOC.Id_filt','FOC.Iq_filt','FOC.Vbus_filt'])
    assert rows[0]['value'].startswith('0 '), rows
    assert rows[1]['value']==0 and rows[2]['value']==0
    regions=[{'address':int(rows[3]['address'],16),'size':16}]
    try:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':2})
        if len(sys.argv)>2:
            d.write_memory(int(rows[1]['address'],16),struct.pack('<f',float(sys.argv[2])))
        result=d.call('capture_dump',{'regions':regions,'period':0.0002,'frames':2000,'duration':1.0})
        (root/(sys.argv[1]+'.json')).write_text(json.dumps(result),encoding='utf-8')
        print('captured',list(result),str(result)[:350])
    finally:
        d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
        d.write_memory(int(rows[1]['address'],16),struct.pack('<f',0.0))
        print('stopped',d.watch(['MotorControl.ModeNow','MotorControl.idRef']))
