[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/thomasgermain/intradel-integration?style=for-the-badge)

# Intradel integration

## Installations

- Through HACS [custom repositories](https://hacs.xyz/docs/faq/custom_repositories/) !
- Otherwise, download the zip from the latest release and copy `intradel` folder and put it inside
  your `custom_components` folder.

You can configure it through the UI using integration.
You have to provide your username and password and the town (same as intradel website)

## Provided entities

### organic/residual waste sensor

The `state` is total weight of waste of the **current year**.
The attribute `details` contains the details of bin collection (weight and date).
The attribute `start_date` is basically 01-01 of the current year.

### recyparc sensor

The `state` is the number of visit of the **current year**.
The attribute `details` contains the details of the visits (detail/volume and date) 
The attribute `start_date` is basically 01-01 of the current year.

---
<a href="https://www.buymeacoffee.com/tgermain" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>
