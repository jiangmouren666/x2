"""Source fragments for AST-only offline tests; not an importable controller.
The main fragment preserves only the armed guard and following init witness.
No hardware runtime, imports, connection configuration, or deployment entry point.
"""

(STALL_ERR, STALL_STILL, STALL_S, STALL_PRELOAD) = (np.radians(3), np.radians(0.5), 0.5, np.radians(1))

def set_mode(node, desc, timeout=3.0, attempts=8):
    """SetMcAction with the official example's retries. Returns (code, message); code 0 = accepted, None = no reply."""
    from aimdk_msgs.srv import SetMcAction
    from aimdk_msgs.msg import McActionCommand
    cli = node.create_client(SetMcAction, '/aimdk_5Fmsgs/srv/SetMcAction')
    if not cli.wait_for_service(timeout_sec=timeout):
        return (None, 'no SetMcAction service')
    req = SetMcAction.Request()
    req.source = INPUT_SOURCE
    req.command = McActionCommand(action_desc=desc)
    for _ in range(attempts):
        req.header.stamp = node.get_clock().now().to_msg()
        fut = cli.call_async(req)
        t0 = time.time()
        while not fut.done() and time.time() - t0 < 0.25:
            time.sleep(0.01)
        if fut.done() and fut.result() is not None:
            r = fut.result().response
            return (int(r.header.code), r.message)
    return (None, 'no reply')

def recover_to_stand(node, ctl):
    try:
        (ok, detail) = switch_mode(node, ctl, STAND_MODE)
    except (Exception, KeyboardInterrupt) as exc:
        (ok, detail) = (False, str(exc))
    print(f'switch back to {STAND_MODE}: {detail}', flush=True)
    if not ok:
        await_operator_takeover(node, ctl)
    return ok

def _on_hand(self, m):
    with self.lock:
        for side in xs.SIDES:
            kind = getattr(getattr(m, side + '_hand_type', None), 'value', None)
            if kind != 1:
                if self.armed or side == self.side:
                    self._abort(f'{side} hand type {kind!r} is not NIMBLE_HANDS')
                continue
            states = getattr(m, side + '_hands')
            if len(states) != 10:
                continue
            q = np.array([h.position for h in states])
            if np.isfinite(q).all():
                self.hands[side] = q
                now = time.monotonic()
                if now - self.t_hands[side] > STATE_TIMEOUT:
                    self.last_feedback_gap = now
                self.t_hands[side] = now

def _check_stall(self, hand_meas, tgt_hand):
    """Freeze driven hand joints that stopped short of their command: the command is past the measurement by
        STALL_ERR in the direction of the target, continuously for STALL_S, while the measurement moved less than
        STALL_STILL. A joint already blocked short of the MC's start command (the standing thumb on the fingers) is
        left alone while it is targeted back at that command; while it is driven away, the command first has to
        catch up with the measurement, which is not a stall."""
    t = time.monotonic()
    idx = np.arange(20)[self.h]
    err = self.cmd_hand[idx] - hand_meas
    toward = np.sign(tgt_hand - hand_meas) == np.sign(err)
    watched = ~(self.preloaded & (np.abs(tgt_hand - self.start_hand10) < 1e-09))
    cond = (np.abs(err) > STALL_ERR) & toward & watched
    for j in range(10):
        if not cond[j] or j in self.stalled:
            self.stall_since[j] = np.nan
            continue
        if np.isnan(self.stall_since[j]) or abs(hand_meas[j] - self.stall_ref[j]) >= STALL_STILL:
            (self.stall_since[j], self.stall_ref[j]) = (t, hand_meas[j])
            continue
        if t - self.stall_since[j] < STALL_S:
            continue
        hold = float(np.clip(hand_meas[j] + np.sign(err[j]) * self.stall_preload, self.hand_lo[j], self.hand_hi[j]))
        was = self.cmd_hand[idx[j]]
        with self.lock:
            self.tgt_hand[j] = hold
        self.cmd_hand[idx[j]] = hold
        self.stalled[j] = hold
        print(f'  STALLED: {self.side} hand joint {j} stopped at {hand_meas[j]:.3f}, command was {was:.3f}; holding {hold:.3f}', flush=True)

