"""AST-isolated regressions: never import ROS or execute the controller module."""
import ast
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[2] / 'tests/fixtures/controllers'

def extract(filename, name):
    tree = ast.parse((ROOT / filename).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    env = dict(np=np, time=time, Path=Path, json=json, STATE_TIMEOUT=.2,
               WAYPOINT_START_TOL=np.radians(3), PICK_HAND_ACTIONS=('cshape','grip','release','home'),
               STALL_PRELOAD=np.radians(1), PIP4=[4,5,7,9], xs=NS(SIDES=('left','right')))
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), env)
    return env[name], env

def state_ctl():
    c = NS(lock=threading.Lock(), armed=True, side='right', aborted=None,
           hands={'left':None,'right':None}, t_hands={'left':0.,'right':0.}, last_feedback_gap=0.,
           hand_feedback={'left':None,'right':None}, hand_status_signature={'left':None,'right':None}, log=[])
    c._abort=lambda why:setattr(c,'aborted',c.aborted or why)
    return c

def message(fault=0, invalid=False):
    def hand(): return [NS(name=f'joint_{i}', position=0., state=0, faultcode=0) for i in range(10)]
    m=NS(left_hand_type=NS(value=1),right_hand_type=NS(value=1),left_hands=hand(),right_hands=hand())
    m.right_hands[1].faultcode=fault
    if invalid: m.right_hands[1].position=float('nan')
    return m

class Regressions(unittest.TestCase):
    def test_candidate_fault_does_not_refresh(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();f(c,message(4))
        self.assertIn('fault codes',c.aborted);self.assertEqual(c.t_hands['right'],0)

    def test_fault_recorded_before_rejection(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();m=message(4)
        f(c,m)
        self.assertEqual(c.hand_feedback['right']['joints'][1]['faultcode'],4)
        self.assertEqual(c.log[-1]['feedback']['joints'][1]['state'],0)
        count=len(c.log);f(c,m);self.assertEqual(len(c.log),count)
        f(c,message())
        self.assertIsNotNone(c.aborted)  # No automatic recovery after a zero-fault message.
        self.assertEqual(c.log[-1]['feedback']['joints'][1]['faultcode'],0)

    def test_fault_in_held_hand_also_rejected(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();c.side='left'
        f(c,message(4));self.assertIn('right hand fault',c.aborted)

    def test_missing_fault_field_rejected(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();m=message()
        del m.right_hands[1].faultcode
        f(c,m);self.assertIn('missing state/faultcode',c.aborted)
        self.assertEqual(c.t_hands['right'],0)

    def test_raw_state_preserved_without_guessed_meaning(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();m=message()
        m.right_hands[1].state=7;f(c,m)
        self.assertEqual(c.hand_feedback['right']['joints'][1]['state'],7)
        self.assertIsNone(c.aborted)

    def test_candidate_invalid_position_stops(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();f(c,message(invalid=True))
        self.assertIn('nonfinite',c.aborted)

    def test_valid_state_still_accepted(self):
        f,_=extract('executor_candidate.py','_on_hand');c=state_ctl();f(c,message())
        self.assertIsNone(c.aborted);self.assertGreater(c.t_hands['right'],0)

    def test_nan_start_rejected(self):
        plan=dict(side='right',stand=[float('nan')]*7,segments=[dict(name='back',path=[[0.]*7],hand=None)])
        c=NS(arm_lo=np.full(7,-2.),arm_hi=np.full(7,2.))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json';p.write_text(json.dumps(plan))
            old,_=extract('box_executor.py','load_pick_plan')
            new,_=extract('executor_candidate.py','load_pick_plan')
            self.assertIsNone(old(p,c,np.zeros(7))[1])
            self.assertIn('finite',new(p,c,np.zeros(7))[1])

    def test_missing_contact_prevents_next_step(self):
        for filename,expected in [('box_executor.py',2),('executor_candidate.py',1)]:
            f,e=extract(filename,'run_steps');calls=[]
            c=NS(aborted=None,stalled={},hand_rate=0.,stall_preload=0.,measured=lambda:(None,np.zeros(10)))
            c._abort=lambda why:setattr(c,'aborted',why)
            e['run_profile']=lambda *args,**kwargs:calls.append(1)
            e['warn_unreached']=lambda *args:None
            f(c,[('grip',np.zeros(10),1.,[],{'contact':[4]}),('next',np.zeros(10),1.,[])],.1)
            self.assertEqual(len(calls),expected)

    def test_candidate_cannot_arm(self):
        tree=ast.parse((ROOT/'executor_candidate.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        guard=next(i for i,n in enumerate(main.body) if isinstance(n,ast.If) and
                   isinstance(n.test,ast.Attribute) and n.test.attr=='armed' and
                   'OFFLINE REVIEW CANDIDATE' in ast.unparse(n))
        init=next(i for i,n in enumerate(main.body) if ast.unparse(n)=='rclpy.init()')
        self.assertLess(guard,init)

if __name__=='__main__': unittest.main()
