"""Whole declared TD edge set, connected canonical beds and unique cut ledger."""

import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig, _footprint
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_incision import _profile
from terrain_pipeline.surface_rivers.metric_valley_union import build_valley_union, load_valley_union, save_valley_union
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID, terrain_from_product
from tools.audit_td_river_geometry_sediment import independent_continuous_bed


ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/"verification/td-river-network-expansion/td1024-20261008-01"


def connected_components(edges, receiver):
    adjacency={}
    for cell in edges:
        target=int(receiver[cell])
        adjacency.setdefault(int(cell),set()).add(target)
        adjacency.setdefault(target,set()).add(int(cell))
    remaining=set(adjacency)
    result=[]
    while remaining:
        seed=min(remaining)
        stack=[seed]
        remaining.remove(seed)
        component=[]
        while stack:
            cell=stack.pop()
            component.append(cell)
            for neighbor in sorted(adjacency[cell]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        result.append(np.asarray(sorted(component),np.int64))
    return result


def independent_mesh(product):
    a=product["arrays"]
    independent_continuous_bed(product)
    points=a["vertices_xz_m"][a["triangles"]]
    signed=((points[:,1,0]-points[:,0,0])*(points[:,2,1]-points[:,0,1])
            -(points[:,2,0]-points[:,0,0])*(points[:,1,1]-points[:,0,1]))/2.
    if np.any(signed==0.) or not (np.all(signed>0.) or np.all(signed<0.)):
        raise AssertionError("degenerate or reversed sparse triangles")
    volume=float(np.dot(np.abs(signed),np.mean(a["source_elevation_m"][a["triangles"]]-a["bed_elevation_m"][a["triangles"]],axis=1)))
    np.testing.assert_allclose(volume,product["metadata"]["cut_volume_m3"],rtol=0.,atol=1e-8)
    bary=a["port_barycentric"]
    vertices=a["triangles"][a["port_triangle_ids"]]
    np.testing.assert_allclose(np.sum(a["vertices_xz_m"][vertices]*bary[...,None],axis=-2),a["port_profile_xz_m"],rtol=0.,atol=1e-8)
    np.testing.assert_allclose(np.sum(a["cut_depth_m"][vertices]*bary,axis=-1),a["port_cut_depth_m"],rtol=0.,atol=1e-9)
    directed=np.concatenate((a["triangles"][:,[0,1]],a["triangles"][:,[1,2]],a["triangles"][:,[2,0]]))
    undirected=np.sort(directed,axis=1)
    _,inverse,counts=np.unique(undirected,axis=0,return_inverse=True,return_counts=True)
    orientation=np.bincount(inverse,weights=np.where(directed[:,0]<directed[:,1],1,-1))
    if np.any(counts>2) or np.any(orientation[counts==2]!=0):
        raise AssertionError("nonmanifold sparse union")
    return volume


def unique_ledger(products):
    """Integrate each global aligned cell once; reject shared positive owners."""
    cells={}
    local_sum=0.
    duplicate_zero_cells=0
    for component_index,product in enumerate(products):
        a=product["arrays"]
        spacing=product["metadata"]["config"]["fine_spacing_m"]
        local_sum+=independent_mesh(product)
        for cell_index,xy in enumerate(a["sparse_cell_xy"]):
            triangles=a["triangles"][4*cell_index:4*cell_index+4]
            coordinates=a["vertices_xz_m"][triangles]
            cuts=a["cut_depth_m"][triangles]
            key=tuple(xy.tolist())
            if key in cells:
                before=cells[key]
                np.testing.assert_array_equal(before[0],coordinates)
                if np.any(before[1]>0.) and np.any(cuts>0.):
                    raise AssertionError(("cross-component positive cut support overlap",key,before[3],component_index))
                duplicate_zero_cells+=1
                cells[key]=(coordinates,np.maximum(cuts,before[1]),spacing,component_index)
            else:
                cells[key]=(coordinates,cuts.copy(),spacing,component_index)
    unique_volume=0.
    for _,cuts,spacing,_ in cells.values():
        unique_volume+=spacing*spacing/4.*float(np.mean(cuts,axis=1).sum())
    np.testing.assert_allclose(unique_volume,local_sum,rtol=1e-10,atol=1e-7)
    return dict(unique_cells=len(cells),duplicate_zero_support_cells=duplicate_zero_cells,
        global_unique_cut_volume_m3=unique_volume,sum_component_cut_volume_m3=local_sum,
        cross_component_positive_support_disjoint=True)


def shape_statistics(edges, receiver, columns, terrain):
    selected=set(map(int,edges))
    angles=[]
    lengths={}
    for cell in selected:
        target=int(receiver[cell])
        if target in selected:
            following=int(receiver[target])
            first=np.array(terrain.world_xz(target))-terrain.world_xz(cell)
            second=np.array(terrain.world_xz(following))-terrain.world_xz(target)
            angle=float(np.degrees(np.arccos(np.clip(np.dot(first,second)/(np.linalg.norm(first)*np.linalg.norm(second)),-1.,1.))))
            angles.append(angle)
        length=0.
        node=cell
        previous=None
        while node in selected:
            next_node=int(receiver[node])
            direction=(next_node//columns-node//columns,next_node%columns-node%columns)
            if previous is not None and direction!=previous:break
            length+=float(np.linalg.norm(np.array(terrain.world_xz(next_node))-terrain.world_xz(node)))
            previous=direction
            node=next_node
        lengths[cell]=length
    return dict(edge_pairs=len(angles),right_angle_pairs=sum(abs(v-90.)<1e-8 for v in angles),
        straight_pairs=sum(v<1e-8 for v in angles),maximum_turn_degrees=max(angles,default=0.),
        longest_straight_m=max(lengths.values(),default=0.),fixed_XZ_angle_change_degrees=0.)


def verify(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    code_paths=("terrain_pipeline/surface_rivers/metric_valley_union.py",
                "terrain_pipeline/surface_rivers/metric_valley_incision.py",
                "tools/verify_td_valley_network_union.py")
    code_pins={path:file_sha256(ROOT/path) for path in code_paths}
    publish_bytes(output/"run-declaration.json",json.dumps(dict(source_sha256=TD_PRODUCT_SHA,
        code_sha256=code_pins,status="running_not_accepted"),indent=2).encode())
    parent=json.loads((PARENT/"acceptance.json").read_text())
    source=load_diagnostic_product(TD_DIRECTORY/"product.npz",expected_sha256=TD_PRODUCT_SHA,expected_identity=TD_PRODUCT_ID)
    terrain=terrain_from_product(source)
    pin=parent["plan"]
    plan=load_network_geometry_plan(PARENT/pin["path"],expected_sha256=pin["sha256"])
    if plan["identity_sha256"]!=pin["identity_sha256"]:raise AssertionError("network plan pin changed")
    a=plan["arrays"]
    receiver=a["graph_receiver"]
    selected=a["selected_edge_source_ids"]
    owner=a["terminal_owner"].reshape(terrain.elevation_m.shape)
    options=dict(owner_grid=owner,corridor_mask=np.ones(owner.shape,bool),lake_mask=np.zeros(owner.shape,bool))
    q=a["contributing_area_m2"]/1000./3600.
    widths=np.maximum(6.,4.*np.sqrt(q))
    depths=np.maximum(.25,.2*np.cbrt(q))
    eligible=[]
    outcomes=[]
    for cell in selected:
        ids=np.array([cell,receiver[cell]],np.int64)
        points=np.array([terrain.world_xz(int(v)) for v in ids])
        rec=np.array([1,-1],np.int64)
        try:
            _profile(points,rec,depths[ids],terrain,4.)
            _footprint(points,rec,widths[ids],np.full(2,4.),terrain,owner,options["corridor_mask"],options["lake_mask"],owner.ravel()[ids],.5)
            eligible.append(int(cell))
            outcomes.append(dict(source_cell_id=int(cell),status="passed_edge_preflight"))
        except ValueError as error:
            outcomes.append(dict(source_cell_id=int(cell),status="refused_edge_preflight",reason=str(error)))
    eligible_set=set(eligible)
    artifacts,records,products={},{},[]
    accepted_edges=[]
    for index,ids in enumerate(connected_components(eligible,receiver)):
        mapping={int(cell):i for i,cell in enumerate(ids)}
        rec=np.array([mapping[int(receiver[cell])] if int(cell) in eligible_set else -1 for cell in ids],np.int64)
        edges=ids[rec>=0]
        record=dict(source_node_ids=ids.tolist(),source_edge_ids=edges.tolist())
        try:
            levels=[]
            for spacing in (.5,.25):
                levels.append(build_valley_union(terrain,ids,rec,widths[ids],depths[ids],**options,
                    source_plan_identity_sha256=plan["identity_sha256"],
                    config=GeometryConfig(fine_spacing_m=spacing,smoothing_iterations=0)))
            cv,fv=[independent_mesh(g) for g in levels]
            error=abs(cv-fv)/max(fv,1e-12)
            if error>.02:raise ValueError("shared union volume refinement exceeds fixed 2% gate")
            for label,product in zip(("coarse","fine"),levels):
                name="component-"+str(index).zfill(3)+"-"+label
                path=output/(name+".npz")
                save_valley_union(path,product)
                sha=file_sha256(path)
                with patch("terrain_pipeline.surface_rivers.metric_valley_union.build_valley_union",side_effect=AssertionError("cold union")):
                    cold=load_valley_union(path,expected_sha256=sha,expected_identity=product["identity_sha256"])
                    independent_mesh(cold)
                artifacts[name]=dict(path=path.name,sha256=sha,identity_sha256=product["identity_sha256"])
            products.append(levels[-1])
            accepted_edges.extend(edges.tolist())
            record.update(status="accepted_connected_component",spatial_refinement_relative=error,cut_volume_m3=fv)
        except ValueError as error:
            record.update(status="refused_connected_component",reason=str(error))
        records[str(index)]=record
        publish_bytes(output/"progress.json",json.dumps(dict(status="incomplete_progress",
            artifacts=artifacts,component_records=records,eligible_edges=len(eligible),preflight=outcomes),indent=2).encode())
        print(json.dumps(dict(component=index,edges=len(edges),status=record["status"],reason=record.get("reason"))),flush=True)
    ledger=unique_ledger(products)
    if len(set(accepted_edges))!=len(accepted_edges):raise AssertionError("duplicate global edge ownership")
    accepted_set=set(accepted_edges)
    # Attribute each original local forcing cell to its first accepted downstream
    # source node, or to an explicit unresolved/outside-coverage owner.
    assignment=np.full(receiver.size,-1,np.int64)
    for cell in a["graph_order_downstream_first"]:
        target=receiver[cell]
        assignment[cell]=cell if int(cell) in accepted_set else (assignment[target] if target>=0 else -1)
    local=source["arrays"]["local_q_m3_s"].reshape(len(source["arrays"]["time_seconds"])-1,-1)
    dt=np.diff(source["arrays"]["time_seconds"])
    assigned_volume=float(np.sum(local[:,assignment>=0]*dt[:,None]))
    unresolved_volume=float(np.sum(local[:,assignment<0]*dt[:,None]))
    np.testing.assert_allclose(assigned_volume+unresolved_volume,float(np.sum(local*dt[:,None])),rtol=1e-12,atol=1e-8)
    report=dict(status="candidate_incomplete_global_geometry",declared_selected_edges=len(selected),
        eligible_edges=len(eligible),accepted_global_edges=len(accepted_edges),coverage_fraction=len(accepted_edges)/len(selected),
        preflight=outcomes,preflight_reasons=dict(Counter(row["reason"] for row in outcomes if "reason" in row)),
        component_records=records,component_status=dict(Counter(row["status"] for row in records.values())),
        source=dict(path=str(TD_DIRECTORY/"product.npz"),sha256=TD_PRODUCT_SHA,identity_sha256=TD_PRODUCT_ID),
        parent_network_plan=pin,artifacts=artifacts,unique_material_ledger=ledger,
        code_sha256=code_pins,
        unique_native_local_source_accounting=dict(assigned_volume_m3=assigned_volume,unresolved_or_outside_coverage_volume_m3=unresolved_volume),
        shape_statistics=shape_statistics(selected,receiver,terrain.elevation_m.shape[1],terrain),
        geometry_verified=False,hydraulic_ready=False,natural_outlet_verified=False,publishable=False,
        limitations=["fixed_XZ_does_not_remove_raster_right_angles","refused_edges_and_components_retained",
                     "accepted_component_ports_share_actual_mesh","no_hydraulic_transfer_across_unresolved_closures",
                     "natural_lake_connections_pending_same_source_global_lake_domains"])
    if any(file_sha256(ROOT/path)!=sha for path,sha in code_pins.items()):
        raise AssertionError("geometry or verification code changed during this run")
    publish_bytes(output/"acceptance.json",json.dumps(report,indent=2,allow_nan=False).encode())
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    result=verify(parser.parse_args().output)
    print(json.dumps({key:result[key] for key in ("status","declared_selected_edges","eligible_edges","accepted_global_edges","coverage_fraction","component_status")}))
