"""Quick-look processing of VmDas ship ADCP data: absolute velocities, QC and plots."""
import cmocean
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from vmdas import VMDAS_NAME

# Speed colormap for arrows: cmocean speed without its palest end, so weak
# currents stay visible on a white background
SPEED_CMAP_ARROWS = cmocean.tools.crop_by_percent(cmocean.cm.speed, 25, which="min")


def process(ds, ref="nav", pg_min=50, err_max=0.2, sidelobe_cells=1.0, dv_max=1.0):
    """Compute absolute velocities and apply basic QC.

    ref      : 'nav' (GPS ship velocity) or 'bt' (bottom track)
    pg_min   : minimum percent good (4-beam solutions)
    err_max  : maximum absolute error velocity (m/s)
    sidelobe_cells : side-lobe cut-off. The bottom echo through the side lobes
               contaminates everything deeper than cos(beam angle) * D below
               the transducer, D = range to the bottom (shallowest beam).
               Each bin averages over about one cell above and below its
               centre, so bins deeper than cos(beam angle) * D - sidelobe_cells
               * cell are masked. None disables the test.
    dv_max   : ensembles where the ship velocity differs from a neighbouring
               ensemble by more than dv_max (m/s) are masked. These are
               averages that include a start/stop or a sharp turn, where the
               ship velocity is poorly removed. None disables the test.
    """
    if ref == "nav":
        su, sv = ds.ship_u, ds.ship_v
    elif ref == "bt":
        su, sv = -ds.bt_u, -ds.bt_v  # BT measures the bottom moving relative to the ship
    else:
        raise ValueError("ref must be 'nav' or 'bt'")

    u = ds.u_rel + su
    v = ds.v_rel + sv

    good = ds.pg >= pg_min
    good &= np.abs(ds.err_vel) <= err_max
    tdepth = ds.attrs["transducer_depth_m"]
    if sidelobe_cells is not None:
        cos_beam = np.cos(np.deg2rad(ds.attrs["beam_angle_deg"]))
        bottom_cut = (tdepth + cos_beam * (ds.bt_depth_min - tdepth)
                      - sidelobe_cells * ds.attrs["cell_size_m"])
        good &= ~(ds.depth > bottom_cut)  # NaN bottom (no BT) -> no masking

    ship_changing = np.zeros(ds.sizes["time"], bool)
    if dv_max is not None and ds.sizes["time"] > 1:
        su_, sv_ = su.values, sv.values
        spd = np.hypot(su_, sv_)
        dv = np.nan_to_num(np.hypot(np.diff(su_), np.diff(sv_)))
        prev_d = np.r_[np.inf, dv]   # difference with previous ensemble
        next_d = np.r_[dv, np.inf]   # difference with next ensemble
        prev_s = np.r_[np.inf, spd[:-1]]
        next_s = np.r_[spd[1:], np.inf]
        # Changing: differs from both neighbours (start/stop in progress or turn)...
        ship_changing = (prev_d > dv_max) & (next_d > dv_max)
        # ...but not a short station between two transits (slower than both neighbours)
        station = spd < np.fmin(prev_s, next_s) - dv_max
        ship_changing &= ~station
        ship_changing[np.isinf(prev_d) & np.isinf(next_d)] = False
        good &= xr.DataArray(~ship_changing, dims="time")
    ds["ship_changing"] = ("time", ship_changing.astype("int8"))
    ds["ship_changing"].attrs["long_name"] = "1 = masked: ship speed/course changing (start, stop or turn)"

    ds["u"] = u.where(good)
    ds["v"] = v.where(good)
    ds["speed"] = np.hypot(ds.u, ds.v)
    ds["u"].attrs = dict(units="m/s", long_name="Eastward absolute current (ref=%s)" % ref)
    ds["v"].attrs = dict(units="m/s", long_name="Northward absolute current (ref=%s)" % ref)
    ds["speed"].attrs = dict(units="m/s", long_name="Current speed")
    ds.attrs.update(reference=ref, qc_pg_min=pg_min, qc_err_max=err_max,
                    qc_sidelobe_cells=str(sidelobe_cells), qc_dv_max=str(dv_max))
    return ds


