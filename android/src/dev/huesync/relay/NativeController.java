package dev.huesync.relay;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** Single-threaded, network-free controller. All times are elapsed realtime. */
public final class NativeController {
    public static final int LIMIT = 12;
    public static final long WINDOW = 90000;
    private static final long CALLBACK_TIMEOUT = 45000;
    private long generation;
    private String desired = "none";
    private long deadline;
    private long due;
    private String nextKind;
    private int rounds;
    private int offConfirmations;
    private long sceneRevision;
    private boolean readRecallPending;
    private long readRecallGeneration;
    private long readRecallRevision;
    private long pauseDue = -1;
    private boolean embyPause;
    private long sceneDeadline;
    private final ArrayDeque<String> scenes = new ArrayDeque<>();
    private final List<String> logs = new ArrayList<>();
    private Request pending;

    public NativeController(long generation) { this.generation = generation; }
    public long generation() { return generation; }
    public String desired() { return desired; }
    public long deadline() { return deadline; }
    public Request pending() { return pending; }
    public List<String> takeLogs() { List<String> out = new ArrayList<>(logs); logs.clear(); return out; }
    public void wake(long now, boolean boot) {
        if (desired.equals("awake") && now < deadline) { logs.add("awake event coalesced"); return; }
        generation++; desired="awake"; deadline=now+WINDOW; rounds=0; offConfirmations=0;
        nextKind="PROBE"; due=now+(boot ? 20000 : 2000);
        logs.add(boot ? "boot check scheduled" : "wake check scheduled");
    }
    public void sleep(long now) {
        if (desired.equals("asleep") && now < deadline) return;
        generation++; desired="asleep"; deadline=now+WINDOW; rounds=0; offConfirmations=0;
        sceneRevision++;readRecallPending=false;
        pauseDue=-1; scenes.clear(); nextKind="STOP"; due=now;
        logs.add("sleep recorded; Stop next");
    }
    public void scene(String kind, long now) {
        if (!isScene(kind)) return;
        sceneRevision++;readRecallPending=false;
        // A queued Read must not override a newer playback/scene decision.
        if(!kind.equals("READ")) scenes.remove("READ");
        if(kind.equals("READ")) scenes.remove("CINEMA");
        sceneDeadline=now+WINDOW;
        if (kind.equals("PAUSE")) { pauseDue=now+3000; embyPause=false; return; }
        if (kind.equals("CINEMA") || kind.equals("READ")) { pauseDue=-1; scenes.remove("PAUSE"); }
        if (!scenes.contains(kind)) scenes.add(kind);
    }
    public void pauseFromEmby(long now) {
        if(pauseDue<0 || embyPause) {sceneRevision++;readRecallPending=false;scenes.remove("READ");pauseDue=now+3000;embyPause=true;sceneDeadline=now+WINDOW;}
    }
    public void cancelEmbyPause() {if(embyPause) {pauseDue=-1;embyPause=false;}}
    public boolean isIdle() { return pending==null && nextKind==null && scenes.isEmpty() && pauseDue<0 && !readRecallPending; }
    public Request next(long now, boolean interactive) {
        if (desired.equals("awake") && !interactive) sleep(now);
        if (pending != null) {
            if (now >= pending.started+CALLBACK_TIMEOUT) {
                logs.add("callback timeout; execution uncertain");
                pending=null;readRecallPending=false;
                if (desired.equals("awake")) { nextKind=null; desired="none"; }
                else if (desired.equals("asleep")) { nextKind="STOP"; due=now; }
            } else { return null; }
        }
        if (!desired.equals("none") && now >= deadline) {
            logs.add("startup deadline reached"); desired="none"; nextKind=null;
        }
        if (now >= sceneDeadline) { scenes.clear(); pauseDue=-1; }
        if (!interactive) { scenes.clear(); pauseDue=-1;readRecallPending=false; }
        if (pauseDue>=0 && now>=pauseDue) { pauseDue=-1; if (interactive && !scenes.contains("PAUSE")) scenes.add("PAUSE"); }
        // Off reconciliation has priority over scenes or a new readiness check.
        if (desired.equals("asleep") && nextKind!=null && now>=due) return dispatchSync(now);
        if(readRecallPending) {
            readRecallPending=false;
            if(interactive && readRecallGeneration==generation && readRecallRevision==sceneRevision) return dispatch("READ_RECALL",now);
        }
        if (interactive && !scenes.isEmpty()) {
            String scene=scenes.remove();return dispatch(scene.equals("READ") ? "READ_CHECK" : scene,now);
        }
        if (desired.equals("awake") && interactive && nextKind!=null && now>=due) return dispatchSync(now);
        return null;
    }
    private Request dispatchSync(long now) {
        String kind=nextKind;
        if (kind.equals("PROBE")) {
            if (rounds>=LIMIT) { logs.add("probe limit reached"); nextKind=null; desired="none"; return null; }
            rounds++;
        }
        if (kind.equals("START") && (rounds>=LIMIT || now+15000>=deadline)) {
            logs.add("insufficient startup window for Start and verification"); nextKind=null; desired="none"; return null;
        }
        nextKind=null;
        return dispatch(kind,now);
    }
    private Request dispatch(String kind,long now) {
        pending=new Request(kind,UUID.randomUUID().toString(),generation,sceneRevision,now);
        logs.add("dispatch " + kind);
        return pending;
    }
    public void complete(String callbackNonce, Result result, long now) {
        if (pending==null || !pending.nonce.equals(callbackNonce)) return;
        if (isScene(pending.kind)) {
            pending=null;
            return;
        }
        if (result==null || !pending.nonce.equals(result.nonce) || !pending.kind.equals(result.kind)) {
            logs.add("mismatched callback; execution uncertain"); return;
        }
        Request finished=pending; pending=null;
        if(finished.kind.equals("READ_CHECK") || finished.kind.equals("READ_RECALL")) {
            if(finished.generation!=generation || finished.sceneRevision!=sceneRevision) {logs.add("stale Read decision discarded");return;}
            if(finished.kind.equals("READ_CHECK") && result.ok && result.ready) {
                readRecallPending=true;readRecallGeneration=generation;readRecallRevision=sceneRevision;
            } else {logs.add(finished.kind.equals("READ_CHECK") ? "Read skipped by guard" : "Read Recall finished");}
            return;
        }
        if (finished.generation!=generation) { logs.add("stale callback discarded"); return; }
        if (now>=deadline) { desired="none"; nextKind=null; logs.add("startup deadline reached"); return; }
        if (finished.kind.equals("START") || finished.kind.equals("STOP")) {
            nextKind="PROBE"; due=now+3000; return;
        }
        if (desired.equals("asleep")) {
            if (result.ok && !result.active) {
                offConfirmations++;
                if (offConfirmations>=2) { desired="none"; nextKind=null; logs.add("API off confirmed after compensation interval"); }
                else { nextKind="PROBE"; due=now+10000; logs.add("API off; compensation check scheduled"); }
            } else { nextKind="STOP"; due=now+(result.ok ? 0 : 5000); offConfirmations=0; }
            if (rounds>=LIMIT) { desired="none"; nextKind=null; logs.add("off probe limit reached"); }
            return;
        }
        if (!desired.equals("awake")) return;
        if (result.ok && result.ready && result.active && result.video) {
            logs.add("API video sync active");
            if (rounds>=LIMIT || now+5000>=deadline) { desired="none"; nextKind=null; logs.add("startup checks complete"); }
            else { nextKind="PROBE"; due=now+5000; }
        } else if (result.ok && result.ready && rounds<LIMIT && now+15000<deadline) {
            nextKind="START"; due=now;
        } else if (rounds<LIMIT && now+5000<deadline) {
            nextKind="PROBE"; due=now+5000; logs.add("waiting for ready video");
        } else { desired="none"; nextKind=null; logs.add("startup checks exhausted"); }
    }
    public static boolean isScene(String kind) {
        return "CINEMA".equals(kind)||"PAUSE".equals(kind)||"READ".equals(kind)||"CYCLE".equals(kind);
    }
    public static final class Request {
        public final String kind,nonce; public final long generation,sceneRevision,started;
        Request(String kind,String nonce,long generation,long sceneRevision,long started) {
            this.kind=kind; this.nonce=nonce; this.generation=generation;this.sceneRevision=sceneRevision; this.started=started;
        }
    }
    public static final class Result {
        public final String kind,nonce; public final boolean ok,ready,active,video;
        public Result(String kind,String nonce,boolean ok,boolean ready,boolean active) {
            this(kind,nonce,ok,ready,active,active);
        }
        public Result(String kind,String nonce,boolean ok,boolean ready,boolean active,boolean video) {
            this.kind=kind; this.nonce=nonce; this.ok=ok; this.ready=ready; this.active=active; this.video=video;
        }
    }
}
