package com.example.birdhome;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Random;

/**
 * "Avian Visitors" style wallpaper: every bird BirdNET-Go heard in the last 24 hours,
 * as kachō-e cut-outs packed onto a cream mulberry-paper ground, sized by how often
 * each one called. Layout follows Avian Visitors: area ∝ n^0.65 normalised to a
 * budget, centre-out elliptical spiral placement with silhouette-mask collision,
 * shrink-and-repack until everything fits.
 *
 * Optional config: files/birds.conf (key=value): api, img1, img2, hours, budget.
 */
class BirdWall {
    static final String TAG = "BirdHome";
    static final int PAPER = 0xFFEFE6D2;

    final File cacheDir, confFile;
    String api = "http://birdnet.local:8080";               // your BirdNET-Go (stays on your network)
    String img1 = "";                                       // optional: your own cut-outs folder (tried first)
    String img2 = "https://raw.githubusercontent.com/tandarra/avianvisitors-NewZealand/main/birds/";  // NZ cut-outs
    int hours = 24;
    float budgetScale = 1f;
    final Map<String, Long> missing = new HashMap<>();

    static class Species {
        String sci, com, slug, last; int count;
    }
    static class Result {
        Bitmap bitmap; int species, calls; String signature, summary;
    }

    BirdWall(File filesDir) {
        cacheDir = new File(filesDir, "birdcache");
        cacheDir.mkdirs();
        confFile = new File(filesDir, "birds.conf");
        loadConf();
    }

    void loadConf() {
        if (!confFile.exists()) return;
        try (FileInputStream in = new FileInputStream(confFile)) {
            Properties p = new Properties(); p.load(in);
            api = trim(p.getProperty("api", api));
            img1 = slash(p.getProperty("img1", img1));
            img2 = slash(p.getProperty("img2", img2));
            hours = Integer.parseInt(p.getProperty("hours", String.valueOf(hours)).trim());
            budgetScale = Float.parseFloat(p.getProperty("budget", "1").trim());
        } catch (Exception e) { Log.w(TAG, "conf: " + e); }
    }
    static String trim(String s) { s = s.trim(); return s.endsWith("/") ? s.substring(0, s.length() - 1) : s; }
    static String slash(String s) { s = s.trim(); return s.isEmpty() || s.endsWith("/") ? s : s + "/"; }

    static String slug(String sci) {
        return sci.toLowerCase(Locale.ROOT).replaceAll("[^a-z]+", "-").replaceAll("^-|-$", "");
    }

    // ------------------------------------------------------------------ data
    List<Species> fetchSpecies() throws Exception {
        Calendar now = Calendar.getInstance();
        int hr = now.get(Calendar.HOUR_OF_DAY);
        SimpleDateFormat df = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        Map<String, Species> out = new HashMap<>();
        addDay(out, df.format(now.getTime()), 0, hr);
        int back = Math.min(24, Math.max(0, hours)) - (hr + 1);
        if (back > 0) {
            Calendar y = (Calendar) now.clone(); y.add(Calendar.DAY_OF_YEAR, -1);
            addDay(out, df.format(y.getTime()), 24 - back, 23);
        }
        List<Species> list = new ArrayList<>(out.values());
        Collections.sort(list, (a, b) -> b.count - a.count);
        return list;
    }

