import requests


def where_stroll_finish():
    f1_url = 'https://f1api.dev/api/current/last/race'

    req = requests.get(f1_url)
    req.raise_for_status()

    res = req.json()
    try:
        for i in range(23):
            driver_id = res['races']['results'][i]['driver']['driverId']
            if driver_id == 'stroll':
                return i
    except IndexError:
        return 404
