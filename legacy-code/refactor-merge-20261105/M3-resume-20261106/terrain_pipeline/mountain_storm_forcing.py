"""Absolute-coordinate parameterized moving storms; not observed weather."""

from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.special import erf

from terrain_pipeline.common_infra import identity, readonly, save_bundle, load_bundle
from terrain_pipeline.runoff import _hash as _hash


SCHEMA = "mountain-moving-storm-v1"
MAX_CELLS = 250000
MAX_HRUS = 256
MAX_STEPS = 1344
MAX_WORK = 50_000_000
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class StormParameters:
    center_x_m: float
    center_z_m: float
    velocity_x_m_s: float
    velocity_z_m_s: float
    sigma_m: float
    peak_mm_h: float
    start_s: float
    end_s: float
    spatial_mode: str = "gaussian"

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key != "spatial_mode" and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("finite storm parameter required: " + key)
        if (not 1 <= self.sigma_m <= 1e7 or not 0 <= self.peak_mm_h <= 1000 or
                not 0 <= self.start_s < self.end_s <= 1e9 or
                math.hypot(self.velocity_x_m_s, self.velocity_z_m_s) > 100 or
                self.spatial_mode not in {"gaussian", "uniform"} or
                max(abs(self.center_x_m), abs(self.center_z_m)) > 1e12):
            raise ValueError("storm outside supported parameter bounds")


def interval_mean_mm_h(east_m, south_m, start_s, end_s, parameters):
    """Analytic Gaussian time integral; center is specified at storm start_s."""
    if not isinstance(parameters, StormParameters):
        raise ValueError("StormParameters required")
    parameters.__post_init__()
    if (type(start_s) not in (int, float) or type(end_s) not in (int, float) or
            not math.isfinite(start_s) or not math.isfinite(end_s) or not 0 <= start_s < end_s <= 1e9):
        raise ValueError("bounded positive physical time interval required")
    east, south = np.broadcast_arrays(np.asarray(east_m), np.asarray(south_m))
    if east.size > MAX_CELLS or east.dtype.kind not in "fiu" or south.dtype.kind not in "fiu" or not np.isfinite(east).all() or not np.isfinite(south).all():
        raise ValueError("bounded finite absolute coordinates required")
    lower = max(start_s, parameters.start_s)
    upper = min(end_s, parameters.end_s)
    if upper <= lower:
        return np.zeros(east.shape, np.float64)
    duration = end_s-start_s
    if parameters.spatial_mode == "uniform":
        return np.full(east.shape, parameters.peak_mm_h*(upper-lower)/duration, np.float64)
    offset_x = east-parameters.center_x_m
    offset_z = south-parameters.center_z_m
    velocity_squared = parameters.velocity_x_m_s**2 + parameters.velocity_z_m_s**2
    sigma_squared = parameters.sigma_m**2
    if velocity_squared == 0:
        return parameters.peak_mm_h*np.exp(-(offset_x**2+offset_z**2)/(2*sigma_squared))*(upper-lower)/duration
    speed = math.sqrt(velocity_squared)
    if speed*(upper-lower)/parameters.sigma_m < 1e-5:
        nodes, weights = np.polynomial.legendre.leggauss(4)
        midpoint = (lower+upper)/2
        half_width = (upper-lower)/2
        average = np.zeros(east.shape,np.float64)
        for node,weight in zip(nodes,weights):
            elapsed = midpoint+half_width*node-parameters.start_s
            distance_x = offset_x-parameters.velocity_x_m_s*elapsed
            distance_z = offset_z-parameters.velocity_z_m_s*elapsed
            average += weight*np.exp(-(distance_x**2+distance_z**2)/(2*sigma_squared))/2
        return parameters.peak_mm_h*average*(upper-lower)/duration
    along_m = (offset_x*parameters.velocity_x_m_s+offset_z*parameters.velocity_z_m_s)/speed
    across_m = (offset_x*parameters.velocity_z_m_s-offset_z*parameters.velocity_x_m_s)/speed
    lower_arg = (speed*(lower-parameters.start_s)-along_m)/(math.sqrt(2)*parameters.sigma_m)
    upper_arg = (speed*(upper-parameters.start_s)-along_m)/(math.sqrt(2)*parameters.sigma_m)
    from scipy.special import erfc

    difference = erf(upper_arg)-erf(lower_arg)
    positive = lower_arg > 0
    negative = upper_arg < 0
    difference = np.where(positive, erfc(lower_arg)-erfc(upper_arg), difference)
    difference = np.where(negative, erfc(-upper_arg)-erfc(-lower_arg), difference)
    integral = np.exp(-across_m**2/(2*sigma_squared))*parameters.sigma_m*math.sqrt(math.pi/2)/speed*difference
    return parameters.peak_mm_h*np.maximum(integral,0.)/duration