    void addDay(Map<String, Species> out, String date, int fromHr, int toHr) throws Exception {
        String body = new String(get(api + "/api/v2/analytics/species/daily?date=" + date, 8000), "UTF-8");
        JSONArray a = new JSONArray(body);
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.getJSONObject(i);
            String sci = o.optString("scientific_name", "");
            if (sci.isEmpty()) continue;
            int n = 0;
            JSONArray h = o.optJSONArray("hourly_counts");
            if (h != null) for (int k = fromHr; k <= toHr && k < h.length(); k++) n += h.optInt(k);
            else if (fromHr == 0) n = o.optInt("count");
            if (n <= 0) continue;
            Species s = out.get(sci);
            if (s == null) {
                s = new Species(); s.sci = sci; s.com = o.optString("common_name", sci); s.slug = slug(sci);
                out.put(sci, s);
            }
            s.count += n;
            String lh = o.optString("latest_heard", "");
            if (fromHr == 0 && !lh.isEmpty()) s.last = lh;
        }
    }

    static byte[] get(String url, int timeout) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(timeout); c.setReadTimeout(timeout);
        c.setRequestProperty("User-Agent", "BirdHome");
        int code = c.getResponseCode();
        if (code != 200) { c.disconnect(); throw new Exception("HTTP " + code + " " + url); }
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream o = new ByteArrayOutputStream();
            byte[] buf = new byte[16384]; int k;
            while ((k = in.read(buf)) > 0) o.write(buf, 0, k);
            return o.toByteArray();
        } finally { c.disconnect(); }
    }

    /** Cached cut-out for slug+suffix ("" perched, "-2" second pose); null if unavailable. */
    File image(String name) {
        File f = new File(cacheDir, name + ".webp");
        if (f.exists() && f.length() > 0) return f;
        Long miss = missing.get(name);
        if (miss != null && System.currentTimeMillis() - miss < 3_600_000L) return null;
        for (String base : new String[]{img1, img2}) {
            if (base == null || base.isEmpty()) continue;
            try {
                byte[] b = get(base + name + ".webp", 10000);
                if (b.length < 100) continue;
                File tmp = new File(cacheDir, name + ".tmp");
                try (FileOutputStream o = new FileOutputStream(tmp)) { o.write(b); }
                if (tmp.renameTo(f)) { missing.remove(name); return f; }
            } catch (Exception ignored) { }
        }
        missing.put(name, System.currentTimeMillis());
        return null;
    }

    // ---------------------------------------------------------------- render
    static class Tile {
        Species sp; Bitmap bmp; float ar, area; int w, h, gx, gy, gw, gh; boolean[] mask;
    }

    /** Fetch and render. Returns null if nothing changed since {@code lastSig}. */
    Result build(int W, int H, String lastSig) throws Exception {
        List<Species> all = fetchSpecies();
        List<Tile> tiles = new ArrayList<>();
        StringBuilder sig = new StringBuilder(W + "x" + H + ";");
        int calls = 0;
        for (int i = 0; i < all.size(); i++) {
            Species s = all.get(i);
            calls += s.count;
            // a third of the birds fly, for movement in the collage (falls back to perched)
            boolean fly = i % 3 == 2;
            File f = fly ? image(s.slug + "-2") : null;
            if (f == null) f = image(s.slug);
            if (f == null) { f = image(s.slug + "-2"); fly = f != null; }
            if (f == null) continue;
            Tile t = new Tile(); t.sp = s; tiles.add(t);
            t.bmp = decode(f, 520);
            if (t.bmp == null) { tiles.remove(t); continue; }
            // mirror a stable ~45% of birds so the flock doesn't all face the same way
            boolean flip = facesRight(s.slug + (fly ? "^" : ""));
            if (flip) {
                android.graphics.Matrix m = new android.graphics.Matrix(); m.preScale(-1f, 1f);
                Bitmap fb = Bitmap.createBitmap(t.bmp, 0, 0, t.bmp.getWidth(), t.bmp.getHeight(), m, true);
                if (fb != t.bmp) { t.bmp.recycle(); t.bmp = fb; }
            }
            t.ar = t.bmp.getWidth() / (float) t.bmp.getHeight();
            sig.append(s.slug).append(fly ? "^" : "").append(flip ? "~" : "").append(':').append(bucket(s.count)).append(',');
        }
        Result r = new Result();
        r.species = all.size(); r.calls = calls;
        r.signature = sig.toString();
        Species top = all.isEmpty() ? null : all.get(0);
        r.summary = all.isEmpty() ? "LISTENING FOR BIRDS"
                : "HEARD TODAY  ·  " + all.size() + (all.size() == 1 ? " SPECIES" : " SPECIES")
                  + "  ·  " + calls + " CALLS" + (top != null ? "  ·  MOST: " + top.com.toUpperCase(Locale.ROOT) : "");
        if (r.signature.equals(lastSig)) { recycle(tiles); return r; }
        r.bitmap = render(W, H, tiles);
        recycle(tiles);
        return r;
    }

    /** Stable per-bird coin toss (same answer every refresh). */
    static boolean facesRight(String key) {
        int h = 0x811C9DC5;
        for (int i = 0; i < key.length(); i++) { h ^= key.charAt(i); h *= 0x01000193; }
        return Integer.remainderUnsigned(h, 100) < 45;
    }

    static int bucket(int n) { return n < 3 ? n : (int) Math.round(Math.log(n) * 4); }
    static void recycle(List<Tile> ts) { for (Tile t : ts) if (t.bmp != null) t.bmp.recycle(); }

    static Bitmap decode(File f, int maxSide) {
        try {
            BitmapFactory.Options o = new BitmapFactory.Options(); o.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(f.getAbsolutePath(), o);
            int s = 1; while (Math.max(o.outWidth, o.outHeight) / (s * 2) >= maxSide) s *= 2;
            BitmapFactory.Options o2 = new BitmapFactory.Options(); o2.inSampleSize = s;
            return BitmapFactory.decodeFile(f.getAbsolutePath(), o2);
        } catch (Throwable t) { return null; }
    }

    Bitmap render(int W, int H, List<Tile> tiles) {
        Bitmap out = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(out);
        paper(c, W, H);
        if (tiles.isEmpty()) return out;

        final int cell = Math.max(4, W / 320);
        final int GW = W / cell, GH = H / cell;
        boolean[] reserved = new boolean[GW * GH];
        // keep clear: clock/greeting (top-left), nav (top-right), favourites dock (bottom), small border
        reserve(reserved, GW, GH, 0, 0, 0.40f, 0.50f);
        reserve(reserved, GW, GH, 0, 0.50f, 0.62f, 0.62f);   // summary line under the date
        reserve(reserved, GW, GH, 0.70f, 0, 1f, 0.10f);
        reserve(reserved, GW, GH, 0, 0.68f, 1f, 1f);         // favourites dock
        reserve(reserved, GW, GH, 0, 0, 1f, 0.025f);
        reserve(reserved, GW, GH, 0, 0, 0.015f, 1f);
        reserve(reserved, GW, GH, 0.985f, 0, 1f, 1f);
        int free = 0; for (boolean b : reserved) if (!b) free++;
        float freeArea = free * (float) cell * cell;

        // sizing: s = n^0.65, normalised to a budget of the free area
        double sum = 0; for (Tile t : tiles) sum += Math.pow(t.sp.count, 0.65);
        float frac = (0.42f + 0.18f * Math.min(1f, tiles.size() / 25f)) * budgetScale;
        float budget = freeArea * frac;
        float aMin = (float) Math.pow(H * 0.075, 2);
        float aMax = (float) Math.pow(H * 0.42, 2);
        for (Tile t : tiles) {
            float a = (float) (budget * Math.pow(t.sp.count, 0.65) / sum);
            t.area = Math.min(aMax, Math.max(aMin, a));
        }
        tiles.sort((a, b) -> Float.compare(b.area, a.area));

        // candidate offsets, nearest first on a horizontally stretched ellipse (bias 2.1)
        final float bias = 2.1f;
        int rx = GW, ry = GH;
        long[] cand = new long[(2 * rx + 1) * (2 * ry + 1)];
        int ci = 0;
        for (int dy = -ry; dy <= ry; dy++) for (int dx = -rx; dx <= rx; dx++) {
            double cost = Math.sqrt((dx / bias) * (dx / bias) + dy * dy);
            cand[ci++] = ((long) (cost * 64) << 32) | ((long) (dy + ry) << 16) | (dx + rx);
        }
        Arrays.sort(cand);
        int cx = (int) (GW * 0.63f), cy = (int) (GH * 0.40f);

        float scale = 1f;
        boolean[] occ = null;
        for (int attempt = 0; attempt < 12; attempt++) {
            occ = reserved.clone();
            boolean ok = true;
            for (Tile t : tiles) {
                float a = t.area * scale * scale;
                t.w = Math.max(cell * 3, Math.round((float) Math.sqrt(a * t.ar)));
                t.h = Math.max(cell * 3, Math.round(t.w / t.ar));
                t.gw = (t.w + cell - 1) / cell; t.gh = (t.h + cell - 1) / cell;
                t.mask = mask(t.bmp, t.gw, t.gh);
                if (!place(t, occ, GW, GH, cand, rx, ry, cx, cy)) { ok = false; break; }
            }
            if (ok) break;
            scale *= 0.93f;
        }

        Paint p = new Paint(Paint.FILTER_BITMAP_FLAG | Paint.ANTI_ALIAS_FLAG);
        for (Tile t : tiles) {
            if (t.gx < 0) continue;
            float x = t.gx * cell + (t.gw * cell - t.w) / 2f, y = t.gy * cell + (t.gh * cell - t.h) / 2f;
            c.drawBitmap(t.bmp, null, new RectF(x, y, x + t.w, y + t.h), p);
        }
        return out;
    }

    static void reserve(boolean[] g, int GW, int GH, float x0, float y0, float x1, float y1) {
        for (int y = (int) (y0 * GH); y < Math.min(GH, (int) Math.ceil(y1 * GH)); y++)
            for (int x = (int) (x0 * GW); x < Math.min(GW, (int) Math.ceil(x1 * GW)); x++) g[y * GW + x] = true;
    }

    /** Silhouette mask on the placement grid, dilated by one cell so birds keep a little air. */
    static boolean[] mask(Bitmap b, int gw, int gh) {
        boolean[] m = new boolean[gw * gh];
        int bw = b.getWidth(), bh = b.getHeight();
        for (int y = 0; y < gh; y++) for (int x = 0; x < gw; x++) {
            boolean on = false;
            for (int sy = 0; sy < 2 && !on; sy++) for (int sx = 0; sx < 2 && !on; sx++) {
                int px = Math.min(bw - 1, (int) ((x + 0.25f + sx * 0.5f) / gw * bw));
                int py = Math.min(bh - 1, (int) ((y + 0.25f + sy * 0.5f) / gh * bh));
                on = Color.alpha(b.getPixel(px, py)) > 40;
            }
            m[y * gw + x] = on;
        }
        boolean[] d = m.clone();
        for (int y = 0; y < gh; y++) for (int x = 0; x < gw; x++) if (m[y * gw + x])
            for (int oy = -1; oy <= 1; oy++) for (int ox = -1; ox <= 1; ox++) {
                int nx = x + ox, ny = y + oy;
                if (nx >= 0 && ny >= 0 && nx < gw && ny < gh) d[ny * gw + nx] = true;
            }
        return d;
    }

    static boolean place(Tile t, boolean[] occ, int GW, int GH, long[] cand, int rx, int ry, int cx, int cy) {
        t.gx = -1;
        for (long k : cand) {
            int dx = (int) (k & 0xFFFF) - rx, dy = (int) ((k >> 16) & 0xFFFF) - ry;
            int x0 = cx + dx - t.gw / 2, y0 = cy + dy - t.gh / 2;
            if (x0 < 0 || y0 < 0 || x0 + t.gw > GW || y0 + t.gh > GH) continue;
            if (fits(t, occ, GW, x0, y0)) {
                for (int y = 0; y < t.gh; y++) for (int x = 0; x < t.gw; x++)
                    if (t.mask[y * t.gw + x]) occ[(y0 + y) * GW + x0 + x] = true;
                t.gx = x0; t.gy = y0;
                return true;
            }
        }
        return false;
    }

    static boolean fits(Tile t, boolean[] occ, int GW, int x0, int y0) {
        // cheap probe at the centre first
        int mc = (t.gh / 2) * t.gw + t.gw / 2;
        if (t.mask[mc] && occ[(y0 + t.gh / 2) * GW + x0 + t.gw / 2]) return false;
        for (int y = 0; y < t.gh; y++) {
            int row = (y0 + y) * GW + x0, mrow = y * t.gw;
            for (int x = 0; x < t.gw; x++) if (t.mask[mrow + x] && occ[row + x]) return false;
        }
        return true;
    }

    /** Warm cream mulberry paper with faint fibre speckle. */
    static void paper(Canvas c, int W, int H) {
        c.drawColor(PAPER);
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        Random r = new Random(1672L);
        for (int i = 0; i < W * H / 900; i++) {
            p.setColor(r.nextBoolean() ? 0x0F6B5A3C : 0x0AFFFFFF);
            float x = r.nextFloat() * W, y = r.nextFloat() * H, len = 2 + r.nextFloat() * 10;
            double a = r.nextDouble() * Math.PI;
            p.setStrokeWidth(0.6f + r.nextFloat());
            c.drawLine(x, y, x + (float) (Math.cos(a) * len), y + (float) (Math.sin(a) * len), p);
        }
    }
}
