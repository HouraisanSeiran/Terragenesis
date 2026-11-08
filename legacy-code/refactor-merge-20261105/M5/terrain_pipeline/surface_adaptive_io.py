"""Bounded adaptive saved evidence IO; imports no adaptive execution helpers."""

import hashlib
import json
import math
from collections.abc import Mapping,Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity, save_bundle, load_bundle, file_sha256, publish_bytes
from terrain_pipeline.runoff import _strict_json as _strict_json

MODEL = "single-domain-adaptive-canonical-HLL-Manning-SSPRK2-v1"
FLAGS = ("hydraulic_ready","natural_outlet_verified","publishable")
MAX_BYTES = 268435456


def near(actual,expected,label):
    if np.shape(actual)!=np.shape(expected) or not np.isfinite(actual).all() or not np.isfinite(expected).all() or not np.allclose(actual,expected,atol=2e-9,rtol=2e-11):
        raise ValueError("adaptive saved "+label+" mismatch")


def geometry_identity(arrays,metadata):
    digest = hashlib.sha256(json.dumps(metadata,sort_keys=True).encode("ascii"))
    for name in sorted(arrays):
        value = arrays[name]
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape,np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def validate_geometry(geometry):
    a,m = geometry["arrays"],geometry["metadata"]
    if m.get("model")!=MODEL or geometry_identity(a,m)!=geometry["identity_sha256"]:
        raise ValueError("adaptive raw geometry model/identity mismatch")
    bed = a["canonical_bed_m"]
    if bed.dtype!=np.float64 or bed.ndim!=2 or not np.isfinite(bed).all() or bed.size>65536 or any(size%4 for size in bed.shape):
        raise ValueError("adaptive canonical geometry budget/type mismatch")
    rows,columns = bed.shape
    n = len(a["leaf_row"])
    expected_names = {"canonical_bed_m","requested_spacing_m","leaf_row","leaf_column","leaf_spacing_m","leaf_area_m2","canonical_owner","subcell_count","subcell_offset", "sorted_subcell_bed_relative_m","prefix_subcell_bed_relative_m","face_left","face_right","face_axis","face_canonical_row","face_canonical_column","face_crest_relative_m","boundary_cell","boundary_axis","boundary_sign","boundary_kind","boundary_crest_m","boundary_bed_relative_m"}
    if set(a)!=expected_names or m["hydraulic_datum_m"]!=float(bed.min()) or not 1<=n<=bed.size:
        raise ValueError("adaptive exact geometry fields/datum mismatch")
    integers = {"requested_spacing_m","leaf_row","leaf_column","leaf_spacing_m","canonical_owner","subcell_count","subcell_offset","face_left","face_right","face_axis","face_canonical_row","face_canonical_column","boundary_cell","boundary_axis","boundary_kind"}
    if any(value.dtype!=(np.int64 if name in integers else np.float64) or not np.isfinite(value).all() for name,value in a.items()) or not np.isin(a["face_axis"],[0,1]).all():
        raise ValueError("adaptive exact geometry dtypes/axes/finite mismatch")
    if any(a[name].shape!=(n,) for name in ("leaf_row","leaf_column","leaf_spacing_m","leaf_area_m2","subcell_count","subcell_offset")):
        raise ValueError("adaptive exact leaf field shape mismatch")
    owner = np.full(bed.shape,-1,np.int64)
    coverage = np.zeros(bed.shape,np.int64)
    sorted_bed,prefix = np.zeros(bed.size),np.zeros(bed.size)
    offsets = np.r_[0,np.cumsum(a["subcell_count"])[:-1]]
    if not np.array_equal(a["subcell_offset"],offsets):
        raise ValueError("adaptive compact canonical offsets mismatch")
    for leaf,(row,column,size) in enumerate(zip(a["leaf_row"],a["leaf_column"],a["leaf_spacing_m"])):
        if size not in (1,2,4) or row<0 or column<0 or row%size or column%size or row+size>rows or column+size>columns:
            raise ValueError("adaptive aligned leaf bounds mismatch")
        patch = (slice(row,row+size),slice(column,column+size))
        coverage[patch] += 1
        owner[patch] = leaf
        samples = np.sort((bed[patch]-m["hydraulic_datum_m"]).ravel())
        offset = offsets[leaf]
        sorted_bed[offset:offset+size*size] = samples
        prefix[offset:offset+size*size] = np.cumsum(samples)
    if np.any(coverage!=1) or not np.array_equal(owner,a["canonical_owner"]):
        raise ValueError("adaptive entire canonical leaf partition mismatch")
    if not np.array_equal(a["subcell_count"],a["leaf_spacing_m"]**2) or not np.array_equal(a["leaf_area_m2"],a["leaf_spacing_m"].astype(float)**2):
        raise ValueError("adaptive exact leaf area/count mismatch")
    near(a["sorted_subcell_bed_relative_m"],sorted_bed,"canonical sorted support")
    near(a["prefix_subcell_bed_relative_m"],prefix,"canonical prefix support")
    requests = a["requested_spacing_m"]
    if requests.shape!=bed.shape or requests.dtype!=np.int64 or not np.isin(requests,[1,2,4]).all():
        raise ValueError("adaptive requested spacing declaration mismatch")
    for direction in (0,1):
        before,after = (owner[:,:-1],owner[:,1:]) if direction==0 else (owner[:-1],owner[1:])
        mask = before!=after
        row,column = np.nonzero(mask)
        selected = a["face_axis"]==direction
        expected_row,expected_column = (row,column+1) if direction==0 else (row+1,column)
        for name,expected in (("face_left",before[mask]),("face_right",after[mask]),("face_canonical_row",expected_row),("face_canonical_column",expected_column)):
            if not np.array_equal(a[name][selected],expected):
                raise ValueError("adaptive unique complete canonical segment "+name+" mismatch")
        adjacent_first,adjacent_second = (bed[:,:-1],bed[:,1:]) if direction==0 else (bed[:-1],bed[1:])
        near(a["face_crest_relative_m"][selected],np.maximum(adjacent_first,adjacent_second)[mask]-m["hydraulic_datum_m"],"canonical segment crest")
    boundary = np.r_[owner[:,0],owner[:,-1],owner[0],owner[-1]]
    bbed = np.r_[bed[:,0],bed[:,-1],bed[0],bed[-1]]
    for name,expected in (("boundary_cell",boundary),("boundary_axis",np.r_[np.zeros(2*rows,np.int64),np.ones(2*columns,np.int64)]),("boundary_sign",np.r_[-np.ones(rows),np.ones(rows),-np.ones(columns),np.ones(columns)])):
        if not np.array_equal(a[name],expected):
            raise ValueError("adaptive canonical boundary incidence mismatch")
    near(a["boundary_bed_relative_m"],bbed-m["hydraulic_datum_m"],"boundary bed")
    if a["boundary_kind"].dtype!=np.int64 or a["boundary_kind"].shape!=boundary.shape or not np.isin(a["boundary_kind"],[0,1,2]).all() or np.any(a["boundary_crest_m"]<bbed):
        raise ValueError("adaptive complete boundary declaration mismatch")
    for size in (1,2,4):
        count = int(np.sum(a["leaf_spacing_m"]==size))
        if m["leaf_counts"][str(size)]!=count or m["leaf_area_m2"][str(size)]!=count*size**2:
            raise ValueError("adaptive leaf occupancy metadata mismatch")
    for name,expected in (("leaf_count",n),("total_area_m2",bed.size),("internal_segment_count",len(a["face_left"])),("boundary_segment_count",len(boundary)),("canonical_shape",list(bed.shape))):
        if m[name]!=expected:
            raise ValueError("adaptive complete geometry metadata mismatch")
    if m.get("full_selected_window_covered") is not True or m.get("uniform_coarse_convergence_claim") is not False:
        raise ValueError("adaptive unsupported geometry claim")
    return True


