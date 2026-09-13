package dev.huesync.relay;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import java.util.Map;

final class TaskerDispatch {
    static final String COMPLETION="net.dinglisch.android.tasker.extras.COMPLETION_INTENT";
    static final String VARIABLES="net.dinglisch.android.tasker.extras.VARIABLES";
    static final String RESULT_CODE="net.dinglisch.android.tasker.extras.RESULT_CODE";
    static final String COMPLETE_ACTION="dev.huesync.relay.COMPLETE";
    private TaskerDispatch() {}
    static void start(Context context,NativeController.Request request) {
        Bundle input=new Bundle();
        Map<String,String> scene=RelayPolicy.payloadFor("dev.huesync.relay."+request.kind);
        if (scene!=null) {
            for (Map.Entry<String,String> entry:scene.entrySet()) input.putString(entry.getKey(),entry.getValue());
        } else {
            String id=NativeShortcutIds.id(request.kind);
            if (id==null) throw new IllegalArgumentException("unsupported helper");
            input.putString("net.dinglisch.android.tasker.extras.ACTION_RUNNER_CLASS","ch.rmy.android.http_shortcuts.plugin.TriggerShortcutActionRunner");
            input.putString("net.dinglisch.android.tasker.extras.ACTION_INPUT_CLASS","ch.rmy.android.http_shortcuts.plugin.Input");
            input.putString("ch.rmy.android.http_shortcuts.shortcut_id",id);
            input.putString("ch.rmy.android.http_shortcuts.shortcut_name",NativeShortcutIds.name(request.kind));
            input.putString("hsr_request_nonce",request.nonce);
        }
        Intent completion=new Intent(COMPLETE_ACTION)
            .setComponent(new ComponentName(context,CompletionReceiver.class))
            .setData(Uri.parse("huesyncrelay://complete/"+request.nonce));
        Intent fire=new Intent(RelayPolicy.TASKER_ACTION)
            .setComponent(new ComponentName(RelayPolicy.TARGET_PACKAGE,RelayPolicy.TARGET_SERVICE))
            .putExtra(RelayPolicy.BUNDLE_KEY,input)
            .putExtra(COMPLETION,completion.toUri(Intent.URI_INTENT_SCHEME));
        // No CAN_BIND flag: the target Tasker service must promote itself.
        context.startForegroundService(fire);
    }
}
