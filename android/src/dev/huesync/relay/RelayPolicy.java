package dev.huesync.relay;

import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Collections;

/** Pure policy boundary; Android handoff lives in SceneReceiver. */
public final class RelayPolicy {
    public static final String TARGET_PACKAGE = "ch.rmy.android.http_shortcuts";
    public static final String TARGET_SERVICE = "com.joaomgcd.taskerpluginlibrary.action.IntentServiceAction";
    public static final String TASKER_ACTION = "com.twofortyfouram.locale.intent.action.FIRE_SETTING";
    public static final String BUNDLE_KEY = "com.twofortyfouram.locale.intent.extra.BUNDLE";
    private RelayPolicy() {}
    public static Map<String, String> payloadFor(String action) {
        if (action == null) return null;
        final String id;
        final String name;
        switch (action) {
            case "dev.huesync.relay.CINEMA":
                id = "b7561efb-536a-5d5a-a411-00656802bede";
                name = "Hue Relay - Cinema";
                break;
            case "dev.huesync.relay.PAUSE":
                id = "73430d53-3ed6-599b-aed3-76dc1e3c7cb3";
                name = "Hue Relay - Pause";
                break;
            case "dev.huesync.relay.READ":
                id = "bcb47c7d-75e7-5560-96cb-9440bb4239fe";
                name = "Hue Relay - Read";
                break;
            case "dev.huesync.relay.CYCLE":
                id = "8248dc33-5183-5a39-bda8-114d3cc349f2";
                name = "Hue Relay - Cycle";
                break;
            default:
                return null;
        }
        Map<String, String> payload = new LinkedHashMap<>();
        payload.put("net.dinglisch.android.tasker.extras.ACTION_RUNNER_CLASS",
            "ch.rmy.android.http_shortcuts.plugin.TriggerShortcutActionRunner");
        payload.put("net.dinglisch.android.tasker.extras.ACTION_INPUT_CLASS",
            "ch.rmy.android.http_shortcuts.plugin.Input");
        payload.put("ch.rmy.android.http_shortcuts.shortcut_id", id);
        payload.put("ch.rmy.android.http_shortcuts.shortcut_name", name);
        return Collections.unmodifiableMap(payload);
    }
}
