#!/usr/bin/env python3
"""Bouwt de fotogalerij van een bestemming op in Uganda2026.html.

Gebruik:
    python3 tools/galerij.py bwindi     één bestemming (mapnaam onder fotos/)
    python3 tools/galerij.py alles      alle bestemmingen die al een galerij hebben

Wat het doet:
  - zet .heic om naar .jpeg en .mov naar .mp4, en maakt bij elk filmpje een
    voorbeeldbeeld (poster) zodat het niet als leeg vlak verschijnt
  - verkleint foto's met een lange zijde boven 2000 px (nooit vergroten)
  - haalt de GPS-locatie en de namen van herkende personen uit de foto's; de
    locatie komt in locaties.tsv in de map,
    dat bestand blijft op deze laptop en gaat niet mee naar GitHub
  - zet de foto's in rijen van ongeveer gelijke hoogte: twee liggende of drie
    staande naast elkaar, zodat staande foto's niet groter uitvallen dan
    liggende; elke foto houdt zijn eigen verhouding, er wordt niets afgesneden
  - vervangt het fotoblok van die bestemming in Uganda2026.html en kopieert
    het resultaat naar index.html

Volgorde: standaard op opnamemoment, zodat de foto's het verhaal volgen.
Foto nummer 1 wordt de hoofdfoto (volle breedte); is die staand, dan wordt
de eerste liggende foto de hoofdfoto. Wil je het anders, zet dan een
volgorde.txt in de map met één bestandsnaam per regel:
    * naam.jpeg                          een * ervoor = volle breedte
    - naam.jpeg                          een - ervoor = niet tonen
    + naam.mp4                           een + ervoor = filmpje naast het vorige
    naam.jpeg | alt-tekst | onderschrift  optioneel, onderschrift onder de foto
Foto's die niet in volgorde.txt staan komen achteraan op opnamemoment,
video's altijd onderaan. Filmpjes naast elkaar krijgen dezelfde hoogte.
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
# Een rij is vol zodra de verhoudingen (breedte/hoogte) samen RIJ_VOL halen:
# twee liggende (2 x 1,33) of drie staande (3 x 0,75). Een rij die dat niet
# haalt wordt niet opgerekt maar smaller gezet, alsof de som RIJ_REF was.
RIJ_VOL = 1.9
RIJ_REF = 2.5
FOTO_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".mp4"}

NAMEN = {
    "kampala": "Kampala",
    "fortportal": "Fort Portal",
    "queenelizabeth": "Queen Elizabeth NP",
    "onderweg": "Onderweg naar Bwindi",
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


def video_maten(pad):
    """Breedte en hoogte van een video via Spotlight, of None als die onbekend zijn."""
    waarden = []
    for sleutel in ("kMDItemPixelWidth", "kMDItemPixelHeight"):
        uit = subprocess.run(["mdls", "-raw", "-name", sleutel, str(pad)],
                             capture_output=True, text=True).stdout.strip()
        if not uit.isdigit():
            return None
        waarden.append(int(uit))
    return tuple(waarden)


def opname(pad):
    """Opnamemoment uit de foto zelf (via Spotlight), of None als dat onbekend is."""
    uit = subprocess.run(["mdls", "-raw", "-name", "kMDItemContentCreationDate", str(pad)],
                         capture_output=True, text=True).stdout.strip()
    return None if not uit or uit == "(null)" else uit


def maak_posters(map_):
    """Voorbeeldbeeld per filmpje in map_/poster/, alleen als het nog ontbreekt."""
    for video in sorted(map_.glob("*.mp4")):
        poster = map_ / "poster" / (video.name + ".jpg")
        if poster.exists() and poster.stat().st_mtime >= video.stat().st_mtime:
            continue
        poster.parent.mkdir(exist_ok=True)
        subprocess.run(["qlmanage", "-t", "-s", "1280", "-o", str(poster.parent), str(video)],
                       capture_output=True)
        png = poster.parent / (video.name + ".png")
        if not png.exists():
            print(f"  LET OP: geen voorbeeldbeeld kunnen maken voor {video.name}")
            continue
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "75",
                        str(png), "--out", str(poster)], capture_output=True, check=True)
        png.unlink()
        print(f"  voorbeeldbeeld gemaakt: {poster.name}")


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
            # Een klein H.264-filmpje niet opblazen naar 720p: alleen in mp4 verpakken.
            maat = video_maten(pad)
            codecs = subprocess.run(["mdls", "-raw", "-name", "kMDItemCodecs", str(pad)],
                                    capture_output=True, text=True).stdout
            klein = maat and max(maat) < 1280 and "H.264" in codecs
            preset = "PresetPassthrough" if klein else "Preset1280x720"
            res = subprocess.run(
                ["avconvert", "--source", str(pad), "--preset", preset,
                 "--output", str(doel), "--replace"],
                capture_output=True, text=True,
            )
            if res.returncode == 0 and doel.exists():
                pad.unlink()
                print(f"  omgezet naar mp4: {doel.name}")
            else:
                print(f"  LET OP: {pad.name} kon niet naar mp4, zet hem zelf om via QuickTime")


def privacy(map_):
    """Haalt GPS-locatie en herkende namen uit alle foto's van de map, zodat die niet online komen.

    De locaties blijven bruikbaar bij het bouwen: ze worden bewaard in
    locaties.tsv in dezelfde map, en dat bestand gaat niet mee naar GitHub.
    """
    fotos = sorted(p for p in map_.rglob("*") if p.suffix.lower() in FOTO_EXT)
    if not fotos:
        return
    res = subprocess.run(["swift", str(ROOT / "tools" / "privacy.swift"), *map(str, fotos)],
                         capture_output=True, text=True)
    if res.stderr.strip():
        print("  " + res.stderr.strip().replace("\n", "\n  "))
    nieuw = [regel for regel in res.stdout.splitlines() if regel.count("\t") == 2]
    if not nieuw:
        return
    bestand = map_ / "locaties.tsv"
    locaties = {}
    if bestand.exists():
        for regel in bestand.read_text(encoding="utf-8").splitlines():
            locaties[regel.split("\t")[0]] = regel
    for regel in nieuw:
        locaties[regel.split("\t")[0]] = regel
    bestand.write_text("\n".join(locaties[n] for n in sorted(locaties, key=natuurlijk)) + "\n",
                       encoding="utf-8")
    print(f"  locatie verwijderd uit {len(nieuw)} foto's (bewaard in locaties.tsv)")


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
    """Geeft [(naam, breed, alt, onderschrift, verborgen, naast)] uit volgorde.txt, of None."""
    pad = map_ / "volgorde.txt"
    if not pad.exists():
        return None
    regels = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        regel = regel.strip()
        if not regel or regel.startswith("#"):
            continue
        breed = regel.startswith("*")
        verborgen = regel.startswith("-")
        naast = regel.startswith("+")
        if breed or verborgen or naast:
            regel = regel[1:].strip()
        delen = [deel.strip() for deel in regel.split("|")] + ["", ""]
        regels.append((delen[0], breed, delen[1], delen[2], verborgen, naast))
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
    eigen = lees_volgorde(map_)
    volgorde = eigen or []
    for v in volgorde:
        if v[0] not in aanwezig:
            print(f"  LET OP: {v[0]} staat in volgorde.txt maar niet in de map, overgeslagen")
    volgorde = [v for v in volgorde if v[0] in aanwezig]
    genoemd = {v[0] for v in volgorde}
    rest = sorted(aanwezig - genoemd - elders,
                  key=lambda n: (opname(map_ / n) or "9999", natuurlijk(n)))
    alles = [v for v in volgorde if not v[4]] + [(naam, False, "", "", False, False) for naam in rest]

    fotos = [v[:4] for v in alles if Path(v[0]).suffix.lower() in FOTO_EXT]
    videos = [(v[0], v[5]) for v in alles if Path(v[0]).suffix.lower() in VIDEO_EXT]
    if fotos and eigen is None:
        # Foto nummer 1 wordt de hoofdfoto, tenzij die staand is: dan de eerste liggende.
        kandidaten = sorted(fotos, key=lambda f: natuurlijk(f[0]))
        hoofd = kandidaten[0]
        b, h = maten(map_ / hoofd[0])
        if b < h:
            liggend = [f for f in fotos if (lambda m: m[0] >= m[1])(maten(map_ / f[0]))]
            if liggend:
                hoofd = liggend[0]
                print(f"  {kandidaten[0][0]} is staand, hoofdfoto wordt {hoofd[0]}")
        fotos.remove(hoofd)
        fotos.insert(0, (hoofd[0], True, hoofd[2], hoofd[3]))
    return fotos, videos


def verdeel(fotos):
    """Verdeelt foto's (naam, breed, alt, onderschrift, verhouding) over rijen.

    Geeft [(groep, hoofd, breedte)]: hoofd = foto over de volle breedte,
    breedte = deel van de paginabreedte dat de rij inneemt.
    """
    rijen, groep = [], []
    for foto in fotos:
        if foto[1]:
            if groep:
                rijen.append((groep, False))
                groep = []
            rijen.append(([foto], True))
            continue
        groep.append(foto)
        if sum(f[4] for f in groep) >= RIJ_VOL:
            rijen.append((groep, False))
            groep = []
    if groep:
        rijen.append((groep, False))

    # Eén losse foto na een rij van drie of meer: verdeel ze liever gelijk.
    for i in range(1, len(rijen)):
        (vorige, hoofd_v), (deze, hoofd_d) = rijen[i - 1], rijen[i]
        if hoofd_v or hoofd_d or len(deze) != 1 or len(vorige) < 3:
            continue
        if sum(f[4] for f in deze) >= RIJ_VOL:
            continue
        if sum(f[4] for f in vorige[:-1]) >= 1.4:
            deze.insert(0, vorige.pop())

    uit = []
    for groep, hoofd in rijen:
        som = sum(f[4] for f in groep)
        if hoofd:
            # Een staande foto over de volle breedte wordt te hoog.
            breedte = 1.0 if som >= 1 else 0.45
        else:
            breedte = 1.0 if som >= RIJ_VOL else min(1.0, som / RIJ_REF)
        uit.append((groep, hoofd, breedte))
    return uit


def bouw_blok(bestemming, fotos, videos):
    map_ = FOTOS / bestemming
    standaard_alt = f"{NAMEN.get(bestemming, bestemming)} Uganda 2026"
    regels = [
        f"    <!-- FOTOS:{bestemming} (gemaakt door tools/galerij.py, niet met de hand aanpassen) -->",
        '    <div class="fotos-sectie">',
        '      <p class="eyebrow fade">Foto\'s</p>',
    ]

    def slot(foto):
        naam, _, alt, onderschrift, verhouding = foto
        src = f"fotos/{bestemming}/{quote(naam)}"
        alt = (alt or standaard_alt).replace('"', "&quot;")
        onder = f'<p class="foto-cap">{onderschrift}</p>' if onderschrift else ""
        return (f'        <div class="foto-slot" style="--r:{verhouding:.4f}">'
                f'<img src="{src}" alt="{alt}" loading="lazy">{onder}</div>')

    gemeten = []
    for naam, breed, alt, onderschrift in fotos:
        b, h = verklein(map_ / naam)
        gemeten.append((naam, breed, alt, onderschrift, b / h))

    for groep, hoofd, breedte in verdeel(gemeten):
        klasse = " hoofd" if hoofd else ""
        stijl = f' style="--b:{breedte:.3f}"' if breedte < 1 else ""
        regels.append(f'      <div class="foto-rij{klasse} fade"{stijl}>')
        regels.extend(slot(foto) for foto in groep)
        regels.append("      </div>")

    def video(naam, in_rij):
        maat = video_maten(map_ / naam)
        staand = " staand" if maat and maat[1] > maat[0] else ""
        verhouding = f' style="aspect-ratio:{maat[0]}/{maat[1]}"' if maat else ""
        poster = map_ / "poster" / (naam + ".jpg")
        # Met een voorbeeldbeeld hoeft het filmpje pas te laden als je op afspelen drukt.
        voorbeeld = (f' poster="fotos/{bestemming}/poster/{quote(poster.name)}" preload="none"'
                     if poster.exists() else "")
        # In een rij bepaalt de verhouding de breedte, zodat de filmpjes even hoog zijn.
        r = f' style="--r:{maat[0] / maat[1]:.4f}"' if in_rij and maat else ""
        inspring = "  " if in_rij else ""
        return [
            f'      {inspring}<div class="video-slot{staand}{"" if in_rij else " fade"}"{r}>',
            f"        {inspring}<video controls playsinline{voorbeeld}{verhouding}>",
            f'          {inspring}<source src="fotos/{bestemming}/{quote(naam)}" type="video/mp4">',
            f"        {inspring}</video>",
            f"      {inspring}</div>",
        ]

    # Filmpjes met een + in volgorde.txt komen naast het vorige filmpje.
    groepen = []
    for naam, naast in videos:
        if naast and groepen:
            groepen[-1].append(naam)
        else:
            groepen.append([naam])
    for groep in groepen:
        if len(groep) == 1:
            regels += video(groep[0], False)
        else:
            # Alleen staande filmpjes: rij smaller zetten, anders worden ze heel hoog.
            maten_ = [video_maten(map_ / naam) for naam in groep]
            som = sum(m[0] / m[1] for m in maten_ if m)
            alles_staand = all(m and m[1] > m[0] for m in maten_)
            klasse = " staand" if alles_staand else ""
            stijl = f' style="--b:{som / RIJ_VOL:.3f}"' if som < RIJ_VOL else ""
            regels.append(f'      <div class="video-rij{klasse} fade"{stijl}>')
            for naam in groep:
                regels += video(naam, True)
            regels.append("      </div>")
    regels += ["    </div>", f"    <!-- /FOTOS:{bestemming} -->"]
    return "\n".join(regels)


def bouw(bestemming):
    map_ = FOTOS / bestemming
    if not map_.is_dir():
        sys.exit(f"Map fotos/{bestemming} bestaat niet")
    print(f"{bestemming}:")
    zet_om(map_)
    maak_posters(map_)
    html = HTML.read_text(encoding="utf-8")
    grenzen = blok_grenzen(html, bestemming)
    fotos, videos = verzamel(bestemming, html, grenzen)
    if not fotos and not videos:
        print("  geen foto's gevonden, niets aangepast")
        return
    blok = bouw_blok(bestemming, fotos, videos)
    HTML.write_text(html[:grenzen[0]] + blok + html[grenzen[1]:], encoding="utf-8")
    print(f"  {len(fotos)} foto's, {len(videos)} video's")
    # Als laatste: de foto's zijn nu verkleind en gesorteerd, locatie en namen mogen eruit.
    privacy(map_)


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
