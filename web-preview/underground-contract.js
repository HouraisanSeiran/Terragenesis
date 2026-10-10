/**
 * Underground-river payload contract checks.
 *
 * This module deliberately has no DOM, canvas, or Three.js dependency. The
 * viewer can therefore reject a malformed or semantically unsafe payload
 * before allocating scene resources or exposing stale geometry.
 */

export function validPoint(point) {
    return Array.isArray(point) && point.length === 3 && point.every(Number.isFinite);
}

export function validateMesh(points, triangles) {
    if (!Array.isArray(points) || !points.length || !points.every(validPoint) || !Array.isArray(triangles) || !triangles.length) {
        throw Error('暗河 XYZ／三角网格为空或无效');
    }
    if (triangles.some(face => !Array.isArray(face) || face.length !== 3 || !face.every(index => Number.isInteger(index) && index >= 0 && index < points.length))) {
        throw Error('暗河三角拓扑无效');
    }
}

export function validate(next) {
    if (next.schema !== 'td-underground-river-preview-v1' || !next.identity_sha256 || next.status !== 'geometry_checked' || next.water !== null) {
        throw Error('暗河 schema／identity／几何状态无效');
    }
    if (!validPoint(next.origin_xyz_m) || !next.parameters || !next.source_pins || !next.metrics) {
        throw Error('暗河来源／参数／坐标契约缺失');
    }
    for (const key of ['hydraulic_solved', 'full_network_verified', 'natural_outlet_certified']) {
        if (next.capabilities?.[key] !== false) {
            throw Error('暗河能力声明不符合第一版几何契约');
        }
    }
    for (const key of ['rock_before', 'cutter', 'rock_after', 'removed']) {
        validateMesh(next.meshes?.[key]?.vertices_local_xyz_m, next.meshes?.[key]?.triangles);
    }
    const vdm = next.vdm;
    validateMesh(vdm?.reference_local_xyz_m, vdm?.triangles);
    validateMesh(vdm?.derived_local_xyz_m, vdm?.triangles);
    if (vdm.reference_local_xyz_m.length !== vdm.derived_local_xyz_m.length || vdm.displacement_xyz_m?.length !== vdm.derived_local_xyz_m.length || !vdm.displacement_xyz_m.every(validPoint)) {
        throw Error('暗河 VDM 数组不匹配');
    }
    for (let index = 0; index < vdm.derived_local_xyz_m.length; index += 1) {
        for (let axis = 0; axis < 3; axis += 1) {
            const reference = vdm.reference_local_xyz_m[index][axis];
            const displacement = vdm.displacement_xyz_m[index][axis];
            const derived = vdm.derived_local_xyz_m[index][axis];
            const tolerance = 1e-7 * Math.max(1, Math.abs(reference), Math.abs(displacement), Math.abs(derived));
            if (Math.abs(reference + displacement - derived) > tolerance) {
                throw Error('暗河 VDM reference + displacement 与 derived 不一致');
            }
        }
    }
    if (!Array.isArray(next.stations) || !next.stations.length || next.stations.some(station => station.station_id == null || !validPoint(station.origin_local_xyz_m) || !Array.isArray(station.ring_local_xyz_m) || station.ring_local_xyz_m.length < 3 || !station.ring_local_xyz_m.every(validPoint))) {
        throw Error('暗河站点／断面无效');
    }
    if (!Array.isArray(next.portals) || next.portals.some(portal => !validPoint(portal.position_local_xyz_m))) {
        throw Error('暗河洞口无效');
    }
}
