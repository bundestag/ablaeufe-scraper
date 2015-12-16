# -*- coding: UTF-8 -*-
import logging
import re
import requests
from lxml import etree, html
from urlparse import urljoin

from common import tbl_ablauf, tbl_beitrag, tbl_position, tbl_beschluss
from common import tbl_person, tbl_referenz, tbl_zuweisung, tbl_schlagwort

from constants import FACTION_MAPS, DIP_GREMIUM_TO_KEY
from constants import DIP_ABLAUF_STATES_FINISHED


WAHLPERIODEN = [17, 18]
EXTRAKT_INDEX = 'http://dipbt.bundestag.de/extrakt/ba/WP%s/'
INLINE_RE = re.compile(r"<!--(.*?)-->", re.M + re.S)
INLINE_COMMENTS_RE = re.compile(r"<-.*->", re.M + re.S)
END_ID = re.compile("[,\n]")

log = logging.getLogger(__name__)


def inline_xml_from_page(page, url):
    try:
        for comment in INLINE_RE.findall(page):
            comment = comment.strip()
            if comment.startswith("<?xml"):
                comment = INLINE_COMMENTS_RE.sub('', comment).split('>', 1)[-1]
                comment = comment.decode('latin-1').replace('\x0b', ' ')
                try:
                    return etree.fromstring(comment)
                except Exception, e:
                    log.error('Failed to parse XML comment on: %r', url)
                    log.exception(e)
    except Exception, e:
        log.exception(e)


def _get_dokument(hrsg, typ, nummer, link=None):
    return {
        'link': link,
        'hrsg': hrsg,
        'typ': typ,
        'nummer': nummer.lstrip("0")
    }


def dokument_by_id(hrsg, typ, nummer, link=None):
    if '/' in nummer:
        section, nummer = nummer.split("/", 1)
        nummer = nummer.lstrip("0")
        nummer = section + "/" + nummer
    return _get_dokument(hrsg, typ, nummer, link=link)


def dokument_by_url(url):
    if url is None or not url:
        return
    if '#' in url:
        url, fragment = url.split('#', 1)
    name, file_ext = url.rsplit('.', 1)
    base = name.split('/', 4)[-1].split("/")
    hrsg, typ = {
        "btd": ("BT", "drs"),
        "btp": ("BT", "plpr"),
        "brd": ("BR", "drs"),
        "brp": ("BR", "plpr")
    }.get(base[0])
    if hrsg == 'BR' and typ == 'plpr':
        nummer = base[1]
    elif hrsg == 'BR' and typ == 'drs':
        nummer = "/".join(base[-1].split("-"))
    elif hrsg == 'BT':
        s = base[1]
        nummer = base[-1][len(s):].lstrip("0")
        nummer = s + "/" + nummer
    return _get_dokument(hrsg, typ, nummer, link=url)


def dokument_by_name(name):
    if name is None or not name:
        return
    if ' - ' in name:
        date, name = name.split(" - ", 1)
    else:
        log.warn("NO DATE: %s", name)
    if ',' in name or '\n' in name:
        name, remainder = END_ID.split(name, 1)
    typ, nummer = name.strip().split(" ", 1)
    hrsg, typ = {
        "BT-Plenarprotokoll": ("BT", "plpr"),
        "BT-Drucksache": ("BT", "drs"),
        "BR-Plenarprotokoll": ("BR", "plpr"),
        "BR-Drucksache": ("BR", "drs")
    }.get(typ, ('BT', 'drs'))
    link = None
    if hrsg == 'BT' and typ == 'drs':
        f, s = nummer.split("/", 1)
        s = s.split(" ")[0]
        s = s.zfill(5)
        link = "http://dipbt.bundestag.de:80/dip21/btd/%s/%s/%s%s.pdf"
        link = link % (f, s[:3], f, s)
    return _get_dokument(hrsg, typ, nummer, link=link)


def scrape_activity(url, elem):
    urheber = elem.findtext("URHEBER")
    fundstelle = elem.findtext("FUNDSTELLE")
    p = {
        'source_url': url,
        'urheber': urheber,
        'fundstelle': fundstelle
    }
    pos_keys = p.copy()
    p['zuordnung'] = elem.findtext("ZUORDNUNG")
    p['abstrakt'] = elem.findtext("VP_ABSTRAKT")
    p['fundstelle_url'] = elem.findtext("FUNDSTELLE_LINK")

    for zelem in elem.findall("ZUWEISUNG"):
        z = pos_keys.copy()
        z['text'] = zelem.findtext("AUSSCHUSS_KLARTEXT")
        z['federfuehrung'] = zelem.find("FEDERFUEHRUNG") is not None
        z['gremium_key'] = DIP_GREMIUM_TO_KEY.get(z['text'])
        tbl_zuweisung.insert(z)

    for belem in elem.findall("BESCHLUSS"):
        b = pos_keys.copy()
        b['seite'] = belem.findtext("BESCHLUSSSEITE")
        b['dokument_text'] = belem.findtext("BEZUGSDOKUMENT")
        b['tenor'] = belem.findtext("BESCHLUSSTENOR")
        b['grundlage'] = belem.findtext("GRUNDLAGE")
        tbl_beschluss.insert(b)

    try:
        dokument = dokument_by_url(p['fundstelle_url']) or \
            dokument_by_name(p['fundstelle'])
        dokument.update(pos_keys)
        tbl_referenz.insert(dokument)
    except Exception, e:
        log.exception(e)

    for belem in elem.findall("PERSOENLICHER_URHEBER"):
        b = pos_keys.copy()
        b['vorname'] = belem.findtext("VORNAME")
        b['nachname'] = belem.findtext("NACHNAME")
        b['funktion'] = belem.findtext("FUNKTION")
        b['ort'] = belem.findtext('WAHLKREISZUSATZ')
        p = tbl_person.find_one(vorname=b['vorname'],
                                nachname=b['nachname'],
                                ort=b['ort'])
        if p is not None:
            b['person_source_url'] = p['source_url']
        b['ressort'] = belem.findtext("RESSORT")
        b['land'] = belem.findtext("BUNDESLAND")
        b['fraktion'] = FACTION_MAPS.get(belem.findtext("FRAKTION"),
                                         belem.findtext("FRAKTION"))
        b['seite'] = belem.findtext("SEITE")
        b['art'] = belem.findtext("AKTIVITAETSART")
        tbl_beitrag.insert(b)


