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

# Minutes between session keep-alive pings; 0 disables. The default is comfortably below
# PHP's 24-minute default session.gc_maxlifetime: the site does not advertise its own
# value, so this errs on the safe side, and a ping costs no payload at all.
CONF_KEEPALIVE_INTERVAL = "keepalive_interval"
DEFAULT_KEEPALIVE_INTERVAL = 15

ATTR_START_DATE = "start_date"
