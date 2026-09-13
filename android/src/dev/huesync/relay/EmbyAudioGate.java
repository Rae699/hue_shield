package dev.huesync.relay;

/** Anonymous audio is used only while tvQuickActions says the Emby app is foreground. */
public final class EmbyAudioGate {
    public enum Action { NONE, PLAY, PAUSE, CANCEL_PAUSE }
    private boolean foreground;
    private Boolean active;
    private long playDue=-1;
    public Action foreground(boolean value) { foreground=value;active=null;playDue=-1;return Action.CANCEL_PAUSE; }
    public Action audio(boolean playing,long now) {
        if(!foreground || (active!=null && active==playing)) return Action.NONE;
        active=playing;
        if(playing) { playDue=now+1000;return Action.CANCEL_PAUSE; }
        playDue=-1;return Action.PAUSE;
    }
    public Action poll(long now) {
        if(foreground && playDue>=0 && now>=playDue) {playDue=-1;return Action.PLAY;}
        return Action.NONE;
    }
    public boolean pending() { return playDue>=0; }
}
