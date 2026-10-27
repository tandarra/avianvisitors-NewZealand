import Toybox.Application;
import Toybox.Communications;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Time;
import Toybox.WatchUi;

// Page 0: today's summary. Pages 1..n: one bird each, most-heard first, with its painting.
class BirdsView extends WatchUi.View {
    const PAPER = 0xEFE6D2;
    const INK = 0x141414;
    const MUTE = 0x6B665C;
    const ACCENT = 0x8C3B1F;
    const IMG_SIZE = 200;

    var page = 0;
    var data = null;
    var loading = false;
    var failed = false;
    var images = {} as Dictionary;      // slug -> bitmap, or false while loading / if missing

    function initialize() {
        View.initialize();
        data = Application.Storage.getValue("today");
    }

    function onShow() as Void {
        var t = (data instanceof Dictionary) ? data["t"] as Number : 0;
        if (Time.now().value() - t > 5 * 60) { fetch(); }
        loadImages();
    }

    function species() as Array {
        return (data instanceof Dictionary) ? data["sp"] as Array : [] as Array;
    }

    function pages() as Number { return species().size() + 1; }

    function next() as Void { if (page < pages() - 1) { page++; loadImages(); WatchUi.requestUpdate(); } }
    function prev() as Void { if (page > 0) { page--; loadImages(); WatchUi.requestUpdate(); } }

    // ---- data
    function fetch() as Void {
        if (loading) { return; }
        loading = true; failed = false;
        Communications.makeWebRequest(BirdsApi.URL, null, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, method(:onData));
        WatchUi.requestUpdate();
    }

    function onData(code as Number, d as Dictionary or String or Null) as Void {
        loading = false;
        if (code == 200 && d instanceof Dictionary) {
            data = BirdsApi.compact(d);
            Application.Storage.setValue("today", data);
            if (page >= pages()) { page = pages() - 1; }
            loadImages();
        } else {
            failed = true;
        }
        WatchUi.requestUpdate();
    }

    // the current bird and the next one, so swiping feels instant
    function loadImages() as Void {
        var sp = species();
        for (var p = page; p <= page + 1; p++) {
            if (p < 1 || p > sp.size()) { continue; }
            var slug = (sp[p - 1] as Array)[1] as String;
            if (images.hasKey(slug)) { continue; }
            images[slug] = false;
            if (images.size() > 6) { trim(slug); }
            Communications.makeImageRequest(BirdsApi.IMG + slug + ".jpg", null, {
                :maxWidth => IMG_SIZE, :maxHeight => IMG_SIZE
            }, new ImageCallback(self, slug).method(:onImage));
        }
    }

    // keep memory low: drop pictures far from the current page
    function trim(keep as String) as Void {
        var sp = species();
        var near = {} as Dictionary;
        for (var p = page - 1; p <= page + 1; p++) {
            if (p >= 1 && p <= sp.size()) { near[(sp[p - 1] as Array)[1]] = true; }
        }
        var keys = images.keys();
        for (var i = 0; i < keys.size(); i++) {
            if (!near.hasKey(keys[i]) && !keys[i].equals(keep)) { images.remove(keys[i]); }
        }
    }

    function setImage(slug as String, img) as Void {
        images[slug] = img;
        WatchUi.requestUpdate();
    }

    // ---- drawing
    function onUpdate(dc as Graphics.Dc) as Void {
        var w = dc.getWidth(), h = dc.getHeight();
        dc.setColor(INK, PAPER);
        dc.clear();
        if (page == 0) { drawSummary(dc, w, h); } else { drawBird(dc, w, h, page - 1); }
        drawDots(dc, w, h);
    }

