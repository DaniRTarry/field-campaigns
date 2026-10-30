# field-campaigns

Data processing and analysis from oceanographic field campaigns.

This repository collects the code, notebooks and analysis I develop for oceanographic field campaigns, mostly multi-platform observations of mesoscale and submesoscale dynamics (surface drifters, ocean gliders and supporting ship-based measurements). Each campaign lives in its own folder.

## Repository structure

```
field-campaigns/
├── YYYY-campaign-name/
│   ├── README.md        # campaign overview, platforms, data sources
│   ├── notebooks/       # exploratory analysis and figures
│   ├── src/             # processing scripts and reusable functions
│   └── figures/         # output figures (optional)
└── ...
```

Campaign folders are named `YYYY-campaign-name`, so they sort chronologically.

## Campaigns

| Campaign | Year | Region | Platforms | Folder |
|----------|------|--------|-----------|--------|
| _SOCIB_MeDITTOPROTECT_Nov2026_ | 2026 | _Cabrera_ | _ARVORC, drifters, ADCP, satellite..._ | [`2026-11_SOCIB_MeDITTOPROTECT_Nov2026`](./2026-11_
SOCIB_MeDITTOPROTECT_Nov2026) |

## Data

Raw data are **not** stored in this repository. Each campaign README points to the official data repository or provider (e.g. PO.DAAC, SEANOE, SOCIB data catalogue) and describes where the scripts expect to find the files locally.

## Requirements

Analysis is done in Python. Main dependencies:

- `numpy`, `pandas`, `xarray`
- `matplotlib`, `cartopy`
- `scipy`

Campaign-specific requirements are listed in each campaign folder.

## License

Code in this repository is released under the [MIT License](./LICENSE).
Figures and derived products, unless stated otherwise, are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Original data remain subject to the policies of their respective providers.

## Contact

Daniel R. Tarry
GitHub: [@DaniRTarry](https://github.com/DaniRTarry)