def step(self):
    """One 50 Hz cycle: rate-limit the driven arm and hand, hold everything else, publish one command.
        Returns the driven side's commanded (arm 7, hand 10)."""
    with self.lock:
        (arm, head) = (self.arm, self.head)
        stale = self._stale_reason()
        held_hand = self.hands[xs.other(self.side)]
        hand_meas = None if self.hands[self.side] is None else self.hands[self.side].copy()
        (tgt_arm, tgt_hand) = (self.tgt_arm7.copy(), self.tgt_hand.copy())
    now = time.time()
    handing_back = self.phase in (f'requesting:{STAND_MODE}', f'confirmed:{STAND_MODE}')
    pub_arm = self.cmd_arm + self.sag
    if stale:
        self._abort(stale)
    elif handing_back:
        pass
    elif np.abs(pub_arm - arm).max() > MAX_TRACK_ERR:
        j = int(np.abs(pub_arm - arm).argmax())
        self._abort(f'tracking error {np.degrees(abs(pub_arm[j] - arm[j])):.1f} deg on {ARM14[j]}')
    elif self.armed and np.abs(self.held_hand0 - held_hand).max() > MAX_HELD_HAND_DRIFT:
        self._abort(f'held {xs.other(self.side)} hand drifted {np.degrees(np.abs(self.held_hand0 - held_hand).max()):.1f} deg')
    elif self.armed and np.abs(self.cmd_head - head).max() > MAX_HEAD_DRIFT:
        self._abort(f'held head drifted {np.degrees(np.abs(self.cmd_head - head).max()):.1f} deg')
    if self.aborted is None:
        goal_arm = self.cmd_arm.copy()
        goal_arm[self.a] = np.clip(tgt_arm, self.arm_lo, self.arm_hi)
        goal_hand = self.cmd_hand.copy()
        goal_hand[self.h] = np.clip(tgt_hand, self.hand_lo, self.hand_hi)
        self.cmd_arm += np.clip(goal_arm - self.cmd_arm, -ARM_RATE / HZ, ARM_RATE / HZ)
        self.cmd_hand += np.clip(goal_hand - self.cmd_hand, -self.hand_rate / HZ, self.hand_rate / HZ)
        if self.armed and hand_meas is not None and (self.phase == f'confirmed:{MODE_NAME}'):
            self._check_stall(hand_meas, tgt_hand)
        if self.sag_comp and self.phase == f'confirmed:{MODE_NAME}' and (np.abs(goal_arm - self.cmd_arm).max() < 1e-09):
            err = self.cmd_arm[self.a] - arm[self.a]
            gain = np.where(np.abs(err) < SAG_MAX_ERR, SAG_GAIN / HZ, 0.0)
            self.sag[self.a] = np.clip(self.sag[self.a] + gain * err, -SAG_MAX, SAG_MAX)
    lo = np.concatenate([xs.ARM_LO[s] for s in xs.SIDES])
    hi = np.concatenate([xs.ARM_HI[s] for s in xs.SIDES])
    pub_arm = np.clip(self.cmd_arm + self.sag, lo, hi)
    if self.pub is not None and np.abs(pub_arm).max() < 0.001:
        self._abort('refusing to publish an all-zero arm_pos')
    elif self.pub is not None:
        msg = self.Msg()
        stamp = self.node.get_clock().now().nanoseconds
        (msg.header.stamp.sec, msg.header.stamp.nanosec) = (stamp // 1000000000, stamp % 1000000000)
        msg.header.frame_id = 'mc_upper_body'
        msg.header.sequence = self.seq
        self.seq += 1
        msg.source = INPUT_SOURCE
        msg.hand_sub_mode = self.Msg.HAND_DEXTEROUS_JOINT
        msg.head_pos = self.cmd_head.tolist()
        msg.arm_pos = pub_arm.tolist()
        msg.hand_pos = self.cmd_hand.tolist()
        self.pub.publish(msg)
    if self.log is not None:
        self.log.append(dict(t=now, monotonic=time.monotonic(), phase=self.phase, side=self.side, cmd_arm=self.cmd_arm.tolist(), cmd_hand=self.cmd_hand.tolist(), pub_arm=pub_arm.tolist(), sag=self.sag.tolist(), meas_arm=None if arm is None else arm.tolist(), meas_hand=None if hand_meas is None else hand_meas.tolist(), aborted=self.aborted))
    return (self.cmd_arm[self.a].copy(), self.cmd_hand[self.h].copy())
