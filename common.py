# coding: utf-8
import os
import dataset
from normality import slugify


db = os.environ.get('DATABASE_URI', 'sqlite:///data.sqlite')
engine = dataset.connect(db)

tbl_person = engine['de_bundestag_person']
tbl_ablauf = engine['de_bundestag_ablauf']
tbl_position = engine['de_bundestag_position']
tbl_beitrag = engine['de_bundestag_beitrag']
tbl_zuweisung = engine['de_bundestag_zuweisung']
tbl_beschluss = engine['de_bundestag_beschluss']
tbl_referenz = engine['de_bundestag_referenz']


def make_long_name(data):
    pg = lambda n: data.get(n) if data.get(n) and data.get(n) != 'None' else ''
    # dept. names are long and skew levenshtein otherwise:
    ressort = "".join([x[0] for x in pg('ressort').split(' ') if len(x)])
    fraktion = pg('fraktion').replace(u"BÜNDNIS ", "B")
    return ' '.join((pg('titel'), pg('vorname'), pg('nachname'), pg('ort'),
                     fraktion or ressort))


def make_person(engine, beitrag, fp, source_url):
    person = {
        'fingerprint': fp,
        'slug': slugify(fp, sep='-'),
        'source_url': source_url,
        'vorname': beitrag['vorname'],
        'nachname': beitrag['nachname'],
        'ort': beitrag.get('ort'),
        'ressort': beitrag.get('ressort'),
        'land': beitrag.get('land'),
        'fraktion': beitrag.get('fraktion')
    }
    tbl_person.upsert(person, ['fingerprint'])
    return fp