def output_stem(ds):
    """Output file name: deployment name + file sequence range + file type.

    One file : SOCIB_CabreraSummer26004_000000_STA
    Several  : SOCIB_CabreraSummer26004_000000-000003_STA
    '_bt' is appended when bottom track is used as reference.
    """
    seqs = [VMDAS_NAME.match(f.strip()).group("seq") for f in ds.attrs["source_files"].split(",")]
    name = "%s_%s" % (ds.attrs["deployment"], seqs[0])
    if len(seqs) > 1:
        name += "-" + seqs[-1]
    name += "_" + ds.attrs["file_type"]
    if ds.attrs.get("reference") == "bt":
        name += "_bt"
    return name


def _with_gaps(ds, factor=3):
    """Insert empty profiles in time gaps so sections show them blank.

    A gap is any interval longer than factor x the typical ensemble interval.
    Two NaN profiles are added inside each gap, one interval after the last
    profile and one before the next, so pcolormesh does not stretch the data
    across the gap.
    """
    if ds.sizes["time"] < 3:
        return ds
    t = ds.time.values
    dt = np.diff(t)
    step = np.median(dt)
    gaps = np.where(dt > factor * step)[0]
    if gaps.size == 0:
        return ds
    new_t = np.concatenate([np.r_[t[i] + step, t[i + 1] - step] for i in gaps])
    empty = ds.isel(time=slice(0, 1)).squeeze("time", drop=True)
    empty = xr.full_like(empty, np.nan).expand_dims(time=new_t)
    return xr.concat([ds, empty], dim="time", data_vars="all").sortby("time")


def plot_sections(ds, outfile=None, vmax=0.5, max_depth=None):
    ymax = max_depth or float(ds.depth.where(ds.u.notnull().any("time")).max()) + 10
    dsp = _with_gaps(ds[["u", "v", "speed", "bt_depth"]])
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, constrained_layout=True)
    panels = [("u", "u (east) [m/s]", cmocean.cm.balance, -vmax, vmax),
              ("v", "v (north) [m/s]", cmocean.cm.balance, -vmax, vmax),
              ("speed", "speed [m/s]", cmocean.cm.speed, 0, vmax)]
    for ax, (var, label, cmap, lo, hi) in zip(axes, panels):
        pc = ax.pcolormesh(dsp.time, dsp.depth, dsp[var].T, cmap=cmap, vmin=lo, vmax=hi,
                           shading="nearest")
        ax.plot(dsp.time, dsp.bt_depth, "k-", lw=1.2, label="bottom (BT)")
        fig.colorbar(pc, ax=ax, label=label, pad=0.01)
        ax.set_ylabel("depth [m]")
        ax.set_ylim(ymax, 0)
    axes[0].legend(loc="lower right", fontsize=8)
    axes[0].set_title("%s  |  ref = %s" % (output_stem(ds), ds.attrs["reference"]), fontsize=10)
    axes[-1].set_xlabel("time (UTC)")
    fig.autofmt_xdate()
    if outfile:
        fig.savefig(outfile, dpi=150)
    return fig


