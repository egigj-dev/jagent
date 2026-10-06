# JSON-LD location parsing; COUNTRY_NAMES expands board country codes and job supplies schema.org fields.
COUNTRY_NAMES = {
    "AL": "Albania", "ALB": "Albania", "TR": "Turkey", "TUR": "Turkey",
    "AT": "Austria", "AUT": "Austria", "BE": "Belgium", "BEL": "Belgium",
    "BG": "Bulgaria", "BGR": "Bulgaria", "HR": "Croatia", "HRV": "Croatia",
    "CY": "Cyprus", "CYP": "Cyprus", "CZ": "Czechia", "CZE": "Czechia",
    "DK": "Denmark", "DNK": "Denmark", "EE": "Estonia", "EST": "Estonia",
    "FI": "Finland", "FIN": "Finland", "FR": "France", "FRA": "France",
    "DE": "Germany", "DEU": "Germany", "GR": "Greece", "GRC": "Greece",
    "HU": "Hungary", "HUN": "Hungary", "IE": "Ireland", "IRL": "Ireland",
    "IT": "Italy", "ITA": "Italy", "LV": "Latvia", "LVA": "Latvia",
    "LT": "Lithuania", "LTU": "Lithuania", "LU": "Luxembourg", "LUX": "Luxembourg",
    "MT": "Malta", "MLT": "Malta", "NL": "Netherlands", "NLD": "Netherlands",
    "PL": "Poland", "POL": "Poland", "PT": "Portugal", "PRT": "Portugal",
    "RO": "Romania", "ROU": "Romania", "SK": "Slovakia", "SVK": "Slovakia",
    "SI": "Slovenia", "SVN": "Slovenia", "ES": "Spain", "ESP": "Spain",
    "SE": "Sweden", "SWE": "Sweden", "GB": "United Kingdom", "GBR": "United Kingdom",
    "CH": "Switzerland", "CHE": "Switzerland", "NO": "Norway", "NOR": "Norway",
    "IS": "Iceland", "ISL": "Iceland", "UA": "Ukraine", "UKR": "Ukraine",
    "US": "United States", "USA": "United States", "CA": "Canada", "CAN": "Canada",
    "GE": "Georgia", "GEO": "Georgia",
}


def job_locations(job, default=None):
    locations = []

    def add(value):
        if isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            add(value.get("name"))
        elif isinstance(value, str) and value.strip():
            value = value.strip()
            value = COUNTRY_NAMES.get(value.upper(), value)
            if value not in locations:
                locations.append(value)

    places = job.get("jobLocation") or []
    if isinstance(places, dict):
        places = [places]
    for place in places:
        address = place.get("address") or {}
        add(address.get("addressLocality"))
        add(address.get("addressCountry"))
    requirements = job.get("applicantLocationRequirements") or []
    if isinstance(requirements, dict):
        requirements = [requirements]
    for requirement in requirements:
        if isinstance(requirement, str):
            add(requirement)
            continue
        add(requirement.get("name"))
        address = requirement.get("address") or {}
        add(address.get("addressCountry"))
        add(address.get("addressRegion"))
    return locations or list(default or [])


def job_remote(job):
    location_type = job.get("jobLocationType")
    return location_type == "TELECOMMUTE" or (
        isinstance(location_type, list) and "TELECOMMUTE" in location_type
    )
