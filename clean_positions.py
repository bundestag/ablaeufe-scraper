import re
import logging
from hashlib import sha1
from datetime import datetime

from common import tbl_position


log = logging.getLogger(__name__)


def extend_position(data):
    dt, rest = data['fundstelle'].split("-", 1)
    data['date'] = datetime.strptime(dt.strip(), "%d.%m.%Y").isoformat()
    if ',' in data['urheber']:
        typ, quelle = data['urheber'].split(',', 1)
        data['quelle'] = re.sub("^.*Urheber.*:", "", quelle).strip()
        data['typ'] = typ.strip()
    else:
        data['typ'] = data['urheber']

    br = 'Bundesregierung, '
    if data['urheber'].startswith(br):
        data['urheber'] = data['urheber'][len(br):]

    data['fundstelle_doc'] = None
    if data['fundstelle_url'] and 'btp' in data['fundstelle_url']:
        data['fundstelle_doc'] = data['fundstelle_url'].rsplit('#', 1)[0]

    key = sha1()
    key.update(data['fundstelle'].encode('utf-8'))
    key.update(data['urheber'].encode('utf-8'))
    key.update(data['source_url'].encode('utf-8'))
    data['hash'] = key.hexdigest()[:10]
    tbl_position.update(data, ['id'])


def extend_positions(engine, source_url):
    log.info("Amending positions ...")
    for data in tbl_position.find(source_url=source_url):
        extend_position(data)