def preflight(cells, active_cells, steps, hrus, spatial_subsamples):
    values = (cells, active_cells, steps, hrus, spatial_subsamples)
    if any(type(value) is not int for value in values) or not 1 <= active_cells <= cells <= MAX_CELLS or not 1 <= steps <= MAX_STEPS or not 1 <= hrus <= MAX_HRUS or spatial_subsamples not in {1,2,4}:
        raise ValueError("storm resource dimensions exceeded")
    work = active_cells*steps*spatial_subsamples**2
    estimated_bytes = 64*cells+32*active_cells+16*steps*hrus
    if work > MAX_WORK or estimated_bytes > MAX_BYTES:
        raise ValueError("storm work/byte budget exceeded before allocation")
    return {"spatial_evaluations": work, "estimated_peak_bytes": estimated_bytes,
            "max_evaluations": MAX_WORK, "max_bytes": MAX_BYTES}


def generate_forcing(cell_owner, *, origin_m_xz, spacing_m, steps, dt_s, start_s,
                     parameters, source_identity, selection_identity, spatial_subsamples=1):
    if (not isinstance(cell_owner, np.ndarray) or cell_owner.ndim != 2 or cell_owner.dtype != np.int64 or
            not 1 <= cell_owner.size <= MAX_CELLS or (cell_owner < -1).any()):
        raise ValueError("typed bounded unique HRU ownership required")
    active = cell_owner >= 0
    hrus = int(cell_owner.max())+1
    resources = preflight(int(cell_owner.size), int(active.sum()), steps, hrus, spatial_subsamples)
    if (not isinstance(origin_m_xz, (list,tuple)) or len(origin_m_xz) != 2 or
            any(type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1e12 for value in origin_m_xz) or
            type(spacing_m) not in (int,float) or not math.isfinite(spacing_m) or not 0 < spacing_m <= 100000 or
            type(dt_s) not in (int,float) or not math.isfinite(dt_s) or not 1e-3 <= dt_s <= 1e7 or
            type(start_s) not in (int,float) or not math.isfinite(start_s) or start_s < 0 or start_s+steps*dt_s > 1e9):
        raise ValueError("invalid absolute metre grid/time")
    for token in (source_identity, selection_identity):
        if not isinstance(token,str) or len(token) != 64:
            raise ValueError("external source and selection identities required")
    if not isinstance(parameters, StormParameters):
        raise ValueError("StormParameters required")
    parameters.__post_init__()
    rows, columns = np.nonzero(active)
    labels = cell_owner[active]
    counts = np.bincount(labels,minlength=hrus)
    if (counts == 0).any():
        raise ValueError("HRU labels must be contiguous and nonempty")
    rain = np.zeros((steps,hrus),np.float64)
    offsets = (np.arange(spatial_subsamples)+.5)/spatial_subsamples-.5
    for step in range(steps):
        lower = start_s+step*dt_s
        values = np.zeros(labels.size,np.float64)
        for delta_z in offsets:
            for delta_x in offsets:
                east = origin_m_xz[0]+(columns+delta_x)*spacing_m
                south = origin_m_xz[1]+(rows+delta_z)*spacing_m
                values += interval_mean_mm_h(east,south,lower,lower+dt_s,parameters)/spatial_subsamples**2
        rain[step] = np.bincount(labels,weights=values,minlength=hrus)/counts
    arrays = {"cell_owner": cell_owner.copy(), "counts": counts, "area_m2": counts.astype(np.float64)*spacing_m**2,
        "rain_mm_h": rain, "time_edges_s": start_s+np.arange(steps+1)*dt_s}
    metadata = {"schema":SCHEMA,"parameters":asdict(parameters),"origin_m_xz":list(origin_m_xz),
        "spacing_m":float(spacing_m),"dt_s":float(dt_s),"start_s":float(start_s),
        "spatial_subsamples":spatial_subsamples,"source_identity":source_identity,"selection_identity":selection_identity,
        "temporal_integration":"analytic_gaussian_erfc_with_4point_gauss_small_displacement",
        "spatial_integration":"equal_area_midpoint_subcells_no_window_normalization",
        "units":"coordinates m; physical time s; rain mm/h; area m2",
        "status":"parameterized_weather_scenario_not_forecast","resources":resources}
    result = {"arrays":arrays,"metadata":metadata,"identity_sha256":identity(arrays,metadata)}
    validate_forcing(result)
    result["arrays"] = {key:readonly(value) for key,value in arrays.items()}
    return result


def _headers(headers):
    keys = {"cell_owner","counts","area_m2","rain_mm_h","time_edges_s","manifest"}
    if set(headers) != keys:
        raise ValueError("weather archive member schema mismatch")
    shape,dtype = headers["cell_owner"]
    rain_shape,rain_dtype = headers["rain_mm_h"]
    if len(shape)!=2 or not 1 <= math.prod(shape)<=MAX_CELLS or dtype!=np.int64 or len(rain_shape)!=2 or rain_dtype!=np.float64:
        raise ValueError("weather typed grid/rain allocation rejected")
    steps,hrus = rain_shape
    if not 1<=steps<=MAX_STEPS or not 1<=hrus<=MAX_HRUS:
        raise ValueError("weather dimensions exceeded")
    for key,expected_shape,expected_dtype in (("counts",(hrus,),"int64"),("area_m2",(hrus,),"float64"),
            ("time_edges_s",(steps+1,),"float64")):
        if headers[key]!=(expected_shape,np.dtype(expected_dtype)):
            raise ValueError("weather vector header mismatch")
    manifest_shape,manifest_dtype=headers["manifest"]
    if len(manifest_shape)!=1 or not 1<=manifest_shape[0]<=65536 or manifest_dtype!=np.uint8:
        raise ValueError("weather metadata header rejected")


