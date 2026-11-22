#!/usr/bin/env python3
"""Veille informative : titres sourcés, sans résumé factuel inventé."""
import datetime as dt
import email.utils
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.datetime.now(dt.timezone.utc)
QUERIES = [
    '"dette publique" France',
    '"déficit public" France',
    '"budget de l’État" France',
    '"taux emprunt" dette France',
]
KEYWORDS = ("dette", "déficit", "budget", "finances publiques", "emprunt", "taux", "obligation", "trésor")
MAX_AUTOMATIC = 12
# Liste éditoriale de sources institutionnelles et de médias d'information.
# La sélection n'implique pas une validation de chaque article.
ALLOWED_SOURCES = (
    "insee", "banque de france", "vie publique", "vie-publique",
    "ministère de l'économie", "economie.gouv", "budget.gouv",
    "cour des comptes", "agence france-presse", "afp",
    "franceinfo", "france info", "france 24", "france inter",
    "le monde", "le figaro", "les echos", "les échos",
    "la tribune", "le parisien", "ouest-france", "ouest france",
    "public sénat", "france télévision", "france télévisions",
)
FRANCE_TERMS = (
    "france", "français", "française", "françaises", "française",
    "budget 2027", "budget 2026", "état français",
    "assemblée nationale", "sénat", "bercy", "cour des comptes",
    "dette publique française",
)
FOREIGN_FOCUS = ("en allemagne", "en bulgarie", "au portugal", "en grèce",
                 "en italie", "en espagne", "aux états-unis", "au royaume-uni")


def load_feed(query):
    params = urllib.parse.urlencode({"q": query, "hl": "fr", "gl": "FR", "ceid": "FR:fr"})
    req = urllib.request.Request(
        "https://news.google.com/rss/search?" + params,
        headers={"User-Agent": "MaDetteFrancaise-NewsFeed/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(2_000_000)
    return ET.fromstring(data).findall("./channel/item")


def article(item):
    title = " ".join((item.findtext("title") or "").split())
    link = (item.findtext("link") or "").strip()
    source = (item.findtext("source") or "Actualités").strip()
    published = item.findtext("pubDate") or ""
    try:
        date = email.utils.parsedate_to_datetime(published).astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return None
    if not title or not link.startswith("https://") or len(title) > 220:
        return None
    if (TODAY - date).days > 7 or date > TODAY + dt.timedelta(days=1):
        return None
    # Google Actualités ajoute souvent « - Nom du média » au titre.
    # Ne pas prendre « Ouest-France » pour une mention de la France dans l'article.
    subject_title = title.rsplit(" - ", 1)[0]
    normalized_title = subject_title.casefold()
    normalized_source = source.casefold()
    if not any(word in normalized_title for word in KEYWORDS):
        return None
    if not any(name in normalized_source for name in ALLOWED_SOURCES):
        return None
    if not any(term in normalized_title for term in FRANCE_TERMS):
        return None
    if any(term in normalized_title for term in FOREIGN_FOCUS):
        return None
    return {
        "date": date.strftime("%d/%m/%Y"),
        "tag": "Veille automatique",
        "title": title,
        "short": "Publication repérée dans la veille des finances publiques. Consultez la source originale pour les faits et les chiffres.",
        "simple": "Cette fiche signale une publication récente. Son contenu n'a pas été résumé ni vérifié individuellement par la rédaction.",
        "pro": "La veille est automatisée à partir d'un flux de référencement. Le titre et le lien ne constituent pas une validation indépendante des informations publiées.",
        "why": "À consulter pour suivre les publications récentes sur la dette, le budget et les finances publiques.",
        "source": source[:100],
        "url": link,
    }


# Les articles acceptés sont conservés ; seules les nouvelles entrées sont filtrées.
# Un article passe en archive après 365 jours. Les archives ne sont pas chargées
# par l'application actuelle : elle continue de lire actualites.json (schemaVersion 1).
ARCHIVE_DAYS = 365
MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def read_catalogue(path):
    if not path.exists():
        return {"schemaVersion": 1, "articles": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("articles"), list):
        raise ValueError(f"Catalogue invalide : {path}")
    return data


def article_date(value):
    value = str(value).strip().casefold()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    match = re.fullmatch(r"(\d{1,2})\s+([a-zéûèêôîàù]+)\s+(\d{4})", value)
    if match and match.group(2) in MONTHS:
        try:
            return dt.date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
        except ValueError:
            pass
    # Ne jamais supprimer un article dont la date n'est pas interprétable.
    return None


def article_key(entry):
    url = str(entry.get("url") or "").strip()
    if url:
        return ("url", url)
    return ("title", str(entry.get("title") or "").strip().casefold())


def merge(*groups):
    items = {}
    for group in groups:
        for entry in group:
            if isinstance(entry, dict) and entry.get("title"):
                items.setdefault(article_key(entry), entry)
    return list(items.values())


def sort_articles(entries):
    return sorted(entries, key=lambda e: article_date(e.get("date", "")) or dt.date.min, reverse=True)


def main():
    editorial = read_catalogue(ROOT / "editorial.json")
    if not editorial["articles"]:
        raise ValueError("Catalogue éditorial vide")
    destination = ROOT / "actualites.json"
    archive_path = ROOT / "archives.json"
    previous = read_catalogue(destination)
    archived = read_catalogue(archive_path)

    # Les articles éditoriaux ne sont plus protégés contre le vieillissement.
    # L'historique existant a priorité, puis les archives et les fiches éditoriales.
    known = merge(previous["articles"], archived["articles"], editorial["articles"])
    keys = {article_key(entry) for entry in known}
    new_entries = []
    successful = seen = eligible = 0
    for query in QUERIES:
        try:
            entries = load_feed(query)
            successful += 1
        except (OSError, ET.ParseError) as exc:
            print("Flux indisponible:", exc)
            continue
        seen += len(entries)
        for item in entries:
            # Le filtre de pertinence ne s'applique qu'aux nouveaux articles.
            raw_link = (item.findtext("link") or "").strip()
            raw_title = " ".join((item.findtext("title") or "").split())
            if ("url", raw_link) in keys or ("title", raw_title.casefold()) in keys:
                continue
            entry = article(item)
            if entry:
                eligible += 1
                key = article_key(entry)
                if key not in keys:
                    keys.add(key)
                    new_entries.append(entry)
    if not successful:
        # Ne jamais effacer l'historique à cause d'une panne des sources.
        raise RuntimeError("Aucun flux accessible : conserver les fichiers actuels")
    all_entries = merge(known, new_entries)
    current, archives = [], []
    for entry in all_entries:
        published = article_date(entry.get("date", ""))
        if published is not None and (TODAY.date() - published).days > ARCHIVE_DAYS:
            archives.append(entry)
        else:
            current.append(entry)
    current, archives = sort_articles(current), sort_articles(archives)
    # Le format de l'API actuelle reste inchangé pour les applications installées.
    payload = {"schemaVersion": 1, "updatedAt": TODAY.date().isoformat(), "articles": current}
    archive_payload = {"schemaVersion": 1, "updatedAt": TODAY.date().isoformat(), "articles": archives}
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Veille : {successful}/{len(QUERIES)} flux, {seen} titres, {eligible} candidats ; "
          f"{len(new_entries)} nouveaux, {len(current)} actifs, {len(archives)} archivés")


if __name__ == "__main__":
    main()
