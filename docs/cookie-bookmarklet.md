# Refreshing the session cookie in one click

The Intradel login form is protected by a server-verified invisible reCAPTCHA, so
an automated login/password request is always rejected. A session cookie captured
from a browser that is already logged in is the only usable credential.

You still log in on the Intradel website yourself, in your own browser. Only the
resulting session is handed over to Home Assistant, by the `intradel.set_cookie`
service, so you never have to open the network inspector again.

## 1. Allow your browser to call Home Assistant

The bookmarklet runs on `www.intradel.be` and calls Home Assistant, which is a
cross-origin request. Add this to `configuration.yaml` and restart:

```yaml
http:
  cors_allowed_origins:
    - https://www.intradel.be
```

## 2. Create a long-lived access token

In Home Assistant, open your profile, go to **Security**, and create a
**long-lived access token**.

> The token is stored in the bookmark itself, in clear text. Anyone with access to
> your browser profile can read it and use it against your Home Assistant. Treat it
> as a password: use a dedicated Home Assistant user with only the permissions it
> needs, and delete the token when you stop using the bookmarklet.

## 3. Create the bookmark

Create a new bookmark whose URL is the code below, after replacing `HA_URL` and
`HA_TOKEN` with your own values.

```js
javascript:(async () => {
  const HA_URL = "http://homeassistant.local:8123";
  const HA_TOKEN = "paste-your-long-lived-token-here";
  const cookie = document.cookie;
  if (!cookie.includes("PHPSESSID")) {
    alert("No Intradel session found. Log in first, then click again.");
    return;
  }
  try {
    const res = await fetch(`${HA_URL}/api/services/intradel/set_cookie`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${HA_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ cookie }),
    });
    alert(res.ok ? "Cookie sent to Home Assistant." : `Failed: HTTP ${res.status}`);
  } catch (err) {
    alert(`Failed to reach Home Assistant: ${err}`);
  }
})();
```

## 4. Use it

Log in at <https://www.intradel.be/particulier/>, then click the bookmark. Home
Assistant validates the cookie against the site before storing it, and reloads the
integration. A cookie the site already rejects is refused with an explicit error
rather than being saved.

## How often will you need this?

Rarely. The session cookie carries no expiry of its own: it dies when the server
garbage-collects an inactive PHP session. The integration pings the site every
15 minutes (`keepalive_interval`, set it to 0 to disable) precisely so the session
stays alive. You should only need the bookmarklet after a long Home Assistant
outage, or if Intradel invalidates the session on its side.