def validate_forcing(result, *, cell_owner=None, source_identity=None, selection_identity=None):
    arrays,meta=result["arrays"],result["metadata"]
    expected_meta={"schema","parameters","origin_m_xz","spacing_m","dt_s","start_s","spatial_subsamples",
        "source_identity","selection_identity","temporal_integration","spatial_integration","units","status","resources"}
    if set(meta)!=expected_meta or meta["schema"]!=SCHEMA or result["identity_sha256"]!=identity(arrays,meta):
        raise ValueError("weather metadata/identity mismatch")
    _headers(dict({key:(value.shape,value.dtype) for key,value in arrays.items()},manifest=((1,),np.dtype("uint8"))))
    parameters=StormParameters(**meta["parameters"])
    origin=meta["origin_m_xz"]
    if (not isinstance(origin,list) or len(origin)!=2 or
            any(type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e12 for value in origin)):
        raise ValueError("invalid saved absolute origin")
    for key,lower,upper in (("spacing_m",0.,100000.),("dt_s",0.,1e7),("start_s",-1.,1e9)):
        value=meta[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not lower<value<=upper:
            raise ValueError("invalid saved positive grid/time: "+key)
    if meta["dt_s"]<1e-3 or meta["start_s"]<0 or type(meta["spatial_subsamples"]) is not int:
        raise ValueError("invalid saved timestep/subsampling")
    for key in ("source_identity","selection_identity"):
        if not isinstance(meta[key],str) or len(meta[key])!=64:
            raise ValueError("invalid saved external identity")
    if (meta["temporal_integration"]!="analytic_gaussian_erfc_with_4point_gauss_small_displacement" or
            meta["spatial_integration"]!="equal_area_midpoint_subcells_no_window_normalization" or
            meta["units"]!="coordinates m; physical time s; rain mm/h; area m2" or
            meta["status"]!="parameterized_weather_scenario_not_forecast"):
        raise ValueError("weather semantic metadata mismatch")
    owner=arrays["cell_owner"]
    rain=arrays["rain_mm_h"]
    if meta["start_s"]+rain.shape[0]*meta["dt_s"]>1e9:
        raise ValueError("saved weather time range exceeded")
    if (owner < -1).any() or (owner >= rain.shape[1]).any() or not (owner>=0).any():
        raise ValueError("invalid saved unique HRU ownership")
    counts=np.bincount(owner[owner>=0],minlength=rain.shape[1])
    resources=preflight(int(owner.size),int(counts.sum()),rain.shape[0],rain.shape[1],meta["spatial_subsamples"])
    if resources!=meta["resources"] or (counts==0).any() or not np.array_equal(counts,arrays["counts"]):
        raise ValueError("weather area counts/resource certificate mismatch")
    if not np.array_equal(arrays["area_m2"],counts*meta["spacing_m"]**2):
        raise ValueError("weather unique area mismatch")
    if not np.array_equal(arrays["time_edges_s"],meta["start_s"]+np.arange(rain.shape[0]+1)*meta["dt_s"]):
        raise ValueError("weather physical time edges mismatch")
    if not np.isfinite(rain).all() or (rain<0).any() or (rain>parameters.peak_mm_h+1e-10).any():
        raise ValueError("invalid bounded saved weather rain")
    if cell_owner is not None and _hash(owner)!=_hash(cell_owner):
        raise ValueError("external unique HRU ownership mismatch")
    if source_identity is not None and source_identity!=meta["source_identity"]:
        raise ValueError("external weather source mismatch")
    if selection_identity is not None and selection_identity!=meta["selection_identity"]:
        raise ValueError("external weather selection mismatch")
    return {"total_rain_m3":float((rain*arrays["area_m2"]).sum()*meta["dt_s"]/3600/1000),
        "area_m2":float(arrays["area_m2"].sum()),"max_rain_mm_h":float(rain.max())}


def save_forcing(path,result):
    save_bundle(path,result,validator=validate_forcing)


def load_forcing(path, *, expected_sha256, cell_owner, source_identity, selection_identity):
    """Read saved forcing with external trust; never regenerate weather at load time."""
    return load_bundle(path,expected_sha256=expected_sha256,max_bytes=MAX_BYTES,header_validator=_headers,
        validator=lambda result:validate_forcing(result,cell_owner=cell_owner,
            source_identity=source_identity,selection_identity=selection_identity))
