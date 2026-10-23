import Toybox.Application;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

// Widget-loop glance: "GARDEN BIRDS / 16 species · 1,193 calls / Most: Eurasian Skylark"
(:glance)
class BirdsGlanceView extends WatchUi.GlanceView {
    function initialize() {
        GlanceView.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_TRANSPARENT, Graphics.COLOR_BLACK);
        dc.clear();
        var h = dc.getHeight();
        var d = Application.Storage.getValue("today");
        var line1 = "Listening for birds";
        var line2 = "Open to load";
        if (d instanceof Dictionary) {
            var sp = d["sp"] as Array;
            if (sp.size() > 0) {
                line1 = sp.size() + (sp.size() == 1 ? " species · " : " species · ") + BirdsApi.thousands(d["calls"] as Number) + " calls";
                line2 = "Most: " + (sp[0] as Array)[0];
            } else {
                line1 = "No birds yet today";
                line2 = "";
            }
        }
        dc.setColor(0xD9B98A, Graphics.COLOR_TRANSPARENT);
        dc.drawText(0, h * 0.16, Graphics.FONT_GLANCE, "GARDEN BIRDS", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(0, h * 0.50, Graphics.FONT_GLANCE_NUMBER, line1, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(0, h * 0.84, Graphics.FONT_GLANCE, line2, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
    }
}
