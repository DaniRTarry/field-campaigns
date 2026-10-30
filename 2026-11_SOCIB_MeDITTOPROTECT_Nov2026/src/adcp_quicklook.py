"""Quick-look processing of VmDas ship ADCP data: absolute velocities, QC and plots."""
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from vmdas import VMDAS_NAME


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
    panels = [("u", "u (east) [m/s]", "RdBu_r", -vmax, vmax),
              ("v", "v (north) [m/s]", "RdBu_r", -vmax, vmax),
              ("speed", "speed [m/s]", "viridis", 0, vmax)]
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


def plot_map(ds, outfile=None, layer=(20, 60), arrow_scale=None):
    lay = ds.sel(depth=slice(*layer))
    um, vm = lay.u.mean("depth"), lay.v.mean("depth")

    fig, ax = plt.subplots(figsize=(8, 8), constrained_layout=True)
    ax.plot(ds.lon, ds.lat, ".-", color="0.6", lw=1, ms=3, zorder=1)
    ok = np.isfinite(um) & np.isfinite(vm)
    if arrow_scale is None:
        span = max(float(ds.lon.max() - ds.lon.min()), float(ds.lat.max() - ds.lat.min()), 0.05)
        arrow_scale = 0.5 / (0.08 * span)  # 0.5 m/s ~ 8 % of the plot width
    q = ax.quiver(ds.lon[ok], ds.lat[ok], um[ok], vm[ok], np.hypot(um[ok], vm[ok]),
                  cmap="plasma", scale=arrow_scale, scale_units="xy", angles="uv",
                  width=0.004, zorder=3)
    ax.quiverkey(q, 0.85, 0.05, 0.5, "0.5 m/s", coordinates="axes")
    fig.colorbar(q, ax=ax, label="speed [m/s]", shrink=0.7)
    ax.plot(ds.lon[0], ds.lat[0], "g^", ms=9, label="start", zorder=4)
    ax.plot(ds.lon[-1], ds.lat[-1], "rs", ms=8, label="end", zorder=4)
    ax.set_aspect(1 / np.cos(np.deg2rad(float(ds.lat.mean()))))
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    t0 = str(ds.time.values[0])[:16].replace("T", " ")
    t1 = str(ds.time.values[-1])[:16].replace("T", " ")
    ax.set_title("Currents %d-%d m  |  %s - %s UTC" % (layer[0], layer[1], t0, t1), fontsize=10)
    if outfile:
        fig.savefig(outfile, dpi=150)
    return fig
