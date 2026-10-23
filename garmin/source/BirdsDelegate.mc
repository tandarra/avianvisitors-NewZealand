import Toybox.Lang;
import Toybox.WatchUi;

class BirdsDelegate extends WatchUi.BehaviorDelegate {
    var view;

    function initialize(v) {
        BehaviorDelegate.initialize();
        view = v;
    }

    function onNextPage() as Boolean { view.next(); return true; }      // swipe up / DOWN button
    function onPreviousPage() as Boolean { view.prev(); return true; }  // swipe down / UP button
    function onSelect() as Boolean { view.next(); return true; }        // tap / START
}
