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
    // tap / START: on a bird, switch perched <-> flying; on the summary, go to the first bird
    function onSelect() as Boolean {
        if (view.page == 0) { view.next(); } else { view.togglePose(); }
        return true;
    }
    function onMenu() as Boolean { view.togglePose(); return true; }    // press and hold
}
