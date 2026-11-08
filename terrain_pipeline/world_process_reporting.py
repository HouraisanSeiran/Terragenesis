"""Read-only comparisons on explicitly owned world-process support."""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import array_sha256


def island_peak_report(initial_bed_m,final_bed_m,component_owner,*,spacing_m,
                       source_identity,final_identity,component_ids=None):
    """Compare sampled island peaks without rescaling either terrain.

    ``component_owner`` is the prepared connected-island ownership raster;
    zero means outside selected islands. Values are component labels, not
    newly inferred mountain footprints. Reported extrema refer to this grid.
    """
    initial=np.asarray(initial_bed_m,np.float64)
    final=np.asarray(final_bed_m,np.float64)
    owner=np.asarray(component_owner)
    if (initial.ndim!=2 or final.shape!=initial.shape or owner.shape!=initial.shape or
            owner.dtype.kind not in 'iu' or np.any(owner<0) or
            not np.isfinite(initial).all() or not np.isfinite(final).all()):
        raise ValueError('finite matching beds and nonnegative integer island ownership required')
    if not np.isfinite(spacing_m) or spacing_m<=0 or not source_identity or not final_identity:
        raise ValueError('explicit metric spacing and source identities required')
    labels=np.unique(owner[owner>0])
    rows=[]
    for label in labels:
        support=owner==label
        before=float(initial[support].max())
        after=float(final[support].max())
        rows.append(dict(component_label=int(label),
            component_id=(component_ids or {}).get(int(label),str(int(label))),
            sample_count=int(support.sum()),sampled_support_area_m2=float(support.sum()*spacing_m**2),
            initial_peak_elevation_m=before,final_peak_elevation_m=after,
            peak_change_m=after-before))
    return dict(schema='world-island-process-peaks-v1',source_identity=source_identity,
        final_identity=final_identity,ownership_sha256=array_sha256(owner),spacing_m=float(spacing_m),components=rows,
        semantics='sampled absolute elevation maxima on prepared ownership; process output is never renormalized')
