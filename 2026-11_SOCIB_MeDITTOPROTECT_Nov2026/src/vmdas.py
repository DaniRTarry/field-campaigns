"""Reader for RDI PD0 files written by VmDas (.LTA, .STA, .ENX).

Reads the ensembles of one VmDas deployment into an xarray Dataset with
ship-relative velocities, bottom track, attitude and the VmDas navigation
block (first/last GPS fix of each average).
"""
import os
import re
import struct
from datetime import datetime, timedelta

import numpy as np
import xarray as xr

BAD_VEL = -32768
BAM32 = 180.0 / 2**31  # binary angle -> degrees (32 bit)
BAM16 = 180.0 / 2**15  # binary angle -> degrees (16 bit)

# PD0 data type IDs used by VmDas
ID_FIXED = 0x0000
ID_VAR = 0x0080
ID_VEL = 0x0100
ID_CORR = 0x0200
ID_ECHO = 0x0300
ID_PG = 0x0400
ID_BT = 0x0600
ID_NAV = 0x2000


def _iter_ensembles(buf):
    """Yield (start, nbytes) of each complete ensemble with a valid checksum.

    Incomplete ensembles at the end of the file (file still being written)
    and corrupted ensembles are skipped.
    """
    i, n = 0, len(buf)
    while i < n - 4:
        if buf[i] == 0x7F and buf[i + 1] == 0x7F:
            nbytes = struct.unpack_from("<H", buf, i + 2)[0]
            end = i + nbytes + 2
            if nbytes > 6 and end <= n:
                checksum = struct.unpack_from("<H", buf, i + nbytes)[0]
                if sum(buf[i : i + nbytes]) & 0xFFFF == checksum:
                    yield i, nbytes
                    i = end
                    continue
        i += 1


def _decode_nav(buf, o):
    """Decode the VmDas navigation block (ID 0x2000) starting at offset o."""
    day, month = buf[o + 2], buf[o + 3]
    year = struct.unpack_from("<H", buf, o + 4)[0]
    t1, _, lat1, lon1, t2, lat2, lon2 = struct.unpack_from("<iiiiiii", buf, o + 6)
    spd, trk = struct.unpack_from("<hH", buf, o + 34)
    out = dict(lat1=np.nan, lon1=np.nan, lat2=np.nan, lon2=np.nan,
               t1=None, t2=None, nav_speed=spd / 1000.0, nav_track=trk * BAM16)
    try:
        d0 = datetime(year, month, day)
    except ValueError:
        return out
    out["t1"] = d0 + timedelta(seconds=t1 / 1e4)
    out["t2"] = d0 + timedelta(seconds=t2 / 1e4)
    if out["t2"] < out["t1"]:  # crossed midnight
        out["t2"] += timedelta(days=1)
    if lat1 != 0 or lon1 != 0:
        out["lat1"], out["lon1"] = lat1 * BAM32, lon1 * BAM32
    if lat2 != 0 or lon2 != 0:
        out["lat2"], out["lon2"] = lat2 * BAM32, lon2 * BAM32
    return out


