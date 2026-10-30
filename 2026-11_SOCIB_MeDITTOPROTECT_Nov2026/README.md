# SOCIB MeDITTOPROTECT — November 2026

Multi-platform field campaign in the Cabrera Archipelago and Cabrera Channel (Balearic Islands, western Mediterranean) on board the R/V SOCIB, November 2026.

- **Dates:** 2–5 November 2026
- **Objectives:**
  - Deploy ARVOR-C profiling floats and SVP-B surface drifters.
  - Sample the Cabrera Channel with the vessel-mounted ADCP.
  - Validate an ocean model with SWOT data assimilation against the ADCP observations.
- **Platforms:** R/V SOCIB (vessel-mounted ADCP, CTD, thermosalinograph), ARVOR-C profiling floats, SVP-B surface drifters, SWOT satellite altimetry.

## Contents

```
2026-11_SOCIB_MeDITTOPROTECT_Nov2026/
├── README.md
├── RV-SOCIB_ADCP_setup.md   # onboard ADCP procedure (in Spanish, for the onboard team)
├── selected_passes.csv      # SWOT passes over the area
├── notebooks/
│   ├── SWOT_passes.ipynb
│   ├── adcp_quicklook.ipynb
│   └── post-cruise_ADCP.ipynb
├── src/
│   ├── vmdas.py             # VmDas PD0 reader
│   └── adcp_quicklook.py    # ADCP quick-look processing, QC and plots
├── figures/
│   └── SWOT_all_passes.png
└── data/                    # local only, not versioned
    ├── SWOT_data/
    ├── ADCP_data/           # raw VmDas files
    └── ADCP_quicklook/      # NetCDF output of adcp_quicklook.ipynb
```

| File | Description |
|------|-------------|
| `notebooks/SWOT_passes.ipynb` | Downloads the SWOT passes listed in `selected_passes.csv`, crops them to the area and plots absolute dynamic topography with geostrophic velocities. |
| `selected_passes.csv` | SWOT cycle/pass numbers and overpass time windows over the area (`;`-separated). |
| `figures/SWOT_all_passes.png` | Output figure of `SWOT_passes.ipynb`. |
| `notebooks/adcp_quicklook.ipynb` | Onboard quick-look of raw VmDas files (`.LTA`/`.STA`/`.ENX`): QC, absolute velocities (GPS or bottom track), sections and layer map. Figures to `figures/adcp_quicklook/`, NetCDF to `data/ADCP_quicklook/`. |
| `src/vmdas.py` | Reader for VmDas PD0 files (`.LTA`/`.STA`/`.ENX`) and `.VMO` settings into an xarray Dataset. Used by `adcp_quicklook.ipynb`. |
| `src/adcp_quicklook.py` | Absolute velocities, QC (percent good, error velocity, side-lobe cut, ship manoeuvres) and quick-look plots. Used by `adcp_quicklook.ipynb`. |
| `notebooks/post-cruise_ADCP.ipynb` | Vessel-mounted ADCP transect processing (work in progress). |
| `RV-SOCIB_ADCP_setup.md` | Onboard ADCP procedure (VmDas acquisition, WinADCP export), in Spanish for the onboard team. |

## Data

Data are not stored in this repository. Notebooks expect the files below, with paths relative to this (campaign) folder.

| Data | Source | Local path |
|------|--------|------------|
| SWOT L3 LR SSH Expert v3.0 | [AVISO/ODATIS](https://www.aviso.altimetry.fr) THREDDS (`tds-odatis.aviso.altimetry.fr`), requires an AVISO account | `data/SWOT_data/` (downloaded by `SWOT_passes.ipynb`) |
| R/V SOCIB ADCP, CTD, TSG (L0/L1 netCDF) | [SOCIB data catalogue](https://www.socib.es) | `data/` (`dep*_socib-rv_*.nc`) |
| Raw ADCP files (VmDas: `.ENR`, `.ENS`, `.ENX`, `.STA`, `.LTA`, `.N1R`–`.N3R`, `.NMS`, `.VMO`, `.LOG`) | R/V SOCIB onboard PC | `data/ADCP_data/` |

AVISO credentials are read from `~/.netrc`:

```
machine tds-odatis.aviso.altimetry.fr login <user> password <password>
```

## Requirements

`numpy`, `pandas`, `xarray`, `matplotlib`, `cmocean`, `cartopy`, `requests`, `siphon`, `tqdm`.

Run the notebooks from `notebooks/` (they reach inputs, `data/` and `figures/` through `../`).
