lazy import logging
lazy import time
lazy import requests
lazy from requests.exceptions import RequestException
lazy from app.core.settings import get_settings

logger = logging.getLogger(__name__)

SETTINGS = get_settings()


def fetch_geogrid_report(
    report_path: str,
    page_size: int = 5000,
    max_attempts: int = 3,
    project_mode: bool = False,
    items: str | None = None,
    geogrid_user_id: int | None = None,
) -> list[dict]:

    all_records = []
    current_page = 1
    consult_totals = 'S'
    total_records = 0
    failed_attempts = 0

    project_mode_flag = 'S' if project_mode else 'N'

    link = SETTINGS.GEOGRID_REPORTS_API_URL + report_path

    while True:
        try:
            if failed_attempts >= max_attempts:
                logger.error(
                    'Max retries exceeded on page %s, try again later',
                    current_page,
                )
                raise RuntimeError('Max retries exceeded ...')

            logger.info('Requesting page %s', current_page)

            response = requests.get(
                link,
                params={
                    'pagina': current_page,
                    'registrosPorPagina': page_size,
                    'consultarTotais': consult_totals,
                    'modoProjeto[]': project_mode_flag,
                    'itens[]': items,
                    'idsUsuarios[]': geogrid_user_id,
                    'ordemOrdenar[]': 'asc',
                },
                headers={'api-key': SETTINGS.GEOGRID_API_KEY},
                timeout=15,
            )

            response.raise_for_status()
            response_json = response.json()

        except RequestException as http_err:
            failed_attempts += 1
            logger.warning(
                'Request failed on page %s (attempt %s/%s): %s',
                current_page,
                failed_attempts,
                max_attempts,
                http_err,
            )
            time.sleep(5)
            continue

        if not response_json['registros']:
            break

        if total_records == 0:
            total_records = int(response_json['totalRegistros'])
            consult_totals = 'N'
            logger.info('Total records reported by API: %s', total_records)

        all_records.extend(response_json['registros'])
        failed_attempts = 0

        logger.info(
            'Page %s: %s records (%s/%s collected)',
            current_page,
            len(response_json['registros']),
            len(all_records),
            total_records,
        )

        current_page += 1

        if len(all_records) >= total_records:
            break

    logger.info('Finished with %s records', len(all_records))

    return all_records