def storage_stage(depth,geometry):
    a = geometry["arrays"]
    answer = np.empty(len(depth))
    counts,offsets = a["subcell_count"],a["subcell_offset"]
    bed,prefix = a["sorted_subcell_bed_relative_m"],a["prefix_subcell_bed_relative_m"]
    for count in np.unique(counts):
        cells = np.flatnonzero(counts==count)
        if count==1:
            answer[cells] = depth[cells]+prefix[offsets[cells]]
            continue
        indices = offsets[cells,None]+np.arange(count)
        volume = depth[cells]*count
        wet = np.maximum(np.count_nonzero(volume[:,None]>=np.arange(1,count+1)*bed[indices]-prefix[indices],axis=1),1)
        answer[cells] = (volume+prefix[indices[np.arange(len(cells)),wet-1]])/wet
    return answer


def validate_snapshot(snapshot,geometry):
    a = geometry["arrays"]
    n,shape = len(a["leaf_row"]),a["canonical_bed_m"].shape
    expected = {"state":(n,3),"leaf_row":(n,),"leaf_column":(n,),"leaf_spacing_m":(n,),"canonical_owner":shape,
                "leaf_stage_relative_m":(n,),"canonical_depth_m":shape,"canonical_momentum_m2_s":(*shape,2)}
    arrays = {name:value for name,value in snapshot.items() if isinstance(value,np.ndarray)}
    if set(arrays)!=set(expected) or any(value.shape!=expected[name] or not np.isfinite(value).all() for name,value in arrays.items()):
        raise ValueError("adaptive exact snapshot layout mismatch")
    if snapshot["geometry_identity"]!=geometry["identity_sha256"] or np.any(snapshot["state"][:,0]<0):
        raise ValueError("adaptive snapshot source/depth mismatch")
    if snapshot["leaf_counts"]!=geometry["metadata"]["leaf_counts"] or snapshot["leaf_area_m2"]!=geometry["metadata"]["leaf_area_m2"]:
        raise ValueError("adaptive snapshot leaf occupancy declaration mismatch")
    for name in ("leaf_row","leaf_column","leaf_spacing_m","canonical_owner"):
        if arrays[name].dtype!=np.int64 or not np.array_equal(arrays[name],a[name]):
            raise ValueError("adaptive exact snapshot leaf geometry mismatch")
    for name in set(arrays)-{"leaf_row","leaf_column","leaf_spacing_m","canonical_owner"}:
        if arrays[name].dtype!=np.float64:
            raise ValueError("adaptive exact snapshot floating type mismatch")
    state = snapshot["state"]
    stage = storage_stage(state[:,0],geometry)
    near(snapshot["leaf_stage_relative_m"],stage,"snapshot inverse storage")
    owner = a["canonical_owner"]
    depth = np.maximum(stage[owner]-(a["canonical_bed_m"]-geometry["metadata"]["hydraulic_datum_m"]),0)
    velocity = np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0)
    near(snapshot["canonical_depth_m"],depth,"snapshot canonical inventory")
    near(snapshot["canonical_momentum_m2_s"],depth[:,:,None]*velocity[owner],"snapshot canonical momentum inventory")
    near(np.bincount(owner.ravel(),weights=depth.ravel(),minlength=len(state)),state[:,0]*a["leaf_area_m2"],"snapshot leaf storage")
    return True


