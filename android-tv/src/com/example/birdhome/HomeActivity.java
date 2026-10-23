package com.example.birdhome;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;

/**
 * Minimal home screen: the BirdWall collage full-screen, a clock, and the "heard today" line.
 * Refreshes every 5 minutes (BirdWall skips the redraw when nothing changed).
 * Add your own app dock on top: query PackageManager for CATEGORY_LEANBACK_LAUNCHER activities.
 */
public class HomeActivity extends Activity {
    static final long REFRESH_MS = 5 * 60_000L;
    final Handler ui = new Handler(Looper.getMainLooper());
    BirdWall wall;
    ImageView art;
    TextView clock, summary;
    volatile String signature;

    final Runnable tick = this::refresh;
    final Runnable clockTick = new Runnable() {
        public void run() {
            clock.setText(android.text.format.DateFormat.format("h:mm", System.currentTimeMillis()));
            ui.postDelayed(this, 10_000);
        }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        java.io.File dir = getExternalFilesDir(null);
        wall = new BirdWall(dir != null ? dir : getFilesDir());   // reads files/birds.conf if present

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(BirdWall.PAPER);
        art = new ImageView(this);
        art.setScaleType(ImageView.ScaleType.FIT_XY);
        root.addView(art, new FrameLayout.LayoutParams(-1, -1));

        clock = text(96, 0xFF141414);
        summary = text(18, 0xFF3A352C);
        summary.setLetterSpacing(0.2f);
        FrameLayout.LayoutParams lc = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        lc.setMargins(110, 140, 0, 0);
        FrameLayout.LayoutParams ls = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        ls.setMargins(110, 560, 0, 0);
        root.addView(clock, lc);
        root.addView(summary, ls);
        setContentView(root);
    }

    TextView text(float sp, int color) {
        TextView t = new TextView(this);
        t.setTextSize(sp); t.setTextColor(color); t.setTypeface(android.graphics.Typeface.create("sans-serif-light", 0));
        return t;
    }

    @Override protected void onResume() { super.onResume(); clockTick.run(); refresh(); }
    @Override protected void onPause() { super.onPause(); ui.removeCallbacks(tick); ui.removeCallbacks(clockTick); }
    @Override public void onBackPressed() { /* this is the home screen: nothing to go back to */ }

    void refresh() {
        ui.removeCallbacks(tick);
        DisplayMetrics m = getResources().getDisplayMetrics();
        final int W = m.widthPixels, H = m.heightPixels;
        new Thread(() -> {
            try {
                BirdWall.Result r = wall.build(W, H, signature);
                if (r != null) ui.post(() -> {
                    summary.setText(r.summary);
                    if (r.bitmap != null) { art.setImageBitmap(r.bitmap); signature = r.signature; }
                });
            } catch (Throwable t) {
                Log.w(BirdWall.TAG, "refresh failed: " + t);
            }
            ui.postDelayed(tick, REFRESH_MS);
        }).start();
    }
}