def along_track_average(lon, lat, u, v, dx_km=2.0):
    """Average current vectors in bins of along-track distance.

    Bins are dx_km long along the ship track, so ensembles taken on station
    (ship not moving) fall in one bin and give a single vector instead of a
    pile of overlapping ones. Returns lon, lat, u, v of the bins with data.
    """
    lon, lat, u, v = (np.asarray(a, float) for a in (lon, lat, u, v))
    pos = np.isfinite(lon) & np.isfinite(lat)
    lon, lat, u, v = lon[pos], lat[pos], u[pos], v[pos]
    R = 6371.0
    step = np.hypot(np.deg2rad(np.diff(lon)) * np.cos(np.deg2rad(lat[:-1])),
                    np.deg2rad(np.diff(lat))) * R
    ibin = (np.r_[0, np.cumsum(step)] // dx_km).astype(int)
    out = []
    for i in np.unique(ibin):
        m = (ibin == i) & np.isfinite(u) & np.isfinite(v)
        if m.any():
            out.append((lon[m].mean(), lat[m].mean(), u[m].mean(), v[m].mean()))
    return np.array(out).T if out else np.empty((4, 0))


def _nice(x):
    """Round x to 1, 2 or 5 x 10^n (for the reference arrow)."""
    if not np.isfinite(x) or x <= 0:
        return 0.1
    e = 10 ** np.floor(np.log10(x))
    return min((1, 2, 5, 10), key=lambda k: abs(k * e - x)) * e


def plot_map(ds, outfile=None, layer=(20, 60), dx_km=2.0, key=None):
    """Ship track and currents averaged over a depth layer.

    dx_km : along-track averaging distance (km) for the vectors; None plots
            every ensemble.
    key   : reference arrow (m/s); None = 90th percentile of the speed, rounded.
            The reference arrow is 10 % of the plot width.
    """
    lay = ds.sel(depth=slice(*layer))
    um, vm = lay.u.mean("depth").values, lay.v.mean("depth").values
    if dx_km:
        x, y, uq, vq = along_track_average(ds.lon, ds.lat, um, vm, dx_km)
    else:
        ok = np.isfinite(um) & np.isfinite(vm)
        x, y, uq, vq = ds.lon.values[ok], ds.lat.values[ok], um[ok], vm[ok]
    spd = np.hypot(uq, vq)
    if key is None:
        key = _nice(np.percentile(spd, 90)) if spd.size else 0.1

    # Square extent in km, so the track fills the plot whatever its orientation
    lat0 = float(ds.lat.mean())
    coslat = np.cos(np.deg2rad(lat0))
    lon_c = (float(ds.lon.max()) + float(ds.lon.min())) / 2
    lat_c = (float(ds.lat.max()) + float(ds.lat.min())) / 2
    half = 0.55 * max(float(ds.lon.max() - ds.lon.min()) * coslat,
                      float(ds.lat.max() - ds.lat.min()), 0.02)

    fig, ax = plt.subplots(figsize=(8.5, 8), constrained_layout=True)
    ax.plot(ds.lon, ds.lat, "-", color="0.6", lw=1, zorder=1)
    q = ax.quiver(x, y, uq, vq, spd, cmap=SPEED_CMAP_ARROWS, clim=(0, 2 * key),
                  scale=key / 0.1, scale_units="width", angles="uv",
                  width=0.005, headwidth=3.5, headlength=4, zorder=3)
    ax.quiverkey(q, 0.9, -0.08, key, "%g m/s" % key, coordinates="axes", labelpos="W")
    fig.colorbar(q, ax=ax, label="speed [m/s]", shrink=0.7, extend="max")
    ax.plot(ds.lon[0], ds.lat[0], "g^", ms=9, label="start", zorder=4)
    ax.plot(ds.lon[-1], ds.lat[-1], "rs", ms=8, label="end", zorder=4)
    ax.set_aspect(1 / coslat)
    ax.set_xlim(lon_c - half / coslat, lon_c + half / coslat)
    ax.set_ylim(lat_c - half, lat_c + half)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    t0 = str(ds.time.values[0])[:16].replace("T", " ")
    t1 = str(ds.time.values[-1])[:16].replace("T", " ")
    avg = "%g km along-track averages" % dx_km if dx_km else "all ensembles"
    ax.set_title("Currents %d-%d m (%s)  |  %s - %s UTC" % (layer[0], layer[1], avg, t0, t1),
                 fontsize=10)
    if outfile:
        fig.savefig(outfile, dpi=150)
    return fig
