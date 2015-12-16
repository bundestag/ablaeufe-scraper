import logging

from offenesparlament.data.ablaeufe.scrape import scrape_index, \
    scrape_ablauf, NoContentException
from offenesparlament.data.ablaeufe.clean_positions import \
    extend_positions
from offenesparlament.data.ablaeufe.clean_beitraege import \
    match_beitraege

log = logging.getLogger(__name__)


def process_ablauf(engine, indexer, url, force=False):
    try:
        data = scrape_ablauf(engine, url, force=force)
        clean_ablauf(engine, data)
        extend_positions(engine, url)
        match_beitraege(engine, url)
    except NoContentException:
        pass


ABLAUF = {
    'generator': scrape_index,
    'handler': process_ablauf
}