def _bundle(item,schema):
    arrays = {name:value for name,value in item.items() if isinstance(value,np.ndarray)}
    metadata = {name:value for name,value in item.items() if not isinstance(value,np.ndarray)}
    metadata.update(schema=schema,**{name:False for name in FLAGS})
    return dict(arrays=arrays,metadata=metadata,identity_sha256=identity(arrays,metadata))


def _unpack(bundle):
    return dict(bundle["metadata"],**bundle["arrays"])


def _record(path,bundle):
    return dict(path=str(path.resolve()),expected_sha256=file_sha256(path),expected_identity=bundle["identity_sha256"])


def _headers(headers):
    for name,(shape,dtype) in headers.items():
        if name=="manifest":
            if dtype!=np.uint8 or len(shape)!=1 or math.prod(shape)>1048576:
                raise ValueError("adaptive bounded manifest required")
        elif dtype not in (np.dtype("float64"),np.dtype("int64"),np.dtype("bool")) or math.prod(shape)>2000000:
            raise ValueError("adaptive bounded array headers required")


def _load(record,root,expected_name,schema):
    path = Path(record["path"]).resolve(strict=True)
    if path != (root/expected_name).resolve(strict=True) or not path.is_relative_to(root):
        raise ValueError("adaptive exact saved layout mismatch")
    result = load_bundle(path,expected_sha256=record["expected_sha256"],max_bytes=MAX_BYTES,header_validator=_headers,validator=lambda item:True)
    if (result["identity_sha256"]!=record["expected_identity"] or result["metadata"].get("schema")!=schema
            or any(result["metadata"].get(name) is not False for name in FLAGS)
            or any(not np.isfinite(value).all() for value in result["arrays"].values())):
        raise ValueError("adaptive saved identity/schema/finite/flags mismatch")
    return result


def _source_binding(source,canonical,forcing,snapshots,first_geometry):
    """Bind copied schedules to the original saved fine run, with explicit lake override."""
    source_path = Path(source["path"])
    if source_path.suffix!=".json":
        return "external canonical source; independent provenance audit required"
    original = _strict_json(source_path.read_text(encoding="utf-8"))
    if original.get("schema")!="single-domain-fine-run-index-v1":
        return "external canonical source; independent provenance audit required"
    def read(record):
        result = load_bundle(record["path"],expected_sha256=record["expected_sha256"],max_bytes=MAX_BYTES,header_validator=_headers,validator=lambda item:True)
        if result["identity_sha256"]!=record["expected_identity"]:
            raise ValueError("adaptive original fine source identity mismatch")
        return result
    bed = read(original["bed_record"])
    if not np.array_equal(bed["arrays"]["canonical_bed_center_m"],canonical["arrays"]["canonical_bed_m"]):
        raise ValueError("adaptive original canonical bed witness mismatch")
    source_forcing,source_states,source_geometry = read(original["forcing"]),read(original["states"]),read(original["geometry"])
    shape = first_geometry["arrays"]["canonical_bed_m"].shape
    near(snapshots[0]["canonical_depth_m"],source_states["arrays"]["initial_depth_m"].reshape(shape),"original canonical initial inventory")
    near(forcing["tailwater_m"],source_forcing["arrays"]["boundary_stage_m"],"original prescribed stage schedule")
    near(np.asarray(forcing["dt_s"]),np.asarray(source_forcing["metadata"]["dt_s"]),"original forcing interval")
    original_q = source_forcing["arrays"]["local_q_m3_s"].reshape(forcing["forcing_m3_s"].shape)
    if np.array_equal(forcing["forcing_m3_s"],original_q) and np.array_equal(first_geometry["arrays"]["boundary_kind"],source_geometry["arrays"]["boundary_kind"]):
        return "original saved canonical source/time schedule"
    if np.all(forcing["forcing_m3_s"]==0) and np.all(first_geometry["arrays"]["boundary_kind"]==0):
        return "explicit zero-source closed lake correction of prior soil-release case"
    raise ValueError("adaptive original hydraulic forcing/boundary schedule changed")


