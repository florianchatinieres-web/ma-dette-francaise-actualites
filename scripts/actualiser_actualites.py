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


def main():
    editorial = json.loads((ROOT / "editorial.json").read_text(encoding="utf-8"))
    if editorial.get("schemaVersion") != 1 or not editorial.get("articles"):
        raise ValueError("Catalogue éditorial invalide")
    found = {}
    successful = 0
    seen = 0
    eligible = 0
    for query in QUERIES:
        try:
            entries = load_feed(query)
            successful += 1
        except (OSError, ET.ParseError) as exc:
            print("Flux indisponible:", exc)
            continue
        seen += len(entries)
        for item in entries:
            entry = article(item)
            if entry:
                eligible += 1
                found.setdefault(entry["title"].casefold(), entry)
    print(f"Diagnostic veille : {successful}/{len(QUERIES)} flux accessibles, {seen} titres lus, {eligible} titres admissibles")
    if not successful:
        raise RuntimeError("Aucun flux accessible : conserver le fichier actuel")
    recent = sorted(found.values(), key=lambda x: dt.datetime.strptime(x["date"], "%d/%m/%Y"), reverse=True)[:MAX_AUTOMATIC]
    # Même si aucun titre n'est retenu, supprimer les anciennes fiches de veille
    # devenues hors sujet ou périmées. Les fiches éditoriales sont conservées.
    if not recent:
        print("Aucun titre de veille retenu : publication des fiches éditoriales uniquement")
    payload = {
        "schemaVersion": 1,
        "updatedAt": TODAY.date().isoformat(),
        "articles": recent + editorial["articles"],
    }
    destination = ROOT / "actualites.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Publication : {len(recent)} titres de veille + {len(editorial['articles'])} fiches éditoriales")


if __name__ == "__main__":
    main()
