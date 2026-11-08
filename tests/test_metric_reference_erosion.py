"""Local router exchange test: positive shear erodes finite bed at zero input."""
import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_reference_erosion import reference_router_classes, reference_scales
from terrain_pipeline.surface_rivers.metric_fluvial_native_routers import source_limited_router_classes


def test_reference_scales_do_not_claim_injected_sediment():
    capacity, erosion = reference_scales(100., 10., .001, 1000, 20.)
    assert capacity == pytest.approx(.005)
    assert erosion == pytest.approx(.001)


def test_zero_load_reference_erosion_keeps_actual_injection_zero_and_respects_floor():
    # Compile the real specialized router, then exercise one controlled cell.
    _, Sand = reference_router_classes()
    ivec = np.array([-1., -1., -1., 0., 0., 0., 1., 1., 1.], dtype=np.float32)
    jvec = np.array([-1., 0., 1., -1., 0., 1., -1., 0., 1.], dtype=np.float32)
    router = Sand(10., 5., 0., 4., .01, 1., 1., .5, ivec, jvec,
        ivec.astype(np.int64), jvec.astype(np.int64), np.maximum(np.hypot(ivec, jvec), 1.),
        .01, 3., 100, False, 1., np.ones((1, 1), dtype=np.float32))
    router.reference_erosion_packet_bulk_m3 = .2
    router.source_floor_m = np.array([[-1.]])
    router.source_floor_limited_bulk_m3 = 0.
    router.source_floor_limited_exchange_count = 0
    router.px = 0
    router.py = 0
    proposed = router._compute_Vp_ero(0., 2., 1., 3., 1.)
    assert proposed == pytest.approx(1.4)
    accepted = router._limit_Vp_change(proposed, 0., -.99, 5., 1, 1.)
    assert 0. < accepted <= .25+1.e-12
    assert -.99-accepted/25. >= -1.
    # Actual parcel load remains zero; reference amount is a potential bed debit.
    assert router.Vp_sed == 0.


def controlled_router(kind, independent, actual_packet):
    classes = reference_router_classes() if independent else source_limited_router_classes(False, True)
    Router = classes[0 if kind == "mud" else 1]
    ivec = np.array([-1., -1., -1., 0., 0., 0., 1., 1., 1.], np.float32)
    jvec = np.array([-1., 0., 1., -1., 0., 1., -1., 0., 1.], np.float32)
    directions = (ivec, jvec, ivec.astype(np.int64), jvec.astype(np.int64), np.maximum(np.hypot(ivec, jvec), 1.))
    if kind == "sand":
        router = Router(10., 5., actual_packet, 4., .01, 1., 1., .5,
            *directions, .01, 3., 100, False, 1., np.ones((3, 3), np.float32))
    else:
        router = Router(10., 5., actual_packet, 4., .5, 1.,
            *directions, .01, .5, 3., 100, False, 1., np.ones((3, 3), np.float32))
    if independent:
        router.reference_erosion_packet_bulk_m3 = .2
    router.source_floor_m = np.full((3, 3), -1.)
    router.source_floor_limited_bulk_m3 = 0.
    router.source_floor_limited_exchange_count = 0
    for field in ("eta", "stage", "depth", "uw", "ux", "uy", "qw", "qx", "qy", "qs", "mod_stable_weight"):
        setattr(router, field, np.zeros((3, 3), np.float32))
    router.eta[:] = -.99
    router.depth[:] = .99
    router.uw[:] = 2.
    router.qw[:] = 2.
    router.qx[:] = 2.
    router.mod_stable_weight[:] = 1.
    router.pad_depth = np.pad(router.depth, 1, mode="edge")
    router.Vp_dep_sand = np.zeros((3, 3))
    router.Vp_dep_mud = np.zeros((3, 3))
    router.Vp_res = actual_packet
    return router


@pytest.mark.parametrize("kind", ["sand", "mud"])
def test_actual_zero_input_exchange_erodes_finite_bed_and_transfers_into_parcel(kind):
    router = controlled_router(kind, True, 0.)
    before = float(router.eta[1, 1])
    router._deposit_or_erode(1, 1)
    removed = (before-float(router.eta[1, 1]))*25.
    assert removed > 0.
    assert router.eta[1, 1] >= -1.
    assert router.Vp_res == pytest.approx(removed)
    assert router.Vp_sed == 0.
    assert router.source_floor_limited_exchange_count > 0
    # Complete the next exchange at a low-speed cell: eroded parcel material
    # either deposits or remains suspended, with no external sediment creation.
    router.uw[1, 2] = 0.
    before_second = float(router.eta[1, 2])
    router._deposit_or_erode(1, 2)
    deposited = (float(router.eta[1, 2])-before_second)*25.
    assert deposited >= 0.
    assert removed == pytest.approx(deposited+router.Vp_res, abs=1.e-12)


@pytest.mark.parametrize("kind", ["sand", "mud"])
def test_matching_reference_packet_has_identical_positive_load_native_exchange(kind):
    reference = controlled_router(kind, True, .2)
    native = controlled_router(kind, False, .2)
    reference._deposit_or_erode(1, 1)
    native._deposit_or_erode(1, 1)
    np.testing.assert_array_equal(reference.eta, native.eta)
    assert reference.Vp_res == native.Vp_res
