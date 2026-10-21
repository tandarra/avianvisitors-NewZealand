#!/usr/bin/env python3
"""
NZ bird illustrations for the Home Assistant "Field Journal" card.

Builds a species list from eBird (birds reported near Pōkeno, or a whole region),
asks Gemini to paint each one as a kachō-e style woodblock print on cream paper,
then cuts the background away so the bird sits cleanly on the card.

Keys: put them in a file called bird_keys.txt next to this script, one per line:
    GEMINI_API_KEY=...
    EBIRD_API_KEY=...
(or set them as environment variables; those win if both exist)

Install once:
    pip install requests pillow "rembg[cpu]"

Typical runs:
    python nz_bird_illustrations.py --limit 3          # test: 3 birds only
    python nz_bird_illustrations.py                    # everything near home (last 30 days, 25 km)
    python nz_bird_illustrations.py --region NZ-WKO    # whole Waikato list (bigger, costs more)
    python nz_bird_illustrations.py --region NZ --list-only   # whole-NZ master list + cost estimate
    python nz_bird_illustrations.py --progress                # master index: birds/master_index.csv + .html
    python nz_bird_illustrations.py --species "Tui"    # redo one bird (use --force to overwrite)

  Batch the NZ list with your best image as the style guide (+ optional photos in birds/refs/<slug>.jpg):
    py nz_bird_illustrations.py --from-prompts --style-ref birds/raw/prosthemadera-novaeseelandiae.png

To redo a bad image: delete it from birds/raw/ and run again for that bird.

Output:
    birds/raw/<slug>.png / <slug>-2.png   original paintings (perched / in flight)
    birds/<slug>.webp / <slug>-2.webp     cut-outs used by the card  (slug = scientific name, e.g. prosthemadera-novaeseelandiae)
"""
import argparse, base64, io, json, os, re, sys, time
from pathlib import Path

import requests
from PIL import Image

HOME_LAT, HOME_LNG = -37.25, 175.02
EBIRD = "https://api.ebird.org/v2"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Prompt template adapted from Avian Visitors by Teddy Warner (CC-BY-NC-SA-4.0).
PROMPT = (
    "Generate a {pose} {com} ({sci}) in the style of an Edo-period Japanese kacho-e woodblock print. "
    "Render with VERY FEW MARKS: the body is 2-4 flat color zones with sharp boundaries, not feather-by-feather texture. "
    "Confident sumi-e ink linework, soft watercolor washes. Earthy palette: burnt umber, ochre, indigo, vermillion, muted greens. "
    "Eye, beak, and feet in crisp ink.\n\n"
    "The bird sits on a CONSISTENT WARM CREAM ground (aged mulberry paper), filling the frame, identical across every print. "
    "This is the only background: NO branch, NO twig, NO perch, NO scenery. The perch is implied by toe posture, never drawn.\n\n"
    "- Exactly two wings, two legs, one head, one beak, one tail.\n"
    "- Posture, color, and markings match {com} field references (as the bird appears in New Zealand).\n"
    "- {rule}"
)
POSES = {
    "": dict(pose="perched", rule="Perched: one wing folded, the other tucked."),
    "-2": dict(pose="in-flight", rule="Flight: both wings fully extended."),
}
# The NZ birds the community illustration sets don't cover (used by --from-prompts).
NZ_BIRDS = {
    "Prosthemadera novaeseelandiae": "Tui", "Rhipidura fuliginosa": "New Zealand Fantail",
    "Hemiphaga novaeseelandiae": "New Zealand Pigeon", "Ninox novaeseelandiae": "Morepork",
    "Gerygone igata": "Gray Gerygone", "Anthornis melanura": "New Zealand Bellbird",
    "Petroica macrocephala": "Tomtit", "Nestor meridionalis": "New Zealand Kaka",
    "Falco novaeseelandiae": "New Zealand Falcon", "Cyanoramphus auriceps": "Yellow-crowned Parakeet",
    "Callaeas wilsoni": "North Island Kokako", "Apteryx mantelli": "North Island Brown Kiwi",
    "Vanellus miles": "Masked Lapwing", "Haematopus unicolor": "Variable Oystercatcher",
    "Morus serrator": "Australasian Gannet", "Numenius phaeopus": "Whimbrel",
    "Botaurus poiciloptilus": "Australasian Bittern", "Spatula rhynchotis": "Australasian Shoveler",
    "Poliocephalus rufopectus": "New Zealand Grebe", "Platalea regia": "Royal Spoonbill",
    "Anarhynchus frontalis": "Wrybill", "Phalacrocorax varius": "Pied Cormorant",
    "Microcarbo melanoleucos": "Little Pied Cormorant", "Phalacrocorax sulcirostris": "Little Black Cormorant",
}