def read_pd0(path):
    """Read one VmDas PD0 file (.LTA, .STA, .ENX) into a list of dicts."""
    with open(path, "rb") as f:
        buf = f.read()

    records = []
    for start, _ in _iter_ensembles(buf):
        ndt = buf[start + 5]
        offsets = struct.unpack_from("<%dH" % ndt, buf, start + 6)
        blocks = {struct.unpack_from("<H", buf, start + o)[0]: start + o for o in offsets}
        if ID_FIXED not in blocks or ID_VAR not in blocks or ID_VEL not in blocks:
            continue

        o = blocks[ID_FIXED]
        ncells = buf[o + 9]
        cell = struct.unpack_from("<H", buf, o + 12)[0] / 100.0
        bin1 = struct.unpack_from("<H", buf, o + 32)[0] / 100.0
        coord = (buf[o + 25] >> 3) & 0b11  # 3 = Earth
        # System configuration, MSB bits 0-1: beam angle (0b11 = other, not coded)
        beam_angle = (15.0, 20.0, 30.0, np.nan)[buf[o + 5] & 0b11]

        o = blocks[ID_VAR]
        yy, mo, dd, hh, mi, ss, hs = buf[o + 4 : o + 11]
        try:
            adcp_time = datetime(2000 + yy, mo, dd, hh, mi, ss) + timedelta(seconds=hs / 100)
        except ValueError:
            adcp_time = None
        r = dict(
            ens=struct.unpack_from("<H", buf, o + 2)[0] + 65536 * buf[o + 11],
            adcp_time=adcp_time,
            heading=struct.unpack_from("<H", buf, o + 18)[0] / 100.0,
            pitch=struct.unpack_from("<h", buf, o + 20)[0] / 100.0,
            roll=struct.unpack_from("<h", buf, o + 22)[0] / 100.0,
            temperature=struct.unpack_from("<h", buf, o + 26)[0] / 100.0,
            ncells=ncells, cell=cell, bin1=bin1, coord=coord, beam_angle=beam_angle,
        )

        def _profile(bid, dtype):
            if bid not in blocks:
                return np.full((ncells, 4), np.nan)
            a = np.frombuffer(buf, dtype=dtype, count=ncells * 4,
                              offset=blocks[bid] + 2).reshape(ncells, 4)
            return a.astype(float)

        vel = _profile(ID_VEL, "<i2")
        vel[vel == BAD_VEL] = np.nan
        r["vel"] = vel / 1000.0  # m/s
        r["echo"] = _profile(ID_ECHO, "u1").mean(axis=1)
        r["pg"] = _profile(ID_PG, "u1")[:, 3]  # beam 4 = % good 4-beam solutions in Earth coords

        if ID_BT in blocks:
            o = blocks[ID_BT]
            rng = np.array(struct.unpack_from("<4H", buf, o + 16), float) / 100.0
            rng[rng == 0] = np.nan
            btv = np.array(struct.unpack_from("<4h", buf, o + 24), float)
            btv[btv == BAD_VEL] = np.nan
            r["bt_range"] = np.nanmean(rng) if np.isfinite(rng).any() else np.nan
            r["bt_range_min"] = np.nanmin(rng) if np.isfinite(rng).any() else np.nan
            r["bt_u"], r["bt_v"] = btv[0] / 1000.0, btv[1] / 1000.0
        else:
            r["bt_range"] = r["bt_range_min"] = r["bt_u"] = r["bt_v"] = np.nan

        if ID_NAV in blocks:
            r.update(_decode_nav(buf, blocks[ID_NAV]))
        else:
            r.update(lat1=np.nan, lon1=np.nan, lat2=np.nan, lon2=np.nan,
                     t1=None, t2=None, nav_speed=np.nan, nav_track=np.nan)
        records.append(r)
    return records


def read_vmo(path):
    """Return a dict with a few useful settings from a VmDas .VMO file."""
    keys = {
        "TransducerDepth(meters)": "transducer_depth",
        "FirstAvgTime": "sta_seconds",
        "SecondAvgTime": "lta_seconds",
        "AlignmentOffsetEA": "alignment_EA",
        "VelocityScaleFactorForProfileAndWTVelocities(unitless)": "scale_factor",
        "PRMarkBadBelowBottom": "mark_bad_below_bottom",
        "ManualBeamAngle": "manual_beam_angle",
    }
    out = {}
    with open(path, errors="ignore") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                if k in keys and keys[k] not in out:
                    out[keys[k]] = v
    return out


# VmDas file names: <DeploymentName><NNN>_<SSSSSS>.<EXT>
# NNN = deployment number, SSSSSS = file sequence number
VMDAS_NAME = re.compile(r"^(?P<name>.*?)(?P<num>\d{3})_(?P<seq>\d{6})\.(?P<ext>\w+)$")


