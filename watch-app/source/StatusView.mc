import Toybox.Graphics;
import Toybox.Time;
import Toybox.WatchUi;

class StatusView extends WatchUi.View {
    var stream;
    function initialize(s) { View.initialize(); stream = s; }
    function onShow() { stream.start(); }
    function onHide() { stream.stop(); }
    function onUpdate(dc) {
        dc.setColor(0xE7FFF4, 0x132D28);
        dc.clear();
        var cx = dc.getWidth() / 2;
        dc.drawText(cx, 65, Graphics.FONT_MEDIUM, "BioTwin Live", Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, 120, Graphics.FONT_SMALL, stream.status, Graphics.TEXT_JUSTIFY_CENTER);
        var sync = stream.lastSync == null ? "Waiting for delivery" : "Synced " + (Time.now().value() - stream.lastSync) + "s ago";
        dc.drawText(cx, 170, Graphics.FONT_SMALL, sync, Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, 215, Graphics.FONT_SMALL, "Sent " + stream.sent + " | Queued " + stream.queued(), Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, 260, Graphics.FONT_XTINY, "Overflow lost: " + stream.dropped, Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(cx, 295, Graphics.FONT_XTINY, "Keep this app open", Graphics.TEXT_JUSTIFY_CENTER);
    }
}