# Birds that can't fly get a different second pose instead of flight.
FLIGHTLESS = {"Apteryx mantelli", "Apteryx australis", "Apteryx owenii", "Apteryx haastii", "Apteryx rowi",
              "Gallirallus australis", "Strigops habroptilus", "Porphyrio hochstetteri",
              "Anas aucklandica", "Anas nesiotis", "Apteryx maxima",
              "Struthio camelus", "Dromaius novaehollandiae"}
PENGUIN_GENERA = {"Eudyptula", "Megadyptes", "Eudyptes", "Aptenodytes", "Pygoscelis", "Spheniscus"}
WALK = dict(pose="walking", rule="Walking: wings small or not visible, mid-stride, foraging; "
            "ignore the 'two wings' rule's flight implications for this flightless bird.")
SWIM = dict(pose="swimming", rule="Swimming underwater, side view, flippers extended, streamlined body; "
            "NO water drawn, the cream ground is the only background. A penguin has two flippers, not wings.")


def second_pose(sci):
    if sci.split()[0] in PENGUIN_GENERA:
        return SWIM
    if sci in FLIGHTLESS:
        return WALK
    return None


STYLE_NOTE = ("\n\nReference images are attached. {notes}"
              "Produce ONE new image of ONE bird on its own 1:1 canvas.")


def slug(sci: str) -> str:
    return re.sub(r"[^a-z]+", "-", sci.lower()).strip("-")


def is_species(sci: str) -> bool:
    # skip "sp.", hybrids, slashes and subspecies
    return bool(re.fullmatch(r"[A-Z][a-z]+ [a-z\-]+", sci.strip()))


def ebird_get(path, key, **params):
    r = requests.get(f"{EBIRD}{path}", headers={"X-eBirdApiToken": key}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def species_nearby(key, dist, days):
    obs = ebird_get("/data/obs/geo/recent", key, lat=HOME_LAT, lng=HOME_LNG, dist=dist, back=days)
    out = {}
    for o in obs:
        if is_species(o.get("sciName", "")):
            out[o["sciName"]] = o["comName"]
    return out


def species_region(key, region):
    codes = ebird_get(f"/product/spplist/{region}", key)
    out = {}
    for i in range(0, len(codes), 100):
        tax = ebird_get("/ref/taxonomy/ebird", key, species=",".join(codes[i:i + 100]), fmt="json")
        for t in tax:
            if t.get("category") == "species" and is_species(t.get("sciName", "")):
                out[t["sciName"]] = t["comName"]
    return out


def img_part(path):
    data = Path(path).read_bytes()
    mime = {".png": "image/png", ".webp": "image/webp"}.get(Path(path).suffix.lower(), "image/jpeg")
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}


