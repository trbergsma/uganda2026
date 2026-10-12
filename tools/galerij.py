#!/usr/bin/env python3
"""Bouwt de fotogalerij van een bestemming op in Uganda2026.html.

Gebruik:
    python3 tools/galerij.py bwindi     één bestemming (mapnaam onder fotos/)
    python3 tools/galerij.py alles      alle bestemmingen die al een galerij hebben

Wat het doet:
  - zet .heic om naar .jpeg en .mov naar .mp4
  - verkleint foto's met een lange zijde boven 2000 px (nooit vergroten)
  - zet de foto's twee aan twee in rijen; elke foto houdt zijn eigen verhouding,
    dus er wordt niets afgesneden en liggend/staand mag door elkaar
  - vervangt het fotoblok van die bestemming in Uganda2026.html en kopieert
    het resultaat naar index.html

Volgorde: standaard op nummer in de bestandsnaam, de eerste foto wordt de
hoofdfoto (volle breedte). Wil je het anders, zet dan een volgorde.txt in de
map met één bestandsnaam per regel:
    * naam.jpeg            een * ervoor = volle breedte
    naam.jpeg | alt-tekst  optionele beschrijving
Foto's die niet in volgorde.txt staan komen achteraan, video's altijd onderaan.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "Uganda2026.html"
INDEX = ROOT / "index.html"
FOTOS = ROOT / "fotos"

MAX_ZIJDE = 2000
KWALITEIT = "80"
FOTO_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4"}

NAMEN = {
    "kampala": "Kampala",
    "fortportal": "Fort Portal",
    "queenelizabeth": "Queen Elizabeth NP",
    "bwindi": "Bwindi",
    "bunyonyi": "Lake Bunyonyi",
    "mburo": "Lake Mburo",
    "entebbe": "Entebbe",
}


def maten(pad):
    uit = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(pad)],
        capture_output=True, text=True, check=True,
    ).stdout
    b = int(re.search(r"pixelWidth: (\d+)", uit).group(1))
    h = int(re.search(r"pixelHeight: (\d+)", uit).group(1))
    return b, h


def zet_om(map_):
    """HEIC -> JPEG en MOV -> MP4, het origineel verdwijnt na een geslaagde omzetting."""
    for pad in sorted(map_.iterdir()):
        ext = pad.suffix.lower()
        if ext == ".heic":
            doel = pad.with_suffix(".jpeg")
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(pad), "--out", str(doel)],
                capture_output=True, check=True,
            )
            pad.unlink()
            print(f"  omgezet naar jpeg: {doel.name}")
        elif ext == ".mov":
            doel = pad.with_suffix(".mp4")
            res = subprocess.run(
                ["avconvert", "--source", str(pad), "--preset", "Preset1280x720",
                 "--output", str(doel), "--replace"],
                capture_output=True, text=True,
            )
            if res.returncode == 0 and doel.exists():
                pad.unlink()
                print(f"  omgezet naar mp4: {doel.name}")
            else:
                print(f"  LET OP: {pad.name} kon niet naar mp4, zet hem zelf om via QuickTime")


def verklein(pad):
    b, h = maten(pad)
    if max(b, h) <= MAX_ZIJDE:
        return b, h
    tmp = pad.with_name(pad.name + ".tmp")
    voor = pad.stat().st_size
    subprocess.run(
        ["sips", "-Z", str(MAX_ZIJDE), "-s", "formatOptions", KWALITEIT,
         str(pad), "--out", str(tmp)],
        capture_output=True, check=True,
    )
    tmp.replace(pad)
    print(f"  verkleind: {pad.name} ({voor // 1024} KB -> {pad.stat().st_size // 1024} KB)")
    return maten(pad)


def natuurlijk(naam):
    return [int(d) if d.isdigit() else d.lower() for d in re.split(r"(\d+)", naam)]


def lees_volgorde(map_):
    """Geeft [(naam, breed, alt)] uit volgorde.txt, of None als die er niet is."""
    pad = map_ / "volgorde.txt"
    if not pad.exists():
        return None
    regels = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        regel = regel.strip()
        if not regel or regel.startswith("#"):
            continue
        breed = regel.startswith("*")
        if breed:
            regel = regel[1:].strip()
        naam, _, alt = (deel.strip() for deel in regel.partition("|"))
        regels.append((naam, breed, alt))
    return regels


def blok_grenzen(html, bestemming):
    """Begin en eind van het fotoblok van deze bestemming in de html."""
    m = re.search(
        rf"[ \t]*<!-- FOTOS:{bestemming}\b.*?-->.*?<!-- /FOTOS:{bestemming} -->",
        html, re.S,
    )
    if m:
        return m.start(), m.end()
    # Nog geen markers: zoek het bestaande fotoblok binnen de sectie.
    sectie = re.search(rf'<section[^>]*id="{bestemming}"', html)
    if not sectie:
        sys.exit(f"Geen sectie met id '{bestemming}' gevonden in {HTML.name}")
    volgende = html.find("<section", sectie.end())
    start = html.find('<div class="fotos-sectie', sectie.end(), volgende if volgende != -1 else len(html))
    if start == -1:
        sys.exit(f"Geen fotoblok gevonden in sectie '{bestemming}'")
    diepte = 0
    for tag in re.finditer(r"<div\b|</div>", html[start:]):
        diepte += 1 if tag.group() != "</div>" else -1
        if diepte == 0:
            eind = start + tag.end()
            break
    regel_start = html.rfind("\n", 0, start) + 1
    return regel_start, eind


def verzamel(bestemming, html, grenzen):
    """Alle foto's en video's van de map, in de juiste volgorde."""
    map_ = FOTOS / bestemming
    # Tegelfoto's (park.jpg e.d.) staan elders in de pagina en horen niet in de galerij.
    buiten = html[:grenzen[0]] + html[grenzen[1]:]
    elders = {unquote(n) for n in re.findall(rf'fotos/{bestemming}/([^"\')]+)', buiten)}

    aanwezig = {p.name for p in map_.iterdir() if p.suffix.lower() in FOTO_EXT | VIDEO_EXT}
    volgorde = lees_volgorde(map_) or []
    for naam, _, _ in volgorde:
        if naam not in aanwezig:
            print(f"  LET OP: {naam} staat in volgorde.txt maar niet in de map, overgeslagen")
    volgorde = [v for v in volgorde if v[0] in aanwezig]
    genoemd = {v[0] for v in volgorde}
    rest = sorted(aanwezig - genoemd - elders, key=natuurlijk)
    alles = volgorde + [(naam, False, "") for naam in rest]

    fotos = [v for v in alles if Path(v[0]).suffix.lower() in FOTO_EXT]
    videos = [v[0] for v in alles if Path(v[0]).suffix.lower() in VIDEO_EXT]
    if fotos and not lees_volgorde(map_):
        fotos[0] = (fotos[0][0], True, fotos[0][2])
    return fotos, videos


def bouw_blok(bestemming, fotos, videos):
    map_ = FOTOS / bestemming
    standaard_alt = f"{NAMEN.get(bestemming, bestemming)} Uganda 2026"
    regels = [
        f"    <!-- FOTOS:{bestemming} (gemaakt door tools/galerij.py, niet met de hand aanpassen) -->",
        '    <div class="fotos-sectie">',
        '      <p class="eyebrow fade">Foto\'s</p>',
    ]

    def slot(naam, alt):
        b, h = verklein(map_ / naam)
        src = f"fotos/{bestemming}/{quote(naam)}"
        alt = (alt or standaard_alt).replace('"', "&quot;")
        return (f'        <div class="foto-slot" style="--r:{b / h:.4f}">'
                f'<img src="{src}" alt="{alt}" loading="lazy"></div>')

    def rij(slots, klasse=""):
        regels.append(f'      <div class="foto-rij{klasse} fade">')
        regels.extend(slots)
        regels.append("      </div>")

    wachtend = []
    for naam, breed, alt in fotos:
        if breed:
            if wachtend:
                rij(wachtend, " enkel")
                wachtend = []
            s = slot(naam, alt)
            # Een staande foto over de volle breedte wordt te hoog.
            staand = float(re.search(r"--r:([\d.]+)", s).group(1)) < 1
            rij([s], " enkel" if staand else " hoofd")
            continue
        wachtend.append(slot(naam, alt))
        if len(wachtend) == 2:
            rij(wachtend)
            wachtend = []
    if wachtend:
        rij(wachtend, " enkel")

    for naam in videos:
        regels += [
            '      <div class="video-slot fade">',
            "        <video controls playsinline>",
            f'          <source src="fotos/{bestemming}/{quote(naam)}" type="video/mp4">',
            "        </video>",
            "      </div>",
        ]
    regels += ["    </div>", f"    <!-- /FOTOS:{bestemming} -->"]
    return "\n".join(regels)


def bouw(bestemming):
    map_ = FOTOS / bestemming
    if not map_.is_dir():
        sys.exit(f"Map fotos/{bestemming} bestaat niet")
    print(f"{bestemming}:")
    zet_om(map_)
    html = HTML.read_text(encoding="utf-8")
    grenzen = blok_grenzen(html, bestemming)
    fotos, videos = verzamel(bestemming, html, grenzen)
    if not fotos and not videos:
        print("  geen foto's gevonden, niets aangepast")
        return
    blok = bouw_blok(bestemming, fotos, videos)
    HTML.write_text(html[:grenzen[0]] + blok + html[grenzen[1]:], encoding="utf-8")
    print(f"  {len(fotos)} foto's, {len(videos)} video's")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    doel = sys.argv[1]
    if doel == "alles":
        html = HTML.read_text(encoding="utf-8")
        doelen = re.findall(r"<!-- FOTOS:(\w+)", html)
    else:
        doelen = [doel]
    for bestemming in doelen:
        bouw(bestemming)
    shutil.copyfile(HTML, INDEX)
    print("index.html bijgewerkt")


if __name__ == "__main__":
    main()
