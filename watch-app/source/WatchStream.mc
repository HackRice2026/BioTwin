import Toybox.ActivityMonitor;
import Toybox.Application.Storage;
import Toybox.Communications;
import Toybox.Math;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.SensorHistory;
import Toybox.Time;
import Toybox.Timer;
import Toybox.WatchUi;

class WatchStream {
    const MAX_QUEUE = 60;
    const BATCH_SIZE = 20;
    var queue as Array = [];
    var flight as Array = [];
    var timer = null;
    var pending = false;
    var running = false;
    var nextSend = 0;
    var retrySeconds = 5;
    var hr = null;
    var hrTime = 0;
    var acceleration = null;
    var accelerationTime = 0;
    var seen as Dictionary = {};
    var status = "Starting";
    var lastSync = null;
    var sent = 0;
    var dropped = 0;

    function initialize() {
        retrySeconds = ApiConfig.SEND_INTERVAL_SECONDS;
        var saved = Storage.getValue("upload");
        // Never deliver the previous account's queued data after re-pairing.
        if (saved instanceof Dictionary && saved["owner"] == ApiConfig.API_KEY && saved["url"] == ApiConfig.API_URL) {
            queue = saved["samples"];
            dropped = saved["dropped"];
        }
    }
    function queued() { return queue.size() + flight.size(); }
    function persist() {
        var rows = [];
        rows.addAll(flight);
        rows.addAll(queue);
        Storage.setValue("upload", {"owner" => ApiConfig.API_KEY, "url" => ApiConfig.API_URL,
            "samples" => rows, "dropped" => dropped});
    }
    function start() {
        if (running) { return; }
        running = true;
        Sensor.setEnabledSensors([Sensor.SENSOR_HEARTRATE]);
        Sensor.enableSensorEvents(method(:onSensor));
        try {
            Sensor.registerSensorDataListener(method(:onMotion), {
                :period => 1,
                :accelerometer => {:enabled => true, :sampleRate => 25}
            });
        } catch (e) { acceleration = null; }
        timer = new Timer.Timer();
        timer.start(method(:tick), ApiConfig.SEND_INTERVAL_SECONDS * 1000, true);
        tick();
    }
    function stop() {
        if (!running) { return; }
        running = false;
        if (timer != null) { timer.stop(); timer = null; }
        Sensor.enableSensorEvents(null);
        Sensor.unregisterSensorDataListener();
        persist();
    }
    function onSensor(info as Sensor.Info) as Void {
        hr = info.heartRate;
        hrTime = Time.now().value();
    }
    function onMotion(data as Sensor.SensorData) as Void {
        var a = data.accelerometerData;
        if (a == null || a.x == null || a.y == null || a.z == null || a.x.size() == 0) { return; }
        var i = a.x.size() - 1;
        // Magnitude of the newest raw sample in milligravity, including gravity.
        // This is not an inferred activity or readiness score.
        var x = a.x[i].toFloat();
        var y = a.y[i].toFloat();
        var z = a.z[i].toFloat();
        acceleration = Math.sqrt(x*x + y*y + z*z);
        accelerationTime = Time.now().value();
    }
    function valid(value, low, high) { return value != null && value >= low && value <= high; }
    function add(row) {
        if (queue.size() >= MAX_QUEUE) {
            queue = queue.slice(1, queue.size());
            dropped += 1;
        }
        queue.add(row);
    }
    function historyRow(metric, iterator, low, high) {
        if (iterator == null) { return; }
        var sample = iterator.next();
        if (sample == null || !valid(sample.data, low, high)) { return; }
        var stamp = sample.when.value();
        var identity = stamp.toString() + ":" + sample.data.toString();
        if (seen[metric] == identity) { return; }
        var row = {"event_time" => stamp};
        row[metric] = sample.data;
        add(row);
        seen[metric] = identity;
    }
    function collect() {
        var now = Time.now().value();
        var row = {"event_time" => now};
        var info = ActivityMonitor.getInfo();
        if (valid(info.steps, 0, 200000)) { row["steps"] = info.steps; }
        // Garmin calories includes resting and active energy. Do not label it active calories.
        if (valid(info.calories, 0, 30000)) { row["total_calories"] = info.calories; }
        if (valid(info.distance, 0, 50000000)) { row["distance_m"] = info.distance / 100.0; }
        if (info has :floorsClimbed && valid(info.floorsClimbed, 0, 1000)) { row["floors_climbed"] = info.floorsClimbed; }
        if (row.size() > 1) { add(row); }
        if (valid(hr, 25, 250) && now - hrTime <= 10) {
            add({"event_time" => hrTime, "heart_rate_bpm" => hr});
        } else {
            // Proven fallback from the reference app, retaining the source timestamp.
            var iterator = ActivityMonitor.getHeartRateHistory(1, true);
            if (iterator != null) {
                var sample = iterator.next();
                if (sample != null && sample.when != null && sample.heartRate != ActivityMonitor.INVALID_HR_SAMPLE && valid(sample.heartRate, 25, 250)) {
                    add({"event_time" => sample.when.value(), "heart_rate_bpm" => sample.heartRate});
                }
            }
        }
        if (valid(acceleration, 0, 32000) && now - accelerationTime <= 5) {
            add({"event_time" => accelerationTime, "acceleration_mg" => acceleration});
        }
        var options = {:period => 1, :order => SensorHistory.ORDER_NEWEST_FIRST};
        if (SensorHistory has :getBodyBatteryHistory) {
            historyRow("body_battery", SensorHistory.getBodyBatteryHistory(options), 0, 100);
        }
        if (SensorHistory has :getStressHistory) {
            historyRow("stress_level", SensorHistory.getStressHistory(options), 0, 100);
        }
        if (SensorHistory has :getOxygenSaturationHistory) {
            historyRow("spo2_pct", SensorHistory.getOxygenSaturationHistory(options), 50, 100);
        }
    }
    function tick() as Void {
        collect();
        persist();
        if (!pending && Time.now().value() >= nextSend) { send(); }
        WatchUi.requestUpdate();
    }
    function send() {
        if (flight.size() == 0 && queue.size() > 0) {
            var count = queue.size() < BATCH_SIZE ? queue.size() : BATCH_SIZE;
            flight = queue.slice(0, count);
            queue = queue.slice(count, queue.size());
        }
        if (flight.size() == 0) { status = "No sensor data"; return; }
        persist();
        pending = true;
        status = "Sending";
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_POST,
            :headers => {
                "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON,
                "x-api-key" => ApiConfig.API_KEY
            },
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON,
            :timeout => 15
        };
        try {
            Communications.makeWebRequest(ApiConfig.API_URL, {"samples" => flight}, options, method(:onReceive));
        } catch (e) { onReceive(-1, null); }
    }
    function onReceive(code as Number, data as Dictionary or String or Null) as Void {
        pending = false;
        if (code == 200 && data != null && data instanceof Toybox.Lang.Dictionary
            && data["accepted"] != null && data["duplicates"] != null
            && data["accepted"] + data["duplicates"] == flight.size()) {
            sent += flight.size();
            flight = [];
            lastSync = Time.now().value();
            retrySeconds = ApiConfig.SEND_INTERVAL_SECONDS;
            status = "Connected";
        } else {
            status = code == 401 ? "Re-pair in web app" : "Error " + code + " - retrying";
            retrySeconds = retrySeconds * 2;
            if (retrySeconds > 60) { retrySeconds = 60; }
        }
        nextSend = Time.now().value() + retrySeconds;
        persist();
        if (running) { WatchUi.requestUpdate(); }
    }
}
