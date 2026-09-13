package dev.huesync.relay;

public final class NativeControllerTest {
    private static int checks;
    private static void check(boolean value, String message) {
        checks++; if (!value) throw new AssertionError(message);
    }
    private static NativeController.Result result(NativeController.Request r, boolean ready, boolean active) {
        return new NativeController.Result(r.kind, r.nonce, true, ready, active);
    }
    private static NativeController idleAwake() {
        NativeController c = new NativeController(0);
        c.wake(0, false);
        c.next(90000, true);
        return c;
    }
    private static NativeController.Request maintenance(NativeController c) {
        check(c.next(149999, true) == null, "maintenance waits a minute after recovery");
        NativeController.Request p = c.next(150000, true);
        check(p != null && p.kind.equals("PROBE"), "idle awake controller performs maintenance Probe");
        return p;
    }
    private static void maintenanceChecks() {
        NativeController c = new NativeController(0);
        check(c.maintenanceDelay(0)==-1, "new controller has maintenance disabled");
        c.wake(0,false);
        check(c.maintenanceDelay(0)>=0, "wake enables maintenance scheduling");
        c.next(90000,true);
        check(c.maintenanceDelay(90000)==60000 && c.maintenanceDelay(150001)==0, "maintenance delay counts down and clamps at zero");
        NativeController.Request p = maintenance(c);
        c.complete(p.nonce, result(p, true, true), 150001);
        check(c.isIdle(), "healthy maintenance ends immediately");
        check(c.next(155001, true) == null && c.next(210000, true) == null, "healthy maintenance does not create a recovery window");
        check(c.next(210001, true).kind.equals("PROBE"), "next healthy check waits sixty seconds from completion");

        c = idleAwake(); p = maintenance(c);
        c.complete(p.nonce, new NativeController.Result(p.kind,p.nonce,false,false,false,false),150001);
        check(c.isIdle() && c.next(210000,true)==null, "failed maintenance backs off without recovery");
        check(c.next(210001,true).kind.equals("PROBE"), "failed maintenance retries next minute");

        c = idleAwake(); p = maintenance(c);
        c.complete(p.nonce,result(p,false,false),150001);
        check(c.isIdle() && c.next(155001,true)==null, "missing video maintenance waits instead of starting");
        check(c.next(210001,true).kind.equals("PROBE"), "missing video checked next minute");

        for (boolean active : new boolean[]{false,true}) {
            c = idleAwake(); p = maintenance(c);
            c.complete(p.nonce,new NativeController.Result(p.kind,p.nonce,true,true,active,false),150001);
            check(c.deadline()==240001, "maintenance escalation has bounded ninety second recovery");
            check(c.next(150001,true).kind.equals("START"), "inactive or wrong-mode video escalates to Start");
        }

        c = idleAwake(); p = maintenance(c);
        check(c.next(194999,true)==null, "maintenance preserves forty-five second callback timeout");
        check(c.next(195000,true)==null && c.isIdle(), "maintenance timeout ends without another request");
        c.complete(p.nonce,result(p,true,false),195001);
        check(c.next(254999,true)==null, "late timed-out result cannot authorize Start");
        check(c.next(255000,true).kind.equals("PROBE"), "timeout backs off one minute");

        c = idleAwake(); p=maintenance(c);
        c.complete(p.nonce,result(p,true,false),150001);
        p=c.next(150001,true); c.complete(p.nonce,result(p,true,true),150002);
        long recoveryTime=153002;
        for (int i=1; i<NativeController.LIMIT; i++) {
            p=c.next(recoveryTime,true);
            check(p!=null && p.kind.equals("PROBE"), "maintenance recovery probe " + i);
            c.complete(p.nonce,result(p,true,true),recoveryTime);
            recoveryTime+=5000;
        }
        check(c.isIdle() && c.maintenanceDelay(recoveryTime-5000)==60000, "maintenance escalation completes after twelve total probes and defers next check");
        check(c.next(recoveryTime,true)==null, "finished maintenance recovery stays quiet");

        c = idleAwake(); c.wake(149000,false);
        long deadline = c.deadline(); c.wake(150000,false);
        check(c.deadline()==deadline && c.next(150000,true)==null, "maintenance and repeated wake do not extend existing recovery");
        check(c.next(151000,true).kind.equals("PROBE"), "existing recovery controls probe timing");

        c = idleAwake(); c.scene("READ",149999); p=c.next(149999,true);
        check(c.next(150000,true)==null, "pending scene blocks maintenance");
        c.complete(p.nonce,result(p,true,false),150001);
        p=c.next(150001,true); check(p.kind.equals("READ_RECALL"), "Read Recall stays ahead of maintenance");
        c.complete(p.nonce,result(p,false,false),150002);
        check(c.next(150002,true).kind.equals("PROBE"), "maintenance resumes after full Read sequence");

        c = idleAwake(); c.scene("PAUSE",149999);
        check(c.next(150000,true)==null, "delayed scene also blocks maintenance");

        c = idleAwake(); p=maintenance(c); c.sleep(150001);
        check(c.maintenanceDelay(150001)==-1, "sleep disables scheduled maintenance immediately");
        check(c.next(150002,false)==null, "sleep keeps maintenance request serialized");
        c.complete(p.nonce,result(p,true,false),150003);
        check(c.next(150003,false).kind.equals("STOP"), "sleep discards maintenance Start decision and compensates Stop");

        c = idleAwake();
        p=c.next(150000,false);
        check(p!=null && p.kind.equals("STOP"), "interactive false reconciles sleep even without active window");
    }
    public static void main(String[] args) {
        NativeController newer = idleAwake();
        NativeController.Request expired = maintenance(newer);
        newer.wake(194000,false);
        long freshDeadline = newer.deadline();
        check(newer.next(195000,true)==null, "old maintenance timeout preserves fresh wake delay");
        check(newer.desired().equals("awake") && newer.deadline()==freshDeadline, "old maintenance timeout preserves fresh wake generation");
        check(newer.next(196000,true).kind.equals("PROBE"), "fresh wake probes after old maintenance expires");
        newer = idleAwake(); expired=maintenance(newer); newer.sleep(194000);
        check(newer.next(195000,false).kind.equals("STOP") && newer.deadline()==284000, "old timeout preserves fresh sleep decision and deadline");
        maintenanceChecks();
        NativeController c = new NativeController(0);
        c.wake(0, false);
        check(c.next(1999, true) == null, "wake waits 2 seconds");
        NativeController.Request p = c.next(2000, true);
        check(p != null && p.kind.equals("PROBE"), "wake probes");
        c.complete(p.nonce, result(p, true, false), 2001);
        NativeController.Request on = c.next(2001, true);
        check(on.kind.equals("START"), "ready starts");
        c.sleep(2002);
        check(c.next(2003, false) == null, "running Start remains serialized");
        c.complete(on.nonce, result(on, true, true), 2004);
        NativeController.Request off = c.next(2004, false);
        check(off.kind.equals("STOP"), "late Start followed by Stop");
        c.complete(off.nonce, result(off, false, false), 2005);
        p = c.next(5005, false);
        check(p.kind.equals("PROBE"), "verify Stop");
        c.complete(p.nonce, result(p, false, false), 5006);
        check(c.next(15005, false) == null, "off compensation waits 10 seconds");
        p = c.next(15006, false);
        c.complete(p.nonce, result(p, false, false), 15007);
        check(c.isIdle(), "off confirmation completes");

        c = new NativeController(0); c.wake(0, true);
        check(c.next(19999, true) == null, "boot waits 20 seconds");
        p = c.next(20000, true); c.complete(p.nonce, result(p, true, true), 20001);
        p = c.next(25001, true); c.complete(p.nonce, result(p, false, false), 25002);
        p = c.next(30002, true); c.complete(p.nonce, result(p, true, false), 30003);
        check(c.next(30003, true).kind.equals("START"), "active-gap-return recovers");

        c = new NativeController(0); c.wake(0, false);
        p = c.next(2000, true); c.complete(p.nonce, result(p, true, false), 2001);
        check(c.next(2002, false).kind.equals("STOP"), "interactive gate prevents Start");

        c = new NativeController(0); c.wake(0, false);
        p = c.next(2000, true); c.sleep(2001); c.wake(2002, false);
        c.complete(p.nonce, result(p, true, false), 2003);
        check(c.next(2003, true) == null, "old GET cannot bypass new wake delay");
        check(c.next(4002, true).kind.equals("PROBE"), "new generation begins fresh");

        c = new NativeController(0); c.wake(0, false); long time = 2000;
        for (int i=0; i<12; i++) {
            p = c.next(time, true); check(p != null && p.kind.equals("PROBE"), "bounded active probe " + i);
            c.complete(p.nonce, result(p, true, true), time); time += 5000;
        }
        check(c.isIdle() && c.next(time, true) == null, "12 rounds end watch");
        c = new NativeController(0); c.wake(0, false);
        check(c.next(90000, true) == null && c.isIdle(), "90 seconds ends watch");

        c = new NativeController(0); c.scene("PAUSE", 0); c.scene("CINEMA", 1000);
        p = c.next(1000, true); check(p.kind.equals("CINEMA"), "Cinema immediate");
        c.complete(p.nonce, null, 1001);
        check(c.next(3000, true) == null, "Cinema cancels delayed Pause");
        c.scene("PAUSE", 4000); check(c.next(6999, true) == null, "Pause waits 3 seconds");
        check(c.next(7000, true).kind.equals("PAUSE"), "Pause due");

        c = new NativeController(0); c.scene("PAUSE",0);c.scene("READ",1000);
        p=c.next(1000,true);c.complete(p.nonce,result(p,false,false),1001);
        check(c.next(17000,true)==null,"Home Read cancels older delayed Pause");

        c = new NativeController(0);c.pauseFromEmby(0);c.cancelEmbyPause();
        check(c.next(3000,true)==null,"Emby exit cancels fallback Pause");
        c.scene("PAUSE",4000);c.cancelEmbyPause();
        check(c.next(7000,true).kind.equals("PAUSE"),"Emby exit preserves ordinary Pause");

        c = new NativeController(0); c.scene("READ", 0);
        p = c.next(0, true);check(p.kind.equals("READ_CHECK"),"Read uses top-level sensor check");
        c.complete(p.nonce,result(p,true,false),1);
        p=c.next(1,true);check(p.kind.equals("READ_RECALL"),"allowed Read recalls immediately without quiet delay");
        c.complete(p.nonce,result(p,false,false),2);check(c.isIdle(),"Read finishes after recall callback");

        c=new NativeController(0);c.scene("READ",0);p=c.next(0,true);
        c.scene("CINEMA",1);c.complete(p.nonce,result(p,true,false),2);
        check(c.next(2,true).kind.equals("CINEMA"),"Cinema cancels old Read decision");
        c=new NativeController(0);c.scene("READ",0);p=c.next(0,true);c.complete(p.nonce,result(p,true,false),1);
        c.sleep(2);check(c.next(2,false).kind.equals("STOP"),"Sleep cancels pending Read Recall");
        c=new NativeController(0);c.scene("READ",0);p=c.next(0,true);c.complete(p.nonce,result(p,true,false),1);
        check(c.next(2,false)==null,"interactive gate blocks Read Recall");
        check(c.next(3,true)==null,"blocked Read Recall does not return after wake");

        c=new NativeController(0);c.sleep(0);off=c.next(89999,false);
        c.wake(90000,false);check(c.next(92000,true)==null,"in-flight old Stop retained across deadline/wake");
        c.complete(off.nonce,result(off,false,false),92001);
        check(c.next(92001,true).kind.equals("PROBE"),"new wake starts after old Stop settles");

        c = new NativeController(0); c.wake(0, false); p=c.next(2000,true);
        c.complete(p.nonce, new NativeController.Result("PROBE","wrong",true,true,false),2001);
        check(c.next(2002,true)==null, "wrong result nonce cannot start");
        check(c.next(47000,true)==null && c.isIdle(), "uncertain execution ends awake recovery safely");
        System.out.println("PASS: " + checks + " native controller checks");
    }
}
