package dev.huesync.relay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/** Receives four fixed scene actions; never starts an Activity or accesses Hue. */
public final class SceneReceiver extends BroadcastReceiver {
    private static final String TAG = "HueSyncRelay";

    @Override
    public void onReceive(Context context, Intent incoming) {
        String action = incoming == null ? null : incoming.getAction();
        boolean lifecycle = "dev.huesync.relay.SYNC_START".equals(action)
            || "dev.huesync.relay.SYNC_BOOT".equals(action)
            || "dev.huesync.relay.SYNC_STOP".equals(action)
            || "dev.huesync.relay.EMBY_ENTER".equals(action)
            || "dev.huesync.relay.EMBY_EXIT".equals(action);
        if (!lifecycle && RelayPolicy.payloadFor(action) == null) {
            Log.w(TAG, "Ignored an unsupported action");
            return;
        }
        try {
            // No incoming extras, IDs, components, URLs or credentials are forwarded.
            context.startForegroundService(new Intent(context, RelayService.class).setAction(action));
        } catch (RuntimeException failure) {
            // No Activity fallback: opening one would recreate the foreground loop.
            Log.e(TAG, "Scene dispatch failed: " + failure.getClass().getSimpleName());
        }
    }
}
