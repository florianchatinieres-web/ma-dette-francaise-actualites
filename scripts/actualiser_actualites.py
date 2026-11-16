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
    '"dette publique" France site:insee.fr OR site:banque-france.fr OR site:economie.gouv.fr',
    '"finances publiques" France site:vie-publique.fr OR site:budget.gouv.fr',
]
KEYWORDS = ("dette", "déficit", "budget", "finances publiques", "emprunt", "taux", "obligation", "trésor")
MAX_AUTOMATIC = 12


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
    if not any(word in title.casefold() for word in KEYWORDS):
        return None
    if not re.search(r"France|français|publique|État|INSEE|Banque de France|Bercy", title, re.I):
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
    for query in QUERIES:
        try:
            entries = load_feed(query)
            successful += 1
        except (OSError, ET.ParseError) as exc:
            print("Flux indisponible:", exc)
            continue
        for item in entries:
            entry = article(item)
            if entry:
                found.setdefault(entry["title"].casefold(), entry)
    if not successful:
        raise RuntimeError("Aucun flux accessible : conserver le fichier actuel")
    recent = sorted(found.values(), key=lambda x: dt.datetime.strptime(x["date"], "%d/%m/%Y"), reverse=True)[:MAX_AUTOMATIC]
    # Ne pas écraser les fiches éditoriales en cas d'échec ou de flux vide.
    if not recent:
        print("Aucune actualité récente pertinente : catalogue inchangé")
        return
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