def scrape_ablauf(url, force=False):
    key = int(url.rsplit('/', 1)[-1].split('.')[0])

    a = tbl_ablauf.find_one(source_url=url)
    if a is not None and a['abgeschlossen'] and not force:
        log.info('Skipping: %r', url)
        return

    res = requests.get(url)
    a = {
        'key': key,
        'source_url': url
    }
    doc = inline_xml_from_page(res.content, url)
    if doc is None:
        log.info('No content: %r', url)
        return

    a['wahlperiode'] = int(doc.findtext("WAHLPERIODE"))
    a['typ'] = doc.findtext("VORGANGSTYP")
    a['titel'] = doc.findtext("TITEL")

    if not a['titel'] or not len(a['titel'].strip()):
        log.info('No title: %r', url)
        return

    if '\n' in a['titel']:
        t, k = a['titel'].rsplit('\n', 1)
        k = k.strip()
        if k.startswith('KOM') or k.startswith('SEK'):
            a['titel'] = t

    a['initiative'] = doc.findtext("INITIATIVE")
    a['stand'] = doc.findtext("AKTUELLER_STAND")
    a['signatur'] = doc.findtext("SIGNATUR")
    a['gesta_id'] = doc.findtext("GESTA_ORDNUNGSNUMMER")
    a['eu_dok_nr'] = doc.findtext("EU_DOK_NR")
    a['abstrakt'] = doc.findtext("ABSTRAKT")
    a['sachgebiet'] = doc.findtext("SACHGEBIET")
    a['zustimmungsbeduerftig'] = doc.findtext("ZUSTIMMUNGSBEDUERFTIGKEIT")
    # a.schlagworte = []

    for sw in doc.findall("SCHLAGWORT"):
        wort = {'wort': sw.text, 'source_url': url}
        tbl_schlagwort.upsert(wort, ['wort', 'source_url'])

    log.info("Ablauf %s: %s", url, a['titel'])
    a['titel'] = a['titel'].strip().lstrip('.').strip()
    a['abgeschlossen'] = DIP_ABLAUF_STATES_FINISHED.get(a['stand'], False)

    if a['wahlperiode'] != max(WAHLPERIODEN):
        a['abgeschlossen'] = True

    if 'Originaltext der Frage(n):' in a['abstrakt']:
        _, a['abstrakt'] = a['abstrakt'].split('Originaltext der Frage(n):', 1)

    tbl_position.delete(source_url=url)
    tbl_beitrag.delete(source_url=url)
    tbl_zuweisung.delete(source_url=url)
    tbl_beschluss.delete(source_url=url)
    tbl_referenz.delete(source_url=url)

    for elem in doc.findall(".//VORGANGSPOSITION"):
        scrape_activity(url, elem)

    for elem in doc.findall("WICHTIGE_DRUCKSACHE"):
        link = elem.findtext("DRS_LINK")
        hash = None
        if link is not None and '#' in link:
            link, hash = link.rsplit('#', 1)
        dokument = dokument_by_id(elem.findtext("DRS_HERAUSGEBER"), 'drs',
                                  elem.findtext("DRS_NUMMER"), link=link)
        dokument['text'] = elem.findtext("DRS_TYP")
        dokument['seiten'] = hash
        dokument['source_url'] = url
        tbl_referenz.upsert(dokument, ['link', 'source_url', 'seiten'])

    for elem in doc.findall("PLENUM"):
        link = elem.findtext("PLPR_LINK")
        if link is not None and '#' in link:
            link, hash = link.rsplit('#', 1)
        dokument = dokument_by_id(elem.findtext("PLPR_HERAUSGEBER"), 'plpr',
                                  elem.findtext("PLPR_NUMMER"), link=link)
        dokument['text'] = elem.findtext("PLPR_KLARTEXT")
        dokument['seiten'] = elem.findtext("PLPR_SEITEN")
        dokument['source_url'] = url
        tbl_referenz.upsert(dokument, ['link', 'source_url', 'seiten'])

    tbl_ablauf.upsert(a, ['source_url'])
    return a


def scrape_index():
    for wp in WAHLPERIODEN:
        url = EXTRAKT_INDEX % wp
        log.info("Loading WP index: %r", url)
        res = requests.get(url)
        doc = html.fromstring(res.content)
        for result in doc.findall(".//a[@class='linkIntern']"):
            aurl = urljoin(url, result.get('href'))
            scrape_ablauf(aurl)


if __name__ == '__main__':
    scrape_index()
