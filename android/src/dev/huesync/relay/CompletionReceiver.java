package dev.huesync.relay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Explicit callback only. A cold/stopped relay never restarts for a late reply. */
public final class CompletionReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent) {
        if (intent==null || !TaskerDispatch.COMPLETE_ACTION.equals(intent.getAction())) return;
        RelayService.acceptCompletion(intent);
    }
}