def list_deployments(data_dir, ext="LTA"):
    """Return {deployment: [files sorted by sequence number]} for one file type.

    deployment is the file name prefix, e.g. 'SOCIB_CabreraSummer26004'.
    """
    out = {}
    for f in os.listdir(data_dir):
        m = VMDAS_NAME.match(f)
        if m and m.group("ext").upper() == ext.upper():
            dep = m.group("name") + m.group("num")
            out.setdefault(dep, []).append((int(m.group("seq")), os.path.join(data_dir, f)))
    return {d: [f for _, f in sorted(v)] for d, v in sorted(out.items())}


def select_deployment(data_dir, deployment, ext="LTA"):
    """Return the files of one deployment, sorted by sequence number.

    deployment : full name as in the file names, e.g. 'SOCIB_CabreraSummer26004'
                 (VmDas DeploymentName + 3-digit DeploymentNumber)
    """
    deps = list_deployments(data_dir, ext)
    if not deps:
        raise FileNotFoundError("No VmDas *.%s files in %s" % (ext, data_dir))
    if deployment not in deps:
        available = "\n  ".join("%s (%d files)" % (d, len(f)) for d, f in deps.items())
        raise ValueError("Deployment %r not found in %s. Available:\n  %s"
                         % (deployment, data_dir, available))
    return deps[deployment]


