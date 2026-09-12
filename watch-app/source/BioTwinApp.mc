import Toybox.Application;
import Toybox.WatchUi;

class BioTwinApp extends Application.AppBase {
    var stream;
    function initialize() { AppBase.initialize(); }
    function onStart(state) { stream = new WatchStream(); }
    function getInitialView() { return [new StatusView(stream)]; }
    function onStop(state) { if (stream != null) { stream.stop(); } }
}