    function drawSummary(dc as Graphics.Dc, w as Number, h as Number) as Void {
        var cx = w / 2;
        dc.setColor(MUTE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.17, Graphics.FONT_XTINY, "HEARD IN THE GARDEN TODAY", Graphics.TEXT_JUSTIFY_CENTER);
        var sp = species();
        if (!(data instanceof Dictionary)) {
            dc.setColor(INK, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, h / 2, Graphics.FONT_SMALL, loading ? "Loading…" : (failed ? "No connection" : "No data yet"),
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }
        dc.setColor(INK, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.25, Graphics.FONT_NUMBER_THAI_HOT, sp.size().toString(), Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(MUTE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.50, Graphics.FONT_SMALL, (sp.size() == 1 ? "species" : "species") + " · " + BirdsApi.thousands(data["calls"] as Number) + " calls",
            Graphics.TEXT_JUSTIFY_CENTER);
        if (sp.size() > 0) {
            dc.setColor(ACCENT, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, h * 0.62, Graphics.FONT_XTINY, "MOST HEARD", Graphics.TEXT_JUSTIFY_CENTER);
            dc.setColor(INK, Graphics.COLOR_TRANSPARENT);
            fitText(dc, cx, h * 0.68, w * 0.78, (sp[0] as Array)[0] as String);
        }
        dc.setColor(MUTE, Graphics.COLOR_TRANSPARENT);
        var foot = loading ? "updating…" : (failed ? "offline · as of " + clock(data["t"] as Number) : (sp.size() > 0 ? "swipe up for the birds" : ""));
        dc.drawText(cx, h * 0.83, Graphics.FONT_XTINY, foot, Graphics.TEXT_JUSTIFY_CENTER);
    }

    function drawBird(dc as Graphics.Dc, w as Number, h as Number, i as Number) as Void {
        var b = species()[i] as Array;
        var cx = w / 2;
        var img = images.get(b[1]);
        var top = (h * 0.07).toNumber();
        if (img != null && img != false) {
            var bmp = img;
            if (bmp has :get) { bmp = bmp.get(); }        // BitmapReference on newer devices
            if (bmp != null) {
                dc.drawBitmap(cx - bmp.getWidth() / 2, top + (IMG_SIZE - bmp.getHeight()) / 2, bmp);
            }
        } else {
            dc.setColor(0xE2D7BF, Graphics.COLOR_TRANSPARENT);
            dc.fillCircle(cx, top + IMG_SIZE / 2, IMG_SIZE * 0.32);
            dc.setColor(MUTE, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, top + IMG_SIZE / 2, Graphics.FONT_XTINY, img == false ? "painting…" : "not painted yet",
                Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
        dc.setColor(INK, Graphics.COLOR_TRANSPARENT);
        fitText(dc, cx, top + IMG_SIZE + 4, w * 0.84, b[0] as String);
        dc.setColor(MUTE, Graphics.COLOR_TRANSPARENT);
        var n = b[2] as Number;
        var line = BirdsApi.thousands(n) + (n == 1 ? " call" : " calls") + (b[3] != null ? " · last " + b[3] : "");
        dc.drawText(cx, h * 0.80, Graphics.FONT_XTINY, line, Graphics.TEXT_JUSTIFY_CENTER);
    }

    // biggest font that fits the width, wrapping to a second line if needed
    function fitText(dc as Graphics.Dc, x as Number, y as Numeric, maxW as Numeric, s as String) as Void {
        var fonts = [Graphics.FONT_MEDIUM, Graphics.FONT_SMALL, Graphics.FONT_TINY];
        for (var i = 0; i < fonts.size(); i++) {
            if (dc.getTextWidthInPixels(s, fonts[i]) <= maxW) {
                dc.drawText(x, y, fonts[i], s, Graphics.TEXT_JUSTIFY_CENTER);
                return;
            }
        }
        var t = Graphics.fitTextToArea(s, Graphics.FONT_TINY, maxW, dc.getFontHeight(Graphics.FONT_TINY) * 2, true);
        dc.drawText(x, y, Graphics.FONT_TINY, t, Graphics.TEXT_JUSTIFY_CENTER);
    }

    // page indicator down the right edge
    function drawDots(dc as Graphics.Dc, w as Number, h as Number) as Void {
        var n = pages();
        if (n <= 1) { return; }
        var shown = n > 9 ? 9 : n;
        var first = page - 4;
        if (first < 0) { first = 0; }
        if (first > n - shown) { first = n - shown; }
        var gap = 12;
        var y0 = h / 2 - (shown - 1) * gap / 2;
        for (var k = 0; k < shown; k++) {
            var p = first + k;
            dc.setColor(p == page ? INK : 0xC9BFA8, Graphics.COLOR_TRANSPARENT);
            dc.fillCircle(w - 18, y0 + k * gap, p == page ? 4 : 3);
        }
    }

    function clock(t as Number) as String {
        var g = Time.Gregorian.info(new Time.Moment(t), Time.FORMAT_SHORT);
        return g.hour.format("%02d") + ":" + g.min.format("%02d");
    }
}

// Remembers which bird an image request was for.
class ImageCallback {
    var view, slug;
    function initialize(v, s) { view = v; slug = s; }
    function onImage(code as Number, img as WatchUi.BitmapResource or Graphics.BitmapReference or Null) as Void {
        view.setImage(slug, code == 200 ? img : null);
    }
}
