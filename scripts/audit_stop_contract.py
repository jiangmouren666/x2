"""Offline characterization of known candidate limitations, not motion clearance.

Extracts three functions with AST. All publishers, services and hardware state
are in-memory fakes. Never imports the controller or ROS.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace as NS, ModuleType
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tests/fixtures/controllers/executor_candidate.py'
EXPECTED = '6f3bb55431d72efec25f183e3908a6f34be643f21e7d48124540e23045ad85fd'


def extract(name):
    tree = ast.parse(SOURCE.read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    env = dict(np=np, time=time, STAND_MODE='STAND_DEFAULT', HZ=50,
               MODE_NAME='UPPERBODY_REMOTE_SPLIT', INPUT_SOURCE='sdk_cup',
               MAX_TRACK_ERR=np.radians(15), MAX_HELD_HAND_DRIFT=np.radians(25),
               MAX_HEAD_DRIFT=np.radians(10),
               xs=NS(SIDES=('left','right'), other=lambda s:'left' if s=='right' else 'right',
                     ARM_LO={s:np.full(7,-3.) for s in ('left','right')},
                     ARM_HI={s:np.full(7,3.) for s in ('left','right')}))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), 'exec'), env)
    return env[name], env


def main():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED, 'Candidate changed; review audit first'
    result = dict(scope='Offline characterization only; checks reproduce gaps, not safe-stop certification',
                  candidate_sha256=EXPECTED, robot_access=False)
    sent = []
    class FakeMsg:
        HAND_DEXTEROUS_JOINT = 2
        def __init__(self):
            self.header = NS(stamp=NS(sec=0,nanosec=0),frame_id='',sequence=0)
    ctl = NS(lock=threading.Lock(), arm=np.full(14,.2), head=np.zeros(2),
             hands={s:np.full(10,.1) for s in ('left','right')}, side='right',
             tgt_arm7=np.full(7,.3),tgt_hand=np.full(10,.2),hand_feedback={},
             cmd_arm=np.full(14,.2),cmd_hand=np.full(20,.1),cmd_head=np.zeros(2),
             sag=np.zeros(14),phase='confirmed:UPPERBODY_REMOTE_SPLIT',
             armed=True,held_hand0=np.full(10,.1),aborted='right hand fault codes: [(1, 4)]',
             pub=NS(publish=lambda m:sent.append(m)),Msg=FakeMsg,seq=0,log=None,
             node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=1))),
             a=slice(7,14),h=slice(10,20),_stale_reason=lambda:None)
    ctl._abort=lambda why:setattr(ctl,'aborted',ctl.aborted or why)
    step,_=extract('step')
    step(ctl)
    assert len(sent)==1 and sent[0].hand_pos == [.1]*20
    result['after_abort'] = dict(publishes=True,hand_targets=len(sent[0].hand_pos),
                                targets_unchanged=True,hardware_isolation=False)

    recover,env=extract('recover_to_stand')
    requested=[]
    env['switch_mode']=lambda node,c,desc:(requested.append(desc) or (True,'FAKE'))
    env['await_operator_takeover']=lambda *a:None
    recover(None,ctl)
    assert requested==['STAND_DEFAULT']
    result['recover_helper'] = dict(requests_stand_when_aborted=True,
                                   internal_pose_freshness_or_fault_gate=False,
                                   limitation='Caller context can differ; this isolates the helper only')

    set_mode,_=extract('set_mode')
    srv,msg=ModuleType('aimdk_msgs.srv'),ModuleType('aimdk_msgs.msg')
    srv.SetMcAction=NS(Request=lambda:NS(header=NS(stamp=None)))
    msg.McActionCommand=lambda **kw:NS(**kw)
    reply=NS(response=NS(header=NS(code=0),message='FAKE rejected',status=NS(value=2)))
    cli=NS(wait_for_service=lambda **kw:True,
           call_async=lambda req:NS(done=lambda:True,result=lambda:reply))
    node=NS(create_client=lambda *a:cli,
            get_clock=lambda:NS(now=lambda:NS(to_msg=lambda:None)))
    with patch.dict(sys.modules,{'aimdk_msgs.srv':srv,'aimdk_msgs.msg':msg}):
        code,_=set_mode(node,'UPPERBODY_REMOTE_SPLIT')
    assert code==0
    result['mode_reply'] = dict(header_code=0,fake_status=2,returned_code=code,
                              status_checked=False,
                              limitation='switch_mode additionally queries observed mode; not tested here')
    print('STOP_AUDIT='+json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
