import Toybox.Lang;
import Toybox.Time;

// Today's garden birds from the same live feed as birds.tandarra.net.
// Stored compactly: {"t" => fetched (epoch s), "calls" => n, "sp" => [[common, slug, count, last], ...]}
(:background, :glance)
module BirdsApi {
    const URL = "https://birds.tandarra.net/api/today";
    const IMG = "https://birds.tandarra.net/birds/watch/";
    const MAX_SPECIES = 30;

    function compact(data as Dictionary) as Dictionary {
        var out = [] as Array;
        var sp = data["species"];
        var calls = 0;
        if (sp instanceof Array) {
            for (var i = 0; i < sp.size(); i++) {
                var s = sp[i];
                if (!(s instanceof Dictionary)) { continue; }
                var n = s["count"];
                if (n instanceof Number) { calls += n; } else { n = 0; }
                if (out.size() < MAX_SPECIES) {
                    out.add([s["com"], s["slug"], n, s["last"]]);
                }
            }
        }
        if (data["calls"] instanceof Number) { calls = data["calls"]; }
        return {"t" => Time.now().value(), "calls" => calls, "sp" => out};
    }

    // 1193 -> "1,193"
    function thousands(n as Number) as String {
        var s = n.toString();
        var out = "";
        var k = 0;
        for (var i = s.length() - 1; i >= 0; i--) {
            out = s.substring(i, i + 1) + out;
            k++;
            if (k % 3 == 0 && i > 0) { out = "," + out; }
        }
        return out;
    }
}
