"use strict";

/**
 * Dynamic river-network rendering for the shared 2D review canvas.
 *
 * This module deliberately separates the evidence layers:
 * diagnostic graph topology, candidate centerlines, bounded channel geometry,
 * and saved water surface. A graph edge is never drawn on a stage projection
 * and its line width never encodes channel width.
 */
(function installRiverRenderer(global) {
    const endpointConvention = 'positive signedEdgeQ flows from graph.edges[index][0] to graph.edges[index][1]';
    const topologyColor = '#9aaea0';
    const centerlineColor = '#e3bb72';
    const channelColor = '#a97954';
    const waterColor = '#72c8d3';

    function flowInterval(data, state) {
        const series = data.timeseries;
        if (!series || !Array.isArray(series.signedEdgeQ) || !series.signedEdgeQ.length) {
            return null;
        }
        const index = state.time === 0 ? 0 : state.time - 1;
        const timeSeconds = series.timeSeconds || [];
        if (!Number.isInteger(index) || index < 0 || index >= series.signedEdgeQ.length ||
            index + 1 >= timeSeconds.length) {
            return null;
        }
        const row = series.signedEdgeQ[index];
        const semantics = series.dischargeSemantics || series.signedEdgeQSemantics || null;
        return {
            kind: 'saved-edge-interval',
            index,
            start: timeSeconds[index],
            end: timeSeconds[index + 1],
            intervalSeconds: timeSeconds[index + 1] - timeSeconds[index],
            row,
            qUnits: series.signedEdgeQUnits || null,
            endpointConvention,
            semantics,
            intervalSemantics: 'payload interval row; no inferred unit or instantaneous-rate interpretation'
        };
    }

    function projectedPolyline(polyline, projection) {
        if (!Array.isArray(polyline)) return [];
        return polyline.map(point => {
            if (!Array.isArray(point) || point.length < 3) return null;
            return projection([Number(point[0]), Number(point[1]), Number(point[2])]);
        }).filter(Boolean);
    }

    function renderCandidateGeometry(data, projection, drawLine) {
        const geometry = data.channelGeometry || data.geometry || data.candidateGeometry;
        if (!geometry) return {centerlines: 0, channels: 0};
        const centerlines = geometry.centerlines || geometry.centerline_xyz_m || [];
        let centerlineCount = 0;
        for (const line of centerlines) {
            const projected = projectedPolyline(line, projection);
            if (projected.length > 1) {
                drawLine(projected, centerlineColor, 2.2);
                centerlineCount++;
            }
        }
        const corridors = geometry.corridors || geometry.channel_corridors || [];
        let channelCount = 0;
        for (const line of corridors) {
            const projected = projectedPolyline(line, projection);
            if (projected.length > 1) {
                drawLine(projected, channelColor, 4.5);
                channelCount++;
            }
        }
        return {centerlines: centerlineCount, channels: channelCount};
    }

    function render(data, width, height, baseCamera, helpers) {
        const {state, bounds, fit, project, camera3d, drawLine, drawTriangle, context} = helpers;
        const graph = data.graph;
        const series = data.timeseries || {};
        const stages = Array.isArray(series.stages?.[state.time]) ? series.stages[state.time] : graph.bed;
        const vertices = graph.coords.map((point, index) => [point[0], graph.bed[index], point[1]]);
        const boundsXZ = bounds(vertices);
        const scale = fit(boundsXZ, width, height, 70);
        const camera = baseCamera || (state.view === '3d' ? camera3d(vertices, [...graph.bed, ...stages], width, height) : null);
        const projection = camera ? camera.projection : point => project(point, boundsXZ, width, height, scale);
        const bed = vertices.map(projection);
        const water = vertices.map((point, index) => projection([point[0], stages[index], point[2]]));
        const interval = flowInterval(data, state);
        const graphPoints = bed;

        if (state.layers.edges !== false) {
            graph.edges.forEach((edge, index) => {
                const start = graphPoints[edge[0]];
                const end = graphPoints[edge[1]];
                if (!start || !end) return;
                const rate = interval?.row?.[index];
                ctxDashed(context, [6, 5]);
                drawLine([start, end], topologyColor, 1.05);
                ctxDashed(context, []);
                if (Number.isFinite(rate) && Math.abs(rate) > 1e-8) {
                    const from = rate < 0 ? end : start;
                    const to = rate < 0 ? start : end;
                    const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
                    drawTriangle([
                        to,
                        [to[0] - 7 * Math.cos(angle - 0.5), to[1] - 7 * Math.sin(angle - 0.5)],
                        [to[0] - 7 * Math.cos(angle + 0.5), to[1] - 7 * Math.sin(angle + 0.5)]
                    ], rate < 0 ? '#e18170' : '#b7d2ba');
                }
            });
        }

        const geometrySummary = renderCandidateGeometry(data, projection, drawLine);
        const order = vertices.map((_, index) => index);
        if (camera) order.sort((left, right) => water[right][2] - water[left][2]);
        for (const index of order) {
            if (state.layers.bed && state.layers.water && camera) drawLine([bed[index], water[index]], '#8ba08d', 1);
            const radius = graph.boundary[index] ? 6 : 4;
            if (state.layers.bed) {
                context.beginPath(); context.arc(bed[index][0], bed[index][1], radius, 0, Math.PI * 2);
                context.fillStyle = '#cfaa75'; context.fill(); context.strokeStyle = '#d7ead8'; context.stroke();
            }
            if (state.layers.water && Number.isFinite(stages[index])) {
                context.beginPath(); context.arc(water[index][0], water[index][1], Math.max(2, radius - 1), 0, Math.PI * 2);
                context.fillStyle = waterColor; context.fill(); context.strokeStyle = '#d7ead8'; context.stroke();
            }
        }
        return {
            bounds: boundsXZ, scale, p: state.layers.water ? water : bed, points: graphPoints,
            bed, water, interval, camera, edges: graph.edges, endpointConvention,
            graphLayer: 'diagnostic drainage topology',
            centerlineLayer: geometrySummary.centerlines ? 'candidate river centerline' : 'not supplied',
            channelLayer: geometrySummary.channels ? 'bounded diagnostic bed geometry' : 'not supplied',
            waterSurfaceLayer: state.layers.water ? 'saved stage projection; source remains payload evidence' : 'hidden',
            overlaySemantics: 'graph topology is a diagnostic annotation on the bed projection; it is not a fine-grid instantaneous water surface'
        };
    }

    function ctxDashed(context, dash) {
        if (typeof context.setLineDash === 'function') context.setLineDash(dash);
    }

    global.riverRenderer = {flowInterval, render};
}(window));
