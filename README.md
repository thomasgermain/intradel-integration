[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/thomasgermain/intradel-integration?style=for-the-badge)

# Intradel integration

## Installations

- Through HACS [custom repositories](https://hacs.xyz/docs/faq/custom_repositories/) !
- Otherwise, download `intradel.zip` from the latest release and extract it into
  `custom_components/intradel` in your Home Assistant configuration folder.

You can configure it through the UI using integration.

Authentication is done with a **session cookie** only. The Intradel login form is protected
by an invisible reCAPTCHA that the site verifies server-side, so a plain username/password
request is always rejected (`La vérification anti-spam a échoué`) — that method is therefore
not offered. Log in once in a regular browser and paste the resulting session cookie.

Capturing the cookie by hand should rarely be needed again afterwards: the integration pings
the site regularly so the session never goes stale.

### How to get the session cookie

1. Open [https://www.intradel.be/particulier/](https://www.intradel.be/particulier/) in your
   browser and log in with your username, password and town.
2. Open the developer tools (`F12`, or right-click anywhere on the page and choose
   **Inspect**), then go to the **Network** tab.
3. Reload the page (`F5`) so a request to the site shows up in the list.
4. Click on the first request (e.g. `particulier` or `data.php`), open its **Headers**, and
   find the **Cookie** header under **Request Headers**.

   ![Where to find the Cookie request header in the browser's network inspector](docs/images/cookie-devtools.png)

5. Copy the full value of that header and paste it in the `Session cookie` field of the
   integration configuration.

The cookie is a session token: if it expires, the integration will ask you to repeat these
steps to provide a fresh one.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Minutes between scans | 720 | How often the data is fetched. |
| Minutes between keep-alive pings | 15 | Keeps the session cookie alive; 0 disables it. |

## Provided entities

### organic/residual waste sensor

The `state` is total weight of waste of the **current year**.
The attribute `details` contains the details of bin collection (weight and date).
The attribute `start_date` is basically 01-01 of the current year.

### recyparc sensor

The `state` is the number of visit of the **current year**.
The attribute `details` contains the details of the visits (detail/volume and date) 
The attribute `start_date` is basically 01-01 of the current year.

## Development

Requires Python 3.13. Tests run against the minimum supported Home Assistant (`hacs.json`),
pinned through `pytest-homeassistant-custom-component` in `requirements_test.txt`:

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check custom_components tests
ruff format custom_components tests
mypy custom_components/intradel
```

Install the git pre-commit hook once per clone; it runs ruff (lint with autofix, format) and
checks the YAML, JSON and TOML files before each commit:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files   # optional: run the hooks on the whole repository
```

To release, publish a GitHub release whose tag is the new version (e.g. `0.1.2` or `0.2.0b1`).
Once the checks pass, CI builds `intradel.zip` with that version in its manifest and attaches it
to the release; the `version` committed in `manifest.json` is a `0.0.0` placeholder.

---
<a href="https://www.buymeacoffee.com/tgermain" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>