def paint(gkey, model, com, sci, pose_kw, style_ref=None, photo_ref=None, tries=3):
    text = PROMPT.format(com=com, sci=sci, **pose_kw)
    parts, notes, n = [], "", 1
    if style_ref:
        parts.append(img_part(style_ref))
        notes += (f"Image {n} is the STYLE reference: match its style, line weight, palette, level of detail "
                  f"and cream ground exactly, but do NOT copy its species. ")
        n += 1
    if photo_ref:
        parts.append(img_part(photo_ref))
        notes += f"Image {n} is a photo of a real {com}: use it ONLY for this bird's shape, colours and markings. "
    if parts:
        text += STYLE_NOTE.format(notes=notes)
    body = {
        "contents": [{"parts": [{"text": text}] + parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}},
    }
    for attempt in range(1, tries + 1):
        r = requests.post(GEMINI.format(model=model), headers={"x-goog-api-key": gkey},
                          json=body, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except Exception:
                msg = r.text[:300]
            if r.status_code == 429 and ("limit: 0" in msg or "billing" in msg.lower()):
                sys.exit(f"\nGemini says this key has no image quota:\n  {msg[:400]}\n"
                         "Enable billing for this key's project in AI Studio, then run again.")
            wait = 20 * attempt
            print(f"    server busy ({r.status_code}): {msg[:160]}")
            print(f"    retrying in {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        for cand in r.json().get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                data = part.get("inlineData") or part.get("inline_data")
                if data and data.get("data"):
                    return base64.b64decode(data["data"])
        print("    no image returned, retrying")
    return None


def cutout(png_bytes, remover):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    cut = remover(img)
    box = cut.getbbox()
    if box:
        pad = 12
        cut = cut.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                        min(box[2] + pad, cut.width), min(box[3] + pad, cut.height)))
    cut.thumbnail((512, 512))
    return cut


