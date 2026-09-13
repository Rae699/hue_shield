package dev.huesync.relay;

final class NativeShortcutIds {
    private NativeShortcutIds() {}
    static String id(String kind) {
        if ("READ_CHECK".equals(kind)) return "bcf66fef-ec09-5a74-9cb0-276bc6fc8c40";
        if ("READ_RECALL".equals(kind)) return "53d095f1-ed94-5ee5-9a4a-0a66f253d140";
        if ("PROBE".equals(kind)) return "899d6091-2e51-5670-ac08-0ad3fdc06aad";
        if ("START".equals(kind)) return "7914b195-3555-5b8a-a4d5-bbc54890482e";
        if ("STOP".equals(kind)) return "2b1b7f54-1a3e-53f1-9691-69d972a0ddfd";
        return null;
    }
    static String name(String kind) {
        if ("READ_CHECK".equals(kind)) return "Hue Relay - Read Check";
        if ("READ_RECALL".equals(kind)) return "Hue Relay - Read Recall";
        if ("PROBE".equals(kind)) return "Hue Relay - Probe";
        if ("START".equals(kind)) return "Hue Relay - Start";
        if ("STOP".equals(kind)) return "Hue Relay - Stop";
        return null;
    }
}
