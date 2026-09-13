package dev.huesync.relay;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import android.hardware.display.DisplayManager;
import android.view.Display;
import android.media.AudioManager;
import android.media.AudioAttributes;
import android.media.AudioPlaybackConfiguration;
import java.util.List;
import org.json.JSONObject;

/** Serialized lighting dispatcher with bounded recovery and idle status checks. */
public final class RelayService extends Service {
    private static final String TAG="HueSyncRelay";
    private static final String PREFIX="dev.huesync.relay.";
    private static RelayService instance;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private NativeController controller;
    private SharedPreferences preferences;
    private PowerManager power;
    private long offLeaseDeadline;
    private static final long DISPATCH_LEASE = 45000;
    private long restartNotBefore;
    private long restartRequestStarted;
    private String restartRequestNonce="",restartRequestKind="";
    private String savedRequestNonce="",savedRequestKind="";
    private long savedRequestUntil=Long.MIN_VALUE;
    private long savedRequestStarted=Long.MIN_VALUE;
    private boolean initialized;
    private boolean awakeResident;
    private boolean acceptingCommands;
    private boolean embyContext;
    private long savedGeneration=Long.MIN_VALUE;
    private String savedDesired="";
    private DisplayManager displays;
    private AudioManager audio;
    private String displayMode="";
    private final EmbyAudioGate emby=new EmbyAudioGate();
    private final AudioManager.AudioPlaybackCallback audioCallback=new AudioManager.AudioPlaybackCallback() {
        @Override public void onPlaybackConfigChanged(List<AudioPlaybackConfiguration> configs) {checkAudio();}
    };
    private final DisplayManager.DisplayListener displayListener=new DisplayManager.DisplayListener() {
        @Override public void onDisplayAdded(int id) {}
        @Override public void onDisplayRemoved(int id) {}
        @Override public void onDisplayChanged(int id) {
            if(id!=Display.DEFAULT_DISPLAY) return;
            String mode=currentDisplayMode();
            if(!mode.equals(displayMode)) {
                displayMode=mode;
                if(awakeResident && power.isInteractive()) {
                    Log.i(TAG,"Display mode changed; bounded check requested");
                    controller.wake(SystemClock.elapsedRealtime(),false);persist();pump();
                }
            }
        }
    };
    private final Runnable tick=this::pump;
    private final BroadcastReceiver screenOff=new BroadcastReceiver() {
        @Override public void onReceive(Context context,Intent intent) {
            if (Intent.ACTION_SCREEN_OFF.equals(intent.getAction())) {
                long now=SystemClock.elapsedRealtime();
                controller.sleep(now); awakeResident=false;offLeaseDeadline=now+NativeController.WINDOW;
                emby.foreground(false);controller.cancelEmbyPause();
                persist(); pump();
            }
        }
    };
    @Override public void onCreate() {
        super.onCreate();
        preferences=getSharedPreferences("native-state",MODE_PRIVATE);
        controller=new NativeController(preferences.getLong("generation",0)+1);
        power=(PowerManager)getSystemService(POWER_SERVICE);
        // A previous foreground-app flag is not evidence of current playback.
        // Only a fresh Emby event can enable scene observation after process loss.
        embyContext=false;
        long now=SystemClock.elapsedRealtime();
        long until=preferences.getLong("requestUntil",0);
        long started=preferences.getLong("requestStarted",0);
        if(started<=now && until>now && until<=now+DISPATCH_LEASE) {
            restartNotBefore=until;restartRequestStarted=started;
            restartRequestNonce=preferences.getString("requestNonce","");
            restartRequestKind=preferences.getString("requestKind","");
        }
        displays=(DisplayManager)getSystemService(DISPLAY_SERVICE);
        audio=(AudioManager)getSystemService(AUDIO_SERVICE);
        NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("hue-relay","Hue lighting checks",NotificationManager.IMPORTANCE_LOW));
        startForeground(1101,new Notification.Builder(this,"hue-relay")
            .setSmallIcon(android.R.drawable.ic_menu_send).setContentTitle("Hue lighting")
            .setContentText("Lighting automation is ready").setOngoing(true).setShowWhen(false).build());
        registerReceiver(screenOff,new IntentFilter(Intent.ACTION_SCREEN_OFF));
        displayMode=currentDisplayMode();
        displays.registerDisplayListener(displayListener,handler);
        audio.registerAudioPlaybackCallback(audioCallback,handler);
        instance=this;
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        String action=intent==null ? null : intent.getAction();
        if(intent!=null && (action==null || !action.startsWith(PREFIX))) {
            if(!initialized) stopSelf();
            return initialized ? START_STICKY : START_NOT_STICKY;
        }
        String kind=action==null ? "" : action.substring(PREFIX.length());
        acceptingCommands=true;
        long now=SystemClock.elapsedRealtime();
        if(!initialized) {
            initialized=true;
            if(kind.equals("SYNC_BOOT")) clearRestartLease();
            awakeResident=power.isInteractive() && !kind.equals("SYNC_STOP");
            if(awakeResident) controller.wake(now,kind.equals("SYNC_BOOT"));
            else {controller.sleep(now);offLeaseDeadline=now+NativeController.WINDOW;}
            Log.i(TAG,"Service created; reconciling current Shield state");
        }
        if (kind.equals("SYNC_START") && power.isInteractive()) {awakeResident=true;controller.wake(now,false);restoreEmbyGate();}
        else if (kind.equals("SYNC_BOOT") && power.isInteractive()) {awakeResident=true;controller.wake(now,true);restoreEmbyGate();}
        else if (kind.equals("SYNC_STOP")) {awakeResident=false;offLeaseDeadline=now+NativeController.WINDOW;controller.sleep(now);emby.foreground(false);controller.cancelEmbyPause();}
        else if(kind.equals("EMBY_ENTER") && power.isInteractive()) {
            embyContext=true;preferences.edit().putBoolean("embyForeground",true).commit();
            awakeResident=true;applyAudio(emby.foreground(true),now);checkAudio();
        } else if(kind.equals("EMBY_EXIT")) {embyContext=false;preferences.edit().putBoolean("embyForeground",false).commit();applyAudio(emby.foreground(false),now);}
        else if (NativeController.isScene(kind) && power.isInteractive()) {
            awakeResident=true;
            if (kind.equals("CINEMA")) controller.wake(now,false);
            controller.scene(kind,now);
        }
        persist(); pump();
        return START_STICKY;
    }
    private boolean persist() {
        NativeController.Request pending=controller.pending();
        long started=pending==null ? restartRequestStarted : pending.started;
        long until=pending==null ? restartNotBefore : pending.started+DISPATCH_LEASE;
        String nonce=pending==null ? restartRequestNonce : pending.nonce;
        String kind=pending==null ? restartRequestKind : pending.kind;
        if(until==0) {started=0;nonce="";kind="";}
        if(savedGeneration==controller.generation() && savedDesired.equals(controller.desired())
            && savedRequestUntil==until && savedRequestStarted==started
            && savedRequestNonce.equals(nonce) && savedRequestKind.equals(kind)) return true;
        // Persist ownership and the possible external request before dispatching.
        boolean saved=preferences.edit().putLong("generation",controller.generation())
            .putString("desired",controller.desired()).putLong("deadline",controller.deadline())
            .putLong("requestUntil",until).putLong("requestStarted",started)
            .putString("requestNonce",nonce).putString("requestKind",kind).commit();
        if (!saved) Log.w(TAG,"Native state persistence failed");
        else {savedGeneration=controller.generation();savedDesired=controller.desired();savedRequestUntil=until;savedRequestStarted=started;savedRequestNonce=nonce;savedRequestKind=kind;}
        return saved;
    }
    private void clearRestartLease() {
        restartNotBefore=0;restartRequestStarted=0;restartRequestNonce="";restartRequestKind="";
    }
    private void pump() {
        handler.removeCallbacks(tick);
        long now=SystemClock.elapsedRealtime();
        boolean interactive=power.isInteractive();
        if(awakeResident && !interactive) {awakeResident=false;offLeaseDeadline=now+NativeController.WINDOW;controller.sleep(now);emby.foreground(false);controller.cancelEmbyPause();}
        if(!awakeResident && offLeaseDeadline>0 && now>=offLeaseDeadline && controller.pending()==null) {Log.i(TAG,"Off reconciliation window ended");stopSelf();return;}
        if(now<restartNotBefore) {
            persist();handler.postDelayed(tick,restartNotBefore-now);return;
        }
        clearRestartLease();
        applyAudio(emby.poll(now),now);
        NativeController.Request request=controller.next(now,interactive);
        boolean saved=persist();
        for(String message:controller.takeLogs()) Log.i(TAG,message);
        if(request!=null) {
            try {
                if(!saved) throw new IllegalStateException("Dispatch state was not saved");
                TaskerDispatch.start(this,request);
            }
            catch(RuntimeException error) {
                Log.e(TAG,"Tasker dispatch failed: "+error.getClass().getSimpleName());
                controller.complete(request.nonce,new NativeController.Result(request.kind,request.nonce,false,false,false),now);
                persist();
            }
        }
        if(controller.isIdle() && !emby.pending()) {
            if(!awakeResident || !interactive) stopSelf();
            else {
                long delay=controller.maintenanceDelay(now);
                if(delay>=0) handler.postDelayed(tick,Math.max(1,delay));
            }
        }
        else handler.postDelayed(tick,250);
    }
    private String currentDisplayMode() {
        Display display=displays.getDisplay(Display.DEFAULT_DISPLAY);
        if(display==null) return "none";
        Display.Mode mode=display.getMode();
        return mode.getModeId()+":"+mode.getPhysicalWidth()+":"+mode.getPhysicalHeight()+":"+mode.getRefreshRate();
    }
    private void checkAudio() {
        if(!acceptingCommands) return;
        boolean playing=false;
        for(AudioPlaybackConfiguration config:audio.getActivePlaybackConfigurations()) {
            int usage=config.getAudioAttributes().getUsage();
            if(usage==AudioAttributes.USAGE_MEDIA || usage==AudioAttributes.USAGE_GAME) {playing=true;break;}
        }
        applyAudio(emby.audio(playing,SystemClock.elapsedRealtime()),SystemClock.elapsedRealtime());
        pump();
    }
    private void restoreEmbyGate() {
        applyAudio(emby.foreground(embyContext && power.isInteractive()),SystemClock.elapsedRealtime());
        if(power.isInteractive()) checkAudio();
    }
    private void applyAudio(EmbyAudioGate.Action action,long now) {
        if(action==EmbyAudioGate.Action.CANCEL_PAUSE) controller.cancelEmbyPause();
        else if(action==EmbyAudioGate.Action.PAUSE) controller.pauseFromEmby(now);
        else if(action==EmbyAudioGate.Action.PLAY && power.isInteractive()) {
            Log.i(TAG,"Emby scoped media playback active");controller.wake(now,false);controller.scene("CINEMA",now);
        }
    }
    static void acceptCompletion(Intent intent) {
        RelayService current=instance;
        if(current!=null) current.onCompletion(intent);
    }
    private void onCompletion(Intent intent) {
        try {
            Uri uri=intent.getData();
            if(uri==null || !"huesyncrelay".equals(uri.getScheme()) || !"complete".equals(uri.getHost())) return;
            String nonce=uri.getLastPathSegment();
            NativeController.Request pending=controller.pending();
            boolean previous=pending==null && restartNotBefore>SystemClock.elapsedRealtime()
                && !restartRequestNonce.isEmpty() && restartRequestNonce.equals(nonce);
            if(!previous && (pending==null || !pending.nonce.equals(nonce))) return;
            String kind=previous ? restartRequestKind : pending.kind;
            NativeController.Result result=null;
            if(!NativeController.isScene(kind)) {
                Bundle variables=intent.getBundleExtra(TaskerDispatch.VARIABLES);
                String raw=variables==null ? null : variables.getString("%result");
                if(raw!=null && raw.length()<=2048) {
                    JSONObject obj=new JSONObject(raw);
                    if(obj.opt("ok") instanceof Boolean && obj.opt("ready") instanceof Boolean
                        && obj.opt("active") instanceof Boolean && obj.opt("video") instanceof Boolean) {
                        result=new NativeController.Result(obj.optString("kind"),obj.optString("nonce"),
                            intent.getIntExtra(TaskerDispatch.RESULT_CODE,4)==-1 && obj.getBoolean("ok"),
                            obj.getBoolean("ready"),obj.getBoolean("active"),obj.getBoolean("video"));
                    }
                }
            }
            if(previous) {
                if(!NativeController.isScene(kind) && (result==null || !kind.equals(result.kind) || !nonce.equals(result.nonce))) return;
                // A matching completion releases only external ownership, never its old decision.
                clearRestartLease();
            } else controller.complete(nonce,result,SystemClock.elapsedRealtime());
            pump();
        } catch(Exception error) {
            Log.w(TAG,"Invalid completion: "+error.getClass().getSimpleName());
        }
    }
    @Override public void onDestroy() {
        if(instance==this) instance=null;
        handler.removeCallbacksAndMessages(null);
        unregisterReceiver(screenOff);
        displays.unregisterDisplayListener(displayListener);
        audio.unregisterAudioPlaybackCallback(audioCallback);
        stopForeground(true);
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