# ---------------------------------------------------------------- PROGRESS
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>NZ Bird Master Index</title>
<style>
:root{--paper:#efebe1;--ink:#141414;--mute:#6b665c;--line:#d6d0c2;--ok:#2f6b3a;--part:#a8741a;--miss:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Georgia,'Times New Roman',serif}
header{position:sticky;top:0;background:var(--paper);border-bottom:3px solid var(--ink);padding:16px 20px 12px;z-index:2}
h1{margin:0;font-size:26px}.sub{font:12px 'Courier New',monospace;color:var(--mute);letter-spacing:.06em;text-transform:uppercase;margin-top:4px}
.bar{height:10px;background:repeating-linear-gradient(90deg,rgba(0,0,0,.12) 0 2px,transparent 2px 4px);margin:10px 0 8px}
.bar i{display:block;height:100%;background:var(--ink)}
.tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button,input{font:13px 'Courier New',monospace;border:1px solid var(--ink);background:transparent;padding:5px 10px;color:var(--ink)}
button.on{background:var(--ink);color:var(--paper)}input{flex:1;min-width:160px}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;padding:16px 20px 40px}
.c{border:1px solid var(--line);background:#f6f3ea;padding:10px;display:flex;flex-direction:column;gap:6px}
.imgs{display:flex;gap:4px;height:84px;align-items:center;justify-content:center}
.imgs img{max-height:84px;max-width:50%;object-fit:contain;mix-blend-mode:multiply}
.ph{width:60px;height:60px;border:1px dashed var(--line)}
.n{font-weight:700;font-size:15px;line-height:1.15}.s{font-style:italic;font-size:12px;color:var(--mute)}
.chips{display:flex;gap:4px;flex-wrap:wrap}.chips span{font:10px 'Courier New',monospace;border:1px solid currentColor;padding:1px 5px;text-transform:uppercase}
.ok{color:var(--ok)}.part{color:var(--part)}.miss{color:var(--miss)}
</style></head><body><header><h1>NZ Bird Master Index</h1>
<div class="sub">__DONE__ of __TOTAL__ species complete &middot; __PART__ partial &middot; __MISS__ not started &middot; __IMGS__ images &middot; updated __WHEN__</div>
<div class="bar"><i style="width:__PCT__%"></i></div>
<div class="tools"><button class="on" data-f="all">All</button><button data-f="ok">Complete</button>
<button data-f="part">Partial</button><button data-f="miss">Missing</button><input id="q" placeholder="Search name..."></div></header>
<main id="g"></main><script>
const D=__DATA__;const g=document.getElementById('g');let f='all',q='';
function draw(){g.innerHTML=D.filter(b=>(f==='all'||b.status===f)&&(b.com+' '+b.sci).toLowerCase().includes(q)).map(b=>`
<div class="c"><div class="imgs">${b.webp.length?b.webp.slice(0,3).map(w=>`<img src="${w}" alt="">`).join(''):'<div class="ph"></div>'}</div>
<div class="n">${b.com}</div><div class="s">${b.sci}</div><div class="chips">
<span class="${b.perched?'ok':'miss'}">perched</span><span class="${b.second?'ok':'miss'}">${b.pose2}</span>
${b.extra?`<span class="ok">+${b.extra}</span>`:''}${b.uncut?`<span class="part">${b.uncut} uncut</span>`:''}</div></div>`).join('')}
document.querySelectorAll('button').forEach(x=>x.onclick=()=>{document.querySelectorAll('button').forEach(y=>y.classList.remove('on'));x.classList.add('on');f=x.dataset.f;draw()});
document.getElementById('q').oninput=e=>{q=e.target.value.toLowerCase();draw()};draw();
</script></body></html>"""


def build_progress(birds, out, raw):
    import csv, datetime
    rows = []
    for sci, com in sorted(birds.items(), key=lambda kv: kv[1]):
        s = slug(sci)
        def raw_has(suffix):
            return any((raw / f"{s}{x}.png").exists() for x in (suffix, suffix.lstrip("-")))
        webps = [p.name for p in sorted(out.glob(f"{s}*.webp")) if re.fullmatch(rf"{re.escape(s)}(-[2-9])?\.webp", p.name)]
        perched = (out / f"{s}.webp").exists()
        second = (out / f"{s}-2.webp").exists()
        extra = max(0, len(webps) - int(perched) - int(second))
        uncut = sum(1 for suf in ["", "-2", "-3", "-4"] if raw_has(suf) and not (out / f"{s}{suf}.webp").exists())
        sp = second_pose(sci)
        status = "ok" if perched and second else ("part" if perched or second or uncut else "miss")
        rows.append(dict(com=com, sci=sci, slug=s, perched=perched, second=second,
                         pose2=(sp["pose"] if sp else "in-flight"), extra=extra, uncut=uncut,
                         status=status, webp=webps))
    with open(out / "master_index.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Common name", "Scientific name", "File name", "Perched", "Second pose", "Second pose type",
                    "Extra poses", "Raw not yet cut out", "Status"])
        for r in rows:
            w.writerow([r["com"], r["sci"], r["slug"], "yes" if r["perched"] else "",
                        "yes" if r["second"] else "", r["pose2"], r["extra"] or "", r["uncut"] or "",
                        {"ok": "Complete", "part": "Partial", "miss": "Missing"}[r["status"]]])
    n = len(rows); done = sum(r["status"] == "ok" for r in rows)
    part = sum(r["status"] == "part" for r in rows); miss = n - done - part
    imgs = sum(len(r["webp"]) for r in rows)
    page = (PAGE.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__DONE__", str(done)).replace("__TOTAL__", str(n)).replace("__PART__", str(part))
            .replace("__MISS__", str(miss)).replace("__IMGS__", str(imgs))
            .replace("__PCT__", f"{done / n * 100 if n else 0:.1f}")
            .replace("__WHEN__", datetime.datetime.now().strftime("%d %b %Y %H:%M")))
    (out / "master_index.html").write_text(page, encoding="utf-8")
    print(f"\n{done}/{n} complete, {part} partial, {miss} not started, {imgs} images.")
    print(f"Wrote {out / 'master_index.csv'} and {out / 'master_index.html'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", help="eBird region code instead of 'near home', e.g. NZ-WKO")
    ap.add_argument("--dist", type=int, default=25, help="km radius for near-home list (max 50)")
    ap.add_argument("--days", type=int, default=30, help="days back for near-home list (max 30)")
    ap.add_argument("--species", action="append", help="only these common names (repeatable)")
    ap.add_argument("--limit", type=int, help="stop after this many new paintings")
    ap.add_argument("--force", action="store_true", help="repaint even if a file exists")
    ap.add_argument("--model", default="gemini-nano-banana-2.1")
    ap.add_argument("--style-ref", help="image whose style every bird should match (e.g. your best tui)")
    ap.add_argument("--refs", default=None, help="folder of species photos named <slug>.jpg/png (default: birds/refs)")
    ap.add_argument("--from-prompts", action="store_true", help="use the species in nz_bird_prompts.txt instead of eBird")
    ap.add_argument("--out", default="birds")
    ap.add_argument("--list-only", action="store_true", help="just print the species list")
    ap.add_argument("--progress", action="store_true",
                    help="write birds/master_index.csv + .html for the whole-NZ list (default region NZ)")
    ap.add_argument("--cutout-only", action="store_true",
                    help="no API calls: cut out every image already saved in birds/raw/")
    a = ap.parse_args()

    if a.cutout_only:
        from rembg import remove, new_session
        session = new_session("u2net")
        out, raw = Path(a.out), Path(a.out) / "raw"
        files = [p for p in sorted(raw.glob("*")) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        if not files:
            sys.exit(f"No images found in {raw.resolve()}")
        n = 0
        for p in files:
            # accept "name2.png" / "name-2.png" / "name_3.png" -> "name-2.webp" / "name-3.webp"
            m = re.fullmatch(r"(.*?)[-_]?([2-9])", p.stem)
            stem = f"{m.group(1)}-{m.group(2)}" if m else p.stem
            target = out / f"{stem}.webp"
            # redo if forced, missing, or the PNG was replaced after the last cut-out
            if target.exists() and not a.force and target.stat().st_mtime >= p.stat().st_mtime:
                continue
            print(f"  cutting out {p.name} -> {target.name}")
            cutout(p.read_bytes(), lambda im: remove(im, session=session)).save(target, "WEBP", quality=88)
            n += 1
        print(f"\nCut out {n} image(s). Copy the .webp files from '{out}' to HA: config/www/birds/")
        return

    keyfile = Path(__file__).with_name("bird_keys.txt")
    if keyfile.exists():
        for line in keyfile.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() in ("GEMINI_API_KEY", "EBIRD_API_KEY") and v.strip() \
                    and "paste-your" not in v:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    ekey, gkey = os.environ.get("EBIRD_API_KEY"), os.environ.get("GEMINI_API_KEY")
    if a.progress:
        region = a.region or "NZ"
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        cache = out / f"master_list_{region}.json"
        if cache.exists():
            master = json.loads(cache.read_text(encoding="utf-8"))
        else:
            if not ekey:
                sys.exit("No eBird key: add EBIRD_API_KEY=... to bird_keys.txt next to this script.")
            master = species_region(ekey, region)
            cache.write_text(json.dumps(master, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"Saved the {region} master list ({len(master)} species) to {cache}")
        # include anything you've painted that isn't on eBird's list (e.g. Whimbrel/Morepork variants)
        if (out / "index.json").exists():
            for v in json.loads((out / "index.json").read_text(encoding="utf-8")).values():
                master.setdefault(v["sci"], v["com"])
        build_progress(master, out, out / "raw")
        return
    if not gkey and not a.list_only:
        sys.exit("No Gemini key: add GEMINI_API_KEY=... to bird_keys.txt next to this script.")

    if a.from_prompts:
        birds = {}
        pf = Path("nz_bird_prompts.txt")
        if pf.exists():
            txt = pf.read_text(encoding="utf-8")
            for m in re.finditer(r"(?:Generate an? [a-z\-]+ |^An? )(.+?) \(([A-Z][a-z]+ [a-z\-]+)\)", txt, re.M):
                birds[m.group(2)] = m.group(1)
        if not birds:
            print("(no usable nz_bird_prompts.txt here, using the built-in NZ list)")
            birds = dict(NZ_BIRDS)
    else:
        birds = {}
        cache = Path(a.out) / "index.json"
        if a.species and cache.exists():
            # Redoing named birds: use the list saved by the last run, no eBird call needed.
            known = {v["sci"]: v["com"] for v in json.loads(cache.read_text(encoding="utf-8")).values()}
            known.update({k: v for k, v in NZ_BIRDS.items() if k not in known})
            want = {x.lower() for x in a.species}
            birds = {sc: c for sc, c in known.items() if c.lower() in want}
        if not birds:
            if not ekey:
                sys.exit("No eBird key: add EBIRD_API_KEY=... to bird_keys.txt next to this script.")
            try:
                birds = species_region(ekey, a.region) if a.region else species_nearby(ekey, a.dist, a.days)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                sys.exit(f"eBird refused the request ({code}). Check EBIRD_API_KEY in bird_keys.txt "
                         f"(no quotes or spaces, and not the placeholder text).")
    if a.species:
        want = {s.lower() for s in a.species}
        birds = {s: c for s, c in birds.items() if c.lower() in want}
    birds = dict(sorted(birds.items(), key=lambda kv: kv[1]))
    print(f"{len(birds)} species")
    if a.list_only:
        for s, c in birds.items():
            print(f"  {c:32s} {s}")

    out0, raw0 = Path(a.out), Path(a.out) / "raw"
    todo = sum(1 for sc in birds for suf in POSES
               if a.force or not any((raw0 / f"{slug(sc)}{x}.png").exists() for x in (suf, suf.lstrip("-"))))
    print(f"{todo} new image(s) to paint, about US${todo * 0.034:.2f} on Nano Banana 2.1")
    if a.list_only:
        return

    from rembg import remove, new_session
    session = new_session("u2net")
    remover = lambda im: remove(im, session=session)

    out, raw = Path(a.out), Path(a.out) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    done = 0
    for sci, com in birds.items():
        s = slug(sci)
        index[s] = {"com": com, "sci": sci}
        refs_dir = Path(a.refs) if a.refs else out / "refs"
        photo = next((p for p in [refs_dir / f"{s}{e}" for e in (".jpg", ".jpeg", ".png", ".webp")] if p.exists()), None)
        for suffix, kw in POSES.items():
            if suffix == "-2" and second_pose(sci):
                kw = second_pose(sci)
            target = out / f"{s}{suffix}.webp"
            # birds/raw/ is the source of truth: delete a bad PNG there to have it repainted.
            # Accepts both "name-2.png" and "name2.png".
            have = next((p for p in [raw / f"{s}{suffix}.png", raw / f"{s}{suffix.lstrip('-')}.png"]
                         if p.exists()), None)
            if have and not a.force:
                if target.exists():
                    print(f"  skip {have.name} (already done)")
                else:
                    print(f"  cutting out {have.name} (no repaint needed)")
                    cutout(have.read_bytes(), remover).save(target, "WEBP", quality=88)
                continue
            if a.limit and done >= a.limit:
                break
            print(f"  painting {com} ({kw['pose']}){' + photo ref' if photo else ''}")
            png = paint(gkey, a.model, com, sci, kw, a.style_ref, photo)
            if not png:
                print("    FAILED, skipping")
                continue
            (raw / f"{s}{suffix}.png").write_bytes(png)
            cutout(png, remover).save(target, "WEBP", quality=88)
            done += 1
            time.sleep(2)

    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"\nPainted {done} new. Review the images in '{raw}', delete any duds there and run again "
          f"(add --species \"Name\" to target one bird), then copy the .webp files from '{out}' to HA: config/www/birds/")


if __name__ == "__main__":
    main()
