package dev.huesync.relay;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class RelayPolicyTest {
    private static int checks;
    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        String[][] expected = {
            {"CINEMA", "b7561efb-536a-5d5a-a411-00656802bede", "Hue Relay - Cinema"},
            {"PAUSE", "73430d53-3ed6-599b-aed3-76dc1e3c7cb3", "Hue Relay - Pause"},
            {"READ", "bcb47c7d-75e7-5560-96cb-9440bb4239fe", "Hue Relay - Read"},
            {"CYCLE", "8248dc33-5183-5a39-bda8-114d3cc349f2", "Hue Relay - Cycle"}
        };
        Set<String> expectedKeys = new HashSet<>(Arrays.asList(
            "net.dinglisch.android.tasker.extras.ACTION_RUNNER_CLASS",
            "net.dinglisch.android.tasker.extras.ACTION_INPUT_CLASS",
            "ch.rmy.android.http_shortcuts.shortcut_id",
            "ch.rmy.android.http_shortcuts.shortcut_name"
        ));
        for (String[] item : expected) {
            Map<String, String> payload = RelayPolicy.payloadFor("dev.huesync.relay." + item[0]);
            check(payload != null, "whitelisted " + item[0] + " must resolve");
            check(payload.keySet().equals(expectedKeys), "only the four Tasker input fields are sent");
            check(item[1].equals(payload.get("ch.rmy.android.http_shortcuts.shortcut_id")), "saved scene ID preserved");
            check(item[2].equals(payload.get("ch.rmy.android.http_shortcuts.shortcut_name")), "saved scene name preserved");
            check("ch.rmy.android.http_shortcuts.plugin.TriggerShortcutActionRunner".equals(payload.get(
                "net.dinglisch.android.tasker.extras.ACTION_RUNNER_CLASS")), "fixed runner class");
            check("ch.rmy.android.http_shortcuts.plugin.Input".equals(payload.get(
                "net.dinglisch.android.tasker.extras.ACTION_INPUT_CLASS")), "fixed input class");
            try {
                payload.put("ch.rmy.android.http_shortcuts.shortcut_id", "arbitrary-id");
                throw new AssertionError("payload must not be mutable");
            } catch (UnsupportedOperationException expectedFailure) { checks++; }
        }
        for (String invalid : new String[]{null, "", "READ", "dev.huesync.relay.read",
                "dev.huesync.relay.READ ", "dev.huesync.relay.START",
                "dev.huesync.relay.READ?shortcut_id=arbitrary", "android.intent.action.BOOT_COMPLETED"}) {
            check(RelayPolicy.payloadFor(invalid) == null, "reject non-whitelisted action");
        }
        check(RelayPolicy.TARGET_PACKAGE.equals("ch.rmy.android.http_shortcuts"), "fixed destination package");
        check(RelayPolicy.TARGET_SERVICE.equals("com.joaomgcd.taskerpluginlibrary.action.IntentServiceAction"), "exported plugin destination");
        check(RelayPolicy.TASKER_ACTION.equals("com.twofortyfouram.locale.intent.action.FIRE_SETTING"), "Tasker fire action");
        check(RelayPolicy.BUNDLE_KEY.equals("com.twofortyfouram.locale.intent.extra.BUNDLE"), "nested Bundle key");
        System.out.println("PASS: " + checks + " relay policy checks");
    }
}