class SavedGeometryMapping(Mapping):
    """Load at most two historical meshes, keeping cold-read memory bounded."""
    def __init__(self,records,root):
        self.records,self.root = records,root
    __hash__ = object.__hash__
    def __len__(self):
        return len(self.records)
    def __iter__(self):
        return iter(self.records)
    @lru_cache(maxsize=2)
    def __getitem__(self,key):
        record = self.records[key]
        name = Path(record["path"]).name
        if not name.startswith("geometry-") or not name.endswith(".npz"):
            raise ValueError("adaptive geometry history filename mismatch")
        bundle = _load(record,self.root,name,"surface-adaptive-geometry-v1")
        geometry = dict(arrays=bundle["arrays"],metadata=bundle["metadata"]["raw_geometry_metadata"],identity_sha256=bundle["metadata"]["raw_geometry_identity"])
        if key!=geometry["identity_sha256"]:
            raise ValueError("adaptive historical geometry binding mismatch")
        validate_geometry(geometry)
        return geometry


class SavedRecordSequence(Sequence):
    def __init__(self,records,root,prefix,schema,digits):
        self.records,self.root,self.prefix,self.schema,self.digits = records,root,prefix,schema,digits
    def __len__(self):
        return len(self.records)
    def __getitem__(self,number):
        if isinstance(number,slice):
            return [self[index] for index in range(*number.indices(len(self)))]
        if number<0:
            number += len(self)
        record = self.records[number]
        return _unpack(_load(record,self.root,f"{self.prefix}-{number:0{self.digits}d}.npz",self.schema))


def validate_epoch(packet,geometry):
    a = geometry["arrays"]
    n,f,b = len(a["leaf_row"]),len(a["face_left"]),len(a["boundary_cell"])
    shapes = dict(state_before=(n,3),state_after=(n,3),internal_transfer=(f,3),boundary_transfer=(b,3),
        bed_impulse=(n,2),manning_impulse=(n,2),forcing_volume_m3=(n,),internal_q_after_m3_s=(f,),boundary_q_after_m3_s=(b,))
    arrays = {name:value for name,value in packet.items() if isinstance(value,np.ndarray)}
    if set(arrays)!=set(shapes) or any(value.dtype!=np.float64 or value.shape!=shapes[name] or not np.isfinite(value).all() for name,value in arrays.items()):
        raise ValueError("adaptive exact epoch arrays mismatch")
    if packet["geometry_identity"]!=geometry["identity_sha256"] or not packet["time_start_s"]<packet["time_end_s"] or np.any(packet["state_before"][:,0]<0) or np.any(packet["state_after"][:,0]<0) or np.any(packet["forcing_volume_m3"]<0):
        raise ValueError("adaptive epoch identity/time/depth mismatch")
    change = np.zeros((n,3))
    np.add.at(change,a["face_left"],-packet["internal_transfer"])
    np.add.at(change,a["face_right"],packet["internal_transfer"])
    np.add.at(change,a["boundary_cell"],-packet["boundary_transfer"])
    change[:,0] += packet["forcing_volume_m3"]
    change[:,1:] += packet["bed_impulse"]+packet["manning_impulse"]
    near((packet["state_after"]-packet["state_before"])*a["leaf_area_m2"][:,None],change,"complete epoch water/momentum closure")
    closed = a["boundary_kind"]==0
    if np.any(packet["boundary_transfer"][closed,0]!=0) or np.any(packet["boundary_q_after_m3_s"][closed]!=0):
        raise ValueError("adaptive closed boundary mass transfer")
    return True


def apply_transaction(packet,before_geometry,after_geometry,before_state):
    a,b = before_geometry["arrays"],after_geometry["arrays"]
    if packet["before_geometry_identity"]!=before_geometry["identity_sha256"] or packet["after_geometry_identity"]!=after_geometry["identity_sha256"] or not np.array_equal(a["canonical_bed_m"],b["canonical_bed_m"]):
        raise ValueError("adaptive refinement original geometry binding mismatch")
    parent = a["canonical_owner"][b["leaf_row"],b["leaf_column"]]
    unchanged = b["leaf_spacing_m"]==a["leaf_spacing_m"][parent]
    child_ids = np.flatnonzero(~unchanged)
    parent_ids = np.unique(parent[~unchanged])
    for name,expected in (("parent_leaf_id",parent[~unchanged]),("refined_parent_leaf_id",parent_ids),("refined_child_leaf_id",child_ids),
            ("unchanged_parent_leaf_id",parent[unchanged]),("unchanged_child_leaf_id",np.flatnonzero(unchanged))):
        if not np.array_equal(packet[name],expected):
            raise ValueError("adaptive sparse refinement mapping mismatch")
    if np.any(b["leaf_spacing_m"]>a["leaf_spacing_m"][parent]):
        raise ValueError("adaptive refinement cannot coarsen")
    stage = storage_stage(before_state[:,0],before_geometry)
    depth = np.maximum(stage[a["canonical_owner"]]-(a["canonical_bed_m"]-before_geometry["metadata"]["hydraulic_datum_m"]),0)
    velocity = np.divide(before_state[:,1:],before_state[:,0,None],out=np.zeros_like(before_state[:,1:]),where=before_state[:,0,None]>0)
    momentum = depth[:,:,None]*velocity[a["canonical_owner"]]
    next_state = np.empty((len(parent),3))
    next_state[unchanged] = before_state[parent[unchanged]]
    for child in child_ids:
        row,column,size = b["leaf_row"][child],b["leaf_column"][child],b["leaf_spacing_m"][child]
        patch = (slice(row,row+size),slice(column,column+size))
        next_state[child,0] = depth[patch].mean()
        next_state[child,1:] = momentum[patch].mean(axis=(0,1))
    before_inventory = before_state*a["leaf_area_m2"][:,None]
    after_inventory = next_state*b["leaf_area_m2"][:,None]
    near(packet["parent_inventory_m3_m4_s"],before_inventory[parent_ids],"refinement saved parent inventory")
    near(packet["child_inventory_m3_m4_s"],after_inventory[child_ids],"refinement saved child inventory")
    grouped = np.zeros_like(before_inventory)
    np.add.at(grouped,parent,after_inventory)
    near(grouped,before_inventory,"refinement complete inventory conservation")
    near(packet["parent_grouped_residual"],(grouped-before_inventory)[parent_ids],"refinement declared residual")
    return next_state


