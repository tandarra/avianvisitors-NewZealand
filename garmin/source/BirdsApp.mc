import Toybox.Application;
import Toybox.Background;
import Toybox.Lang;
import Toybox.System;
import Toybox.Time;
import Toybox.WatchUi;

(:background, :glance)
class BirdsApp extends Application.AppBase {
    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        schedule();
        var view = new BirdsView();
        return [view, new BirdsDelegate(view)];
    }

    function getGlanceView() {
        schedule();
        return [new BirdsGlanceView()];
    }

    function getServiceDelegate() {
        return [new BirdsService()];
    }

    // Results from the background refresh land here.
    function onBackgroundData(data) {
        if (data instanceof Dictionary) {
            Application.Storage.setValue("today", data);
            WatchUi.requestUpdate();
        }
    }

    // Refresh in the background every 30 minutes so the glance is current without opening the app.
    function schedule() as Void {
        try {
            if (Background.getTemporalEventRegisteredTime() == null) {
                Background.registerForTemporalEvent(new Time.Duration(30 * 60));
            }
        } catch (e) {
        }
    }
}