def load(data_dir, deployment, ext="LTA", transducer_depth=None):
    """Read all files of one deployment and file type into an xarray Dataset."""
    dep = deployment
    files = select_deployment(data_dir, deployment, ext)

    vmo = {}
    vmo_files = list_deployments(data_dir, "VMO").get(dep, [])
    if vmo_files:
        vmo = read_vmo(vmo_files[0])
    else:
        print("WARNING: no .VMO file found for %s" % dep)
    if transducer_depth is None:
        transducer_depth = float(vmo.get("transducer_depth", 0.0))

    recs = []
    for f in files:
        recs.extend(read_pd0(f))
    if not recs:
        raise RuntimeError("No complete ensembles found")

    r0 = recs[0]
    if r0["coord"] != 3:
        print("WARNING: data are not in Earth coordinates (EX bits = %d)" % r0["coord"])

    # The bin setup should not change within a deployment; if it does, keep the
    # first configuration and report what is dropped
    # (bin 1 distance jitters by ~1 cm between ensembles, so compare with a tolerance)
    cfg0 = (r0["ncells"], r0["cell"], r0["bin1"])

    def same_cfg(r):
        return (r["ncells"] == cfg0[0] and abs(r["cell"] - cfg0[1]) < 0.01
                and abs(r["bin1"] - cfg0[2]) < 0.1 * cfg0[1])

    n_all = len(recs)
    recs = [r for r in recs if same_cfg(r)]
    if len(recs) < n_all:
        print("WARNING: bin configuration changes within %s. Kept %d of %d ensembles "
              "(%d bins of %.1f m); the rest were dropped." % (dep, len(recs), n_all,
                                                              cfg0[0], cfg0[1]))
    ncells = r0["ncells"]
    beam_angle = r0["beam_angle"]
    if not np.isfinite(beam_angle):
        beam_angle = float(vmo.get("manual_beam_angle", 30.0))
        print("WARNING: beam angle not coded in the PD0 header; using %.0f deg" % beam_angle)
    depth = transducer_depth + r0["bin1"] + r0["cell"] * np.arange(ncells)

    def col(k):
        return np.array([r[k] for r in recs], dtype=float)

    # Time: midpoint between first and last GPS fix (UTC); fall back to ADCP clock
    time = []
    for r in recs:
        if r["t1"] is not None and r["t2"] is not None:
            time.append(r["t1"] + (r["t2"] - r["t1"]) / 2)
        else:
            time.append(r["adcp_time"])
    time = np.array(time, dtype="datetime64[ns]")

    # Ship velocity over ground from the first/last GPS fixes of each average
    lat1, lon1, lat2, lon2 = col("lat1"), col("lon1"), col("lat2"), col("lon2")
    dt = np.array([(r["t2"] - r["t1"]).total_seconds() if r["t1"] else np.nan
                   for r in recs])
    dt[dt <= 0] = np.nan
    R = 6371000.0
    latm = np.deg2rad((lat1 + lat2) / 2)
    ship_u = np.deg2rad(lon2 - lon1) * R * np.cos(latm) / dt
    ship_v = np.deg2rad(lat2 - lat1) * R / dt

    vel = np.stack([r["vel"] for r in recs])  # (time, depth, 4)

    ds = xr.Dataset(
        data_vars=dict(
            u_rel=(("time", "depth"), vel[:, :, 0]),
            v_rel=(("time", "depth"), vel[:, :, 1]),
            w=(("time", "depth"), vel[:, :, 2]),
            err_vel=(("time", "depth"), vel[:, :, 3]),
            echo=(("time", "depth"), np.stack([r["echo"] for r in recs])),
            pg=(("time", "depth"), np.stack([r["pg"] for r in recs])),
            lat=("time", np.where(np.isfinite(lat2), (lat1 + lat2) / 2, lat1)),
            lon=("time", np.where(np.isfinite(lon2), (lon1 + lon2) / 2, lon1)),
            ship_u=("time", ship_u),
            ship_v=("time", ship_v),
            bt_u=("time", col("bt_u")),
            bt_v=("time", col("bt_v")),
            bt_depth=("time", col("bt_range") + transducer_depth),
            bt_depth_min=("time", col("bt_range_min") + transducer_depth),
            heading=("time", col("heading")),
            pitch=("time", col("pitch")),
            roll=("time", col("roll")),
            temperature=("time", col("temperature")),
            ens=("time", col("ens")),
        ),
        coords=dict(time=time, depth=depth),
        attrs=dict(
            deployment=dep,
            source_files=", ".join(os.path.basename(f) for f in files),
            file_type=ext,
            transducer_depth_m=transducer_depth,
            cell_size_m=r0["cell"],
            beam_angle_deg=beam_angle,
            **{"vmdas_" + k: str(v) for k, v in vmo.items()},
        ),
    )
    ds = ds.sortby("time")
    _, keep = np.unique(ds.time.values, return_index=True)
    ds = ds.isel(time=np.sort(keep))

    units = dict(u_rel="m/s", v_rel="m/s", w="m/s", err_vel="m/s", echo="counts",
                 pg="%", lat="degrees_north", lon="degrees_east", ship_u="m/s",
                 ship_v="m/s", bt_u="m/s", bt_v="m/s", bt_depth="m", bt_depth_min="m",
                 heading="degrees",
                 pitch="degrees", roll="degrees", temperature="degC")
    for k, u in units.items():
        ds[k].attrs["units"] = u
    ds["depth"].attrs.update(units="m", positive="down")
    ds["u_rel"].attrs["long_name"] = "Eastward water velocity relative to the ship"
    ds["v_rel"].attrs["long_name"] = "Northward water velocity relative to the ship"
    ds["ship_u"].attrs["long_name"] = "Eastward ship velocity from GPS fixes"
    ds["ship_v"].attrs["long_name"] = "Northward ship velocity from GPS fixes"
    ds["bt_u"].attrs["long_name"] = "Eastward bottom velocity relative to the ship (bottom track)"
    ds["bt_v"].attrs["long_name"] = "Northward bottom velocity relative to the ship (bottom track)"
    ds["bt_depth"].attrs["long_name"] = "Bottom depth from bottom track (mean of the beams)"
    ds["bt_depth_min"].attrs["long_name"] = "Bottom depth from bottom track (shallowest beam)"
    return ds