def save_adaptive_run(path,result,*,forcing_m3_s,tailwater_m,forcing_interval_s,budget,source_record,code_sha256,code_records=None,resource_observer=None):
    """Save only snapshots, geometry epochs and sampled steps, never all substeps."""
    root = Path(path).resolve()
    root.mkdir(parents=True,exist_ok=False)
    geometries = result["geometries"]
    records = {}
    def write(name,item,schema):
        bundle = _bundle(item,schema)
        target = root/name
        save_bundle(target,bundle,validator=lambda value:True)
        record = _record(target,bundle)
        _load(record,root,name,schema)
        if resource_observer is not None:
            resource_observer()
        return record
    def load_original_record(record,schema):
        item = _unpack(_load(record,root,Path(record["path"]).name,schema))
        for name in ("schema",*FLAGS):
            item.pop(name,None)
        return item
    def bind_record(collection,number,record,schema):
        if hasattr(collection,"bind_saved_record"):
            collection.bind_saved_record(number,record,lambda pin:load_original_record(pin,schema))
            if resource_observer is not None:
                resource_observer()
    def load_original_geometry(record):
        bundle = _load(record,root,Path(record["path"]).name,"surface-adaptive-geometry-v1")
        geometry = dict(arrays=bundle["arrays"],metadata=bundle["metadata"]["raw_geometry_metadata"],
            identity_sha256=bundle["metadata"]["raw_geometry_identity"])
        # Publication already checked the partition; this immutable pin binds that proof.
        if geometry_identity(geometry["arrays"],geometry["metadata"])!=geometry["identity_sha256"]:
            raise ValueError("adaptive archived original geometry identity mismatch")
        return geometry
    for number,(key,geometry) in enumerate(geometries.items()):
        validate_geometry(geometry)
        if key!=geometry["identity_sha256"]:
            raise ValueError("adaptive geometry history key mismatch")
        records[key] = write(f"geometry-{number:04d}.npz",dict(geometry["arrays"],raw_geometry_metadata=geometry["metadata"],raw_geometry_identity=key),"surface-adaptive-geometry-v1")
        if hasattr(geometries,"bind_saved_geometry"):
            geometries.bind_saved_geometry(key,records[key],load_original_geometry)
            if resource_observer is not None:
                resource_observer()
    snapshots = []
    for number,item in enumerate(result["snapshots"]):
        validate_snapshot(item,geometries[item["geometry_identity"]])
        record = write(f"snapshot-{number:03d}.npz",item,"surface-adaptive-canonical-snapshot-v1")
        snapshots.append(record)
        bind_record(result["snapshots"],number,record,"surface-adaptive-canonical-snapshot-v1")
    epochs = []
    for number,item in enumerate(result["epoch_packets"]):
        validate_epoch(item,geometries[item["geometry_identity"]])
        record = write(f"epoch-{number:04d}.npz",item,"surface-adaptive-epoch-v1")
        epochs.append(record)
        bind_record(result["epoch_packets"],number,record,"surface-adaptive-epoch-v1")
    def write_sequence(collection,prefix,schema,digits):
        records = []
        for number,item in enumerate(collection):
            record = write(f"{prefix}-{number:0{digits}d}.npz",item,schema)
            records.append(record)
            bind_record(collection,number,record,schema)
        return records
    transactions = write_sequence(result["refinement_transactions"],"refinement","surface-adaptive-refinement-v1",4)
    steps = write_sequence(result["first_rk_packets"],"step","surface-adaptive-first-step-v1",3)
    forcing = write("forcing.npz",dict(forcing_m3_s=np.asarray(forcing_m3_s),tailwater_m=np.asarray(tailwater_m),dt_s=forcing_interval_s),"surface-adaptive-forcing-v1")
    first_geometry = geometries[result["snapshots"][0]["geometry_identity"]]
    canonical_source = write("canonical-source.npz",dict(canonical_bed_m=first_geometry["arrays"]["canonical_bed_m"],
        origin_m_xz=first_geometry["metadata"]["origin_m_xz"],source_record=source_record),"surface-adaptive-canonical-source-v1")
    states = write("ledger.npz",dict(ledger=result["ledger"],solver_metadata=result["metadata"],interval_ledgers=result["interval_ledgers"]),"surface-adaptive-ledger-v1")
    if sum(target.stat().st_size for target in root.iterdir())>2147483648:
        raise ValueError("adaptive saved output exceeds 2GiB")
    index = dict(schema="surface-adaptive-run-index-v1",model=MODEL,geometries=records,snapshots=snapshots,epochs=epochs,
        refinements=transactions,first_steps=steps,forcing=forcing,canonical_source=canonical_source,states=states,budget=vars(budget) if hasattr(budget,"__dict__") else budget,
        source_record=source_record,code_sha256=code_sha256,equations_sampled=True,all_substep_states_saved=False,
        stage_accepted=False,uniform_coarse_convergence_claim=False,**{name:False for name in FLAGS})
    if code_records is not None:
        index["code_records"] = code_records
    target = root/"index.json"
    publish_bytes(target,(json.dumps(index,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    if resource_observer is not None:
        resource_observer()
    pin = dict(path=str(target),expected_sha256=file_sha256(target))
    load_adaptive_run(target,expected_sha256=pin["expected_sha256"])
    return pin


def load_adaptive_run(path,*,expected_sha256):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size>8*1024**2 or file_sha256(path)!=expected_sha256:
        raise ValueError("adaptive index external hash/budget mismatch")
    index = _strict_json(path.read_text(encoding="utf-8"))
    root = path.parent
    if (index.get("schema")!="surface-adaptive-run-index-v1" or index.get("model")!=MODEL or any(index.get(name) is not False for name in FLAGS)
            or index.get("stage_accepted") is not False or index.get("uniform_coarse_convergence_claim") is not False):
        raise ValueError("adaptive unsupported index schema/claim")
    if not isinstance(index.get("code_sha256"),dict) or not index["code_sha256"] or not index["geometries"]:
        raise ValueError("adaptive frozen implementation and historical geometry pins required")
    records = list(index["geometries"].values())+index["snapshots"]+index["epochs"]+index["refinements"]+index["first_steps"]+[index["forcing"],index["canonical_source"],index["states"]]
    if sum(Path(record["path"]).stat().st_size for record in records)>2147483648 or any(Path(record["path"]).stat().st_size>MAX_BYTES for record in records):
        raise ValueError("adaptive saved archive output/artifact budgets exceeded")
    from terrain_pipeline.single_domain_fine_io import _validate_code_records
    if "code_records" in index:
        _validate_code_records(index["code_sha256"],index["code_records"],root.parent)
    else:
        repository = Path(__file__).resolve().parents[1]
        for name,digest in index["code_sha256"].items():
            target = (repository/name).resolve(strict=True)
            if not target.is_relative_to(repository) or file_sha256(target)!=digest:
                raise ValueError("adaptive current implementation pin mismatch")
    source = index["source_record"]
    if file_sha256(source["path"])!=source["expected_sha256"]:
        raise ValueError("adaptive original canonical source hash mismatch")
    geometries = SavedGeometryMapping(index["geometries"],root)
    canonical_source = _load(index["canonical_source"],root,"canonical-source.npz","surface-adaptive-canonical-source-v1")
    for key in geometries:
        geometry = geometries[key]
        if (not np.array_equal(geometry["arrays"]["canonical_bed_m"],canonical_source["arrays"]["canonical_bed_m"])
                or geometry["metadata"]["origin_m_xz"]!=canonical_source["metadata"]["origin_m_xz"]
                or canonical_source["metadata"]["source_record"]!=source):
            raise ValueError("adaptive complete geometry original canonical source mismatch")
    def read_sequence(role,prefix,schema):
        return SavedRecordSequence(index[role],root,prefix,schema,3 if role in ("snapshots","first_steps") else 4)
    snapshots = read_sequence("snapshots","snapshot","surface-adaptive-canonical-snapshot-v1")
    epochs = read_sequence("epochs","epoch","surface-adaptive-epoch-v1")
    transactions = read_sequence("refinements","refinement","surface-adaptive-refinement-v1")
    steps = read_sequence("first_steps","step","surface-adaptive-first-step-v1")
    forcing = _unpack(_load(index["forcing"],root,"forcing.npz","surface-adaptive-forcing-v1"))
    states = _unpack(_load(index["states"],root,"ledger.npz","surface-adaptive-ledger-v1"))
    n = len(steps)
    first_geometry = geometries[snapshots[0]["geometry_identity"]]
    shape = first_geometry["arrays"]["canonical_bed_m"].shape
    dt = forcing["dt_s"]
    if not 1<=n<=48 or len(snapshots)!=n+1 or forcing["forcing_m3_s"].dtype!=np.float64 or forcing["tailwater_m"].dtype!=np.float64 or np.any(forcing["forcing_m3_s"]<0) or forcing["forcing_m3_s"].shape!=(n,*shape) or forcing["tailwater_m"].shape!=(n,2*sum(shape)) or not 0<dt<=3600:
        raise ValueError("adaptive complete bounded forcing/snapshot coverage mismatch")
    for number,snapshot in enumerate(snapshots):
        near(np.asarray(snapshot["time_s"]),np.asarray(number*dt),"snapshot physical time")
        validate_snapshot(snapshot,geometries[snapshot["geometry_identity"]])
        if np.any(snapshot["state"][:,0]>index["budget"]["max_depth_m"]) or len(snapshot["state"])>index["budget"]["max_cells"]:
            raise ValueError("adaptive snapshot depth/active-leaf budget exceeded")
    _verify_chain(index,geometries,snapshots,epochs,transactions,steps,forcing,states)
    source_semantics = _source_binding(source,canonical_source,forcing,snapshots,first_geometry)
    if file_sha256(path)!=expected_sha256:
        raise ValueError("adaptive index changed during load")
    return dict(index=index,geometries=geometries,snapshots=snapshots,epochs=epochs,refinements=transactions,first_steps=steps,
        forcing=forcing,canonical_source=canonical_source,states=states,source_semantics=source_semantics,solver_advanced=False,equations_sampled=True)


def _verify_chain(index,geometries,snapshots,epochs,transactions,steps,forcing,states):
    dt,n = forcing["dt_s"],len(steps)
    budget = index["budget"]
    if budget["max_wall_s"]>1800 or budget["max_bytes"]>MAX_BYTES or budget["max_cells"]>65536:
        raise ValueError("adaptive predeclared budget mismatch")
    metadata = states["solver_metadata"]
    if metadata["status"]!="completed" or metadata["model"]!=MODEL or metadata["wall_s"]>1800 or metadata["substeps"]>budget["max_substeps"] or metadata["face_evaluations"]>budget["max_face_evaluations"]:
        raise ValueError("adaptive complete solver work mismatch")
    key = snapshots[0]["geometry_identity"]
    current = snapshots[0]["state"]
    time = 0.
    transaction_number = 0
    seen_intervals = set()
    supplies = np.zeros(n)
    boundaries = np.zeros(n)
    for epoch in epochs:
        interval = epoch["interval"]
        if type(interval) is not int or not 0<=interval<n or abs(epoch["time_start_s"]-time)>1e-9 or epoch["time_end_s"]>(interval+1)*dt+1e-9:
            raise ValueError("adaptive uninterrupted epoch timeline mismatch")
        while transaction_number<len(transactions) and abs(transactions[transaction_number]["time_s"]-time)<=1e-9:
            transaction = transactions[transaction_number]
            if transaction["interval"]!=interval or transaction["before_geometry_identity"]!=key:
                raise ValueError("adaptive transaction time/source chain mismatch")
            after_key = transaction["after_geometry_identity"]
            current = apply_transaction(transaction,geometries[key],geometries[after_key],current)
            key = after_key
            transaction_number += 1
        if epoch["geometry_identity"]!=key:
            raise ValueError("adaptive epoch geometry chain mismatch")
        geometry = geometries[key]
        validate_epoch(epoch,geometry)
        near(epoch["state_before"],current,"epoch original state continuity")
        a = geometry["arrays"]
        duration = epoch["time_end_s"]-epoch["time_start_s"]
        source = np.bincount(a["canonical_owner"].ravel(),weights=forcing["forcing_m3_s"][interval].ravel(),minlength=len(current))
        near(epoch["forcing_volume_m3"],duration*source,"epoch complete canonical forcing")
        supplies[interval] += epoch["forcing_volume_m3"].sum()
        boundaries[interval] += epoch["boundary_transfer"][:,0].sum()
        if interval not in seen_intervals:
            step = steps[interval]
            if step["interval"]!=interval or step["geometry_identity"]!=key or abs(step["time_start_s"]-time)>1e-9:
                raise ValueError("adaptive complete first-step source/time binding")
            near(step["state_before"],current,"first-step original epoch state")
            near(step["forcing_m3_s"],source,"first-step forcing")
            near(step["tailwater_m"],forcing["tailwater_m"][interval],"first-step tailwater")
            _validate_step_algebra(step,geometry,budget)
            seen_intervals.add(interval)
        current,time = epoch["state_after"],epoch["time_end_s"]
        if abs(time-(interval+1)*dt)<=1e-9:
            snapshot = snapshots[interval+1]
            if snapshot["geometry_identity"]!=key:
                raise ValueError("adaptive interval end original geometry mismatch")
            near(snapshot["state"],current,"interval end original snapshot state")
    if abs(time-n*dt)>1e-9 or transaction_number!=len(transactions) or seen_intervals!=set(range(n)):
        raise ValueError("adaptive full epoch/refinement/interval coverage mismatch")
    ledger = states["ledger"]
    if ledger.dtype!=np.float64 or ledger.shape!=(n+1,5):
        raise ValueError("adaptive exact cumulative ledger shape mismatch")
    volumes = np.array([np.sum(snapshot["state"][:,0]*geometries[snapshot["geometry_identity"]]["arrays"]["leaf_area_m2"]) for snapshot in snapshots])
    near(ledger[:,0],np.r_[0,np.cumsum(supplies)],"complete ledger supply")
    near(ledger[:,3],volumes,"snapshot ledger volume")
    near(np.diff(ledger[:,2])-np.diff(ledger[:,1]),boundaries,"signed boundary ledger")
    near(ledger[:,4],volumes-volumes[0]-ledger[:,0]-ledger[:,1]+ledger[:,2],"ledger residual")
    near(ledger[:,4],np.zeros(n+1),"whole water budget")


def _validate_step_algebra(packet,geometry,budget):
    a = geometry["arrays"]
    n,f,b = len(a["leaf_row"]),len(a["face_left"]),len(a["boundary_cell"])
    shapes = dict(state_before=(n,3),state_predictor=(n,3),state_after=(n,3),manning_momentum_change=(n,2),
        manning_inverse_depth_third_mean=(n,),leaf_area_m2=(n,),face_left=(f,),face_right=(f,),face_axis=(f,),face_crest_relative_m=(f,),
        boundary_cell=(b,),forcing_m3_s=(n,),tailwater_m=(b,))
    for rk in (1,2):
        shapes.update({f"rk{rk}_internal_flux":(f,3),f"rk{rk}_boundary_flux":(b,3),f"rk{rk}_bed_source":(n,3)})
    arrays = {name:value for name,value in packet.items() if isinstance(value,np.ndarray)}
    if set(arrays)!=set(shapes) or any(value.shape!=shapes[name] or not np.isfinite(value).all() for name,value in arrays.items()):
        raise ValueError("adaptive exact first-step arrays mismatch")
    for name,value in arrays.items():
        expected_dtype = np.int64 if name in ("face_left","face_right","face_axis","boundary_cell") else np.float64
        if value.dtype!=expected_dtype:
            raise ValueError("adaptive exact first-step array dtype mismatch")
    if any(np.any(packet[name][:,0]<0) or np.any(packet[name][:,0]>budget["max_depth_m"]) for name in ("state_before","state_predictor","state_after")):
        raise ValueError("adaptive sampled nonnegative/bounded depth mismatch")
    for name in ("leaf_area_m2","face_left","face_right","face_axis","face_crest_relative_m","boundary_cell"):
        if not np.array_equal(packet[name],a[name]):
            raise ValueError("adaptive first-step saved incidence mismatch")
    dt = packet["dt_s"]
    if not 0<dt<=budget["max_dt_s"]:
        raise ValueError("adaptive first-step dt mismatch")
    area = a["leaf_area_m2"]
    equations = []
    for rk in (1,2):
        source = packet[f"rk{rk}_bed_source"]
        if np.any(source[:,0]!=0) or np.any(packet[f"rk{rk}_boundary_flux"][a["boundary_kind"]==0,0]!=0):
            raise ValueError("adaptive sampled closed mass or bed source mismatch")
        rhs = source.copy()
        np.add.at(rhs,a["face_left"],-packet[f"rk{rk}_internal_flux"]/area[a["face_left"],None])
        np.add.at(rhs,a["face_right"],packet[f"rk{rk}_internal_flux"]/area[a["face_right"],None])
        np.add.at(rhs,a["boundary_cell"],-packet[f"rk{rk}_boundary_flux"]/area[a["boundary_cell"],None])
        rhs[:,0] += packet["forcing_m3_s"]/area
        equations.append(rhs)
    near(packet["state_predictor"],packet["state_before"]+dt*equations[0],"saved predictor equation")
    undamped = .5*packet["state_before"]+.5*(packet["state_predictor"]+dt*equations[1])
    near(packet["state_after"][:,0],undamped[:,0],"saved RK mass equation")
    stage = storage_stage(undamped[:,0],geometry)
    factor = np.zeros(n)
    for cell,count in enumerate(a["subcell_count"]):
        offset = a["subcell_offset"][cell]
        h = np.maximum(stage[cell]-a["sorted_subcell_bed_relative_m"][offset:offset+count],0)
        factor[cell] = np.sum(h[h>0]**(-1/3))/count
    near(packet["manning_inverse_depth_third_mean"],factor,"saved canonical Manning integral")
    squared = undamped[:,0]**2
    denominator = squared+dt*budget["gravity_m_s2"]*budget["roughness_s_m_third"]**2*np.hypot(undamped[:,1],undamped[:,2])*factor
    damping = np.divide(squared,denominator,out=np.zeros_like(squared),where=denominator>0)
    expected = undamped[:,1:]*damping[:,None]
    near(packet["state_after"][:,1:],expected,"saved canonical Manning equation")
    near(packet["manning_momentum_change"],expected-undamped[:,1:],"saved Manning change")
