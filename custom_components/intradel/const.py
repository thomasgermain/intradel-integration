"""intradel integration constants."""

from homeassistant.const import Platform

DOMAIN = "intradel"
COOKIE_DOMAIN = "intradel.be"

PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 720
# Minutes. 0 would silently disable polling, so it is not offered.
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 10080  # one week

# Seconds before a request to the site is given up on; aiohttp's own default is 5 minutes.
REQUEST_TIMEOUT = 30

# Only kept to describe entries created before login/password was removed; the
# integration authenticates with a session cookie exclusively.
CONF_TOWN = "town"
CONF_COOKIE = "cookie"

# Minutes between session keep-alive pings for cookie-based entries; 0 disables.
CONF_KEEPALIVE_INTERVAL = "keepalive_interval"
DEFAULT_KEEPALIVE_INTERVAL = 15
MAX_KEEPALIVE_INTERVAL = 1440  # one day

MANUFACTURER = "Intradel"
# Id pyintradel gives the recypark item (it has no chip, so its name is used).
RECYPARC_ID = "RECYPARC"

ATTR_START_DATE = "start_date"
ATTR_DETAILS = "details"
ATTR_BIN_COLLECTIONS = "collections"
ATTR_CHIP = "chip"
