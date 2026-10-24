"""intradel integration constants."""

from homeassistant.const import Platform

DOMAIN = "intradel"
COOKIE_DOMAIN = "intradel.be"

PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = 720

# Only kept to describe entries created before login/password was removed; the
# integration authenticates with a session cookie exclusively.
CONF_TOWN = "town"
CONF_COOKIE = "cookie"

# Minutes between keep-alive pings, 0 disables; below PHP's 24 min default session lifetime.
CONF_KEEPALIVE_INTERVAL = "keepalive_interval"
DEFAULT_KEEPALIVE_INTERVAL = 15

ATTR_START_DATE = "start_date"
