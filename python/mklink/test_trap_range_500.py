from pathlib import Path
import json,struct,subprocess,time,math
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

root=Path(__file__).resolve().parents[2]
folder=root/'.mklink/trap_range_500';folder.mkdir(parents=True,exist_ok=True)
d=SharedCLI()
def watch(names):return d.watch(names)
param_names=['MotorControl.current_limit','MotorControl.speed_limit','MotorControl.pos_maxspeed']
rows=watch(['MotorControl.ModeNow','FOC.Vbus_filt','Encoder.theta_mech']+param_names+['MotorControl.posRef','MotorControl.posAcc','MotorControl.posDec'])
values={r['name']:r['value'] for r in rows};addresses={r['name']:int(r['address'],16) for r in rows}
print('initial',json.dumps(values),flush=True)
assert str(values['MotorControl.ModeNow']).startswith('0 ')
assert 18<values['FOC.Vbus_filt']<40
assert abs(values['Encoder.theta_mech'])<500
summary={'initial':values,'segments':[],'commands':[]}
def put(name,v):d.write_memory(addresses[name],struct.pack('<f',v))
def command(v):
 assert -500<=v<=500
 put('MotorControl.posRef',v)
 summary['commands'].append({'posRef':v,'time':time.time()})
 print('target',v,flush=True)
def state():
 return {r['name']:r['value'] for r in watch(['MotorControl.ModeNow','MotorControl.posRef','Traj.profile_done','Traj.Y','Traj.Yd','Encoder.theta_mech','Encoder.vel_mech','MotorControl.iqRef','FOC.Vbus_filt','g_position_encoder_error','g_position_encoder_fault_delta','g_position_encoder_fault_ticks','g_position_encoder_fault_limit'])}
rs=watch(['Traj.Y','Encoder.theta_mech','Encoder.vel_mech','PID_Speed.ref_value','MotorControl.iqRef','FOC.Iq_filt'])
assert int(rs[2]['address'],16)==int(rs[1]['address'],16)+4
regions=[{'address':int(rs[i]['address'],16),'size':size} for i,size in [(0,16),(1,8),(3,4),(4,4),(5,4)]]
summary['regions']=regions
last=None
counter=0
def capture(label):
 global last,counter
 cap=d.call('capture_dump',{'regions':regions,'period':.002,'frames':2500,'duration':5.6})
 path=folder/('%03d_%s.json'%(counter,label));counter+=1;path.write_text(json.dumps(cap))
 peak_v=peak_ref=peak_iq=peak_err=0.;jumps=[]
 for row in cap['samples']:
  blobs=[bytes.fromhex(r['data_hex']) for r in row['regions']]
  y,yd,a,j=struct.unpack('<4f',blobs[0]);pos,vel=struct.unpack('<2f',blobs[1]);ref=struct.unpack('<f',blobs[2])[0];iq=struct.unpack('<f',blobs[3])[0];fb=struct.unpack('<f',blobs[4])[0]
  assert all(math.isfinite(v) for v in (y,yd,pos,vel,ref,iq,fb))
  peak_v=max(peak_v,abs(vel));peak_ref=max(peak_ref,abs(ref));peak_iq=max(peak_iq,abs(iq));peak_err=max(peak_err,abs(y-pos))
  stamp=row['timestamp_us']
  if last and 0<stamp-last[0]<10000 and abs(ref-last[1])>20:
   jumps.append({'time_us':stamp,'from':last[1],'to':ref,'dt_us':stamp-last[0]})
  last=(stamp,ref)
 st=state();rec={'file':str(path),'label':label,'samples':cap['sample_count'],'stats':cap['stats'],'peak_motor_speed':peak_v,'peak_speed_ref':peak_ref,'peak_iq_ref':peak_iq,'peak_tracking_error_rad':peak_err,'jump_candidates':jumps[:20],'state':st}
 summary['segments'].append(rec);(folder/'summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(rec),flush=True)
 assert str(st['MotorControl.ModeNow']).startswith('4 '),st
 assert st['g_position_encoder_error']==0,st
 assert peak_ref<=218.1 and peak_iq<=2.01 and peak_v<270,rec
 assert abs(st['Encoder.theta_mech'])<510 and peak_err<5,rec
 assert 18<st['FOC.Vbus_filt']<40,st
 assert not jumps,rec
 return st

def complete(target,label):
 command(target)
 for _ in range(18):
  st=capture(label)
  if st['Traj.profile_done'] and abs(st['Encoder.theta_mech']+target)<.025:return
 raise RuntimeError('move timeout')
try:
 put('MotorControl.current_limit',2.)
 put('MotorControl.speed_limit',218.)
 put('MotorControl.pos_maxspeed',20.)
 command(-values['Encoder.theta_mech'])
 d.call('write_variable',{'name':'MotorControl.ModeNow','value':4})
 for v in [10,-30,30,0]:complete(v,'small')
 for v in [100,-100,0]:complete(v,'medium')
 for v in [-500,500,-500,0]:complete(v,'full')
 for v in [500,-30,300,-500]:command(v);capture('moving_retarget')
 complete(0,'return')
 summary['passed']=True
finally:
 d.call('write_variable',{'name':'MotorControl.ModeNow','value':0})
 for name in param_names:put(name,values[name])
 pos=watch(['Encoder.theta_mech'])[0]['value'];put('MotorControl.posRef',-pos)
 summary['final']={r['name']:r['value'] for r in watch(['MotorControl.ModeNow','MotorControl.iqRef']+param_names)}
 (folder/'summary.json').write_text(json.dumps(summary,indent=2))
 print('disabled',json.dumps(summary['final']),flush=True)
