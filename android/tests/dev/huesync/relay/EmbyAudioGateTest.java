package dev.huesync.relay;
public final class EmbyAudioGateTest {
    static int checks;
    static void check(boolean ok,String message) {checks++;if(!ok)throw new AssertionError(message);}
    public static void main(String[] args) {
        EmbyAudioGate g=new EmbyAudioGate();
        check(g.audio(true,0)==EmbyAudioGate.Action.NONE,"outside Emby ignored");
        g.foreground(true);g.audio(true,0);
        check(g.poll(999)==EmbyAudioGate.Action.NONE,"one second stability");
        check(g.poll(1000)==EmbyAudioGate.Action.PLAY,"stable playback starts once");
        check(g.poll(2000)==EmbyAudioGate.Action.NONE,"no repeated Play");
        check(g.audio(false,2000)==EmbyAudioGate.Action.PAUSE,"inactive requests debounced Pause");
        check(g.audio(true,2500)==EmbyAudioGate.Action.CANCEL_PAUSE,"resume cancels Pause immediately");
        g.foreground(false);check(g.poll(5000)==EmbyAudioGate.Action.NONE,"exit cancels pending Play");
        System.out.println("PASS: "+checks+" Emby audio checks");
    }
}
