"""Persistent product encoding, inventories and cold read validation."""
from copy import deepcopy
import math

import numpy as np
from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, save_bundle

SCHEMA = "environment-process-product-v1"
ALGORITHM = "finite-environment-process-coupling-v1"
EXPLICIT_V2_ALGORITHM = "finite-environment-process-coupling-v2"
SEASONAL_ALGORITHM = "finite-environment-seasonal-coupling-v1"
SEASONAL_V2_ALGORITHM = "finite-environment-seasonal-coupling-v2"
MAX_CELLS = 4096
PACKETS = ("litter_carbon_kg", "plant_nutrient_return_kg", "soil_water_m3", "soil_salt_kg",
           "subsurface_salt_kg", "subsurface_nutrient_kg")


def _pack(product, validate_product):
    validate_product(product)
    chunks, layout = [], []
    offset = 0
    def encode(value):
        nonlocal offset
        if isinstance(value, np.ndarray):
            data = np.ascontiguousarray(value)
            if data.dtype.kind not in "biuf" or not np.isfinite(data).all():
                raise ValueError("finite numeric/bool arrays required")
            key = len(layout)
            raw = data.view(np.uint8).ravel()
            layout.append({"offset": offset, "bytes": raw.size, "shape": list(data.shape), "dtype": data.dtype.str})
            chunks.append(raw)
            offset += raw.size
            return {"array_index": key}
        if isinstance(value, dict):
            return {str(key): encode(value[key]) for key in sorted(value)}
        if isinstance(value, (tuple, list)):
            return [encode(child) for child in value]
        if isinstance(value, np.generic):
            return value.item()
        return value
    tree = encode(product)
    payload = np.concatenate(chunks) if chunks else np.empty(0, np.uint8)
    if payload.nbytes > 64 * 1024 * 1024:
        raise ValueError("product payload exceeds bounded memory budget")
    metadata = {"schema": SCHEMA, "algorithm": product["algorithm"], "tree": tree, "layout": layout}
    arrays = {"payload": payload}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def _validate_bundle(bundle, validate_product):
    metadata = bundle["metadata"]
    if metadata.get("schema") != SCHEMA or metadata.get("algorithm") not in (ALGORITHM, EXPLICIT_V2_ALGORITHM, SEASONAL_ALGORITHM, SEASONAL_V2_ALGORITHM):
        raise ValueError("environment process schema mismatch")
    if identity(bundle["arrays"], metadata) != bundle["identity_sha256"]:
        raise ValueError("environment process identity mismatch")
    payload = bundle["arrays"]["payload"]
    offset = 0
    for item in metadata["layout"]:
        dtype = np.dtype(item["dtype"])
        if dtype.kind not in "biuf" or any(not isinstance(n, int) or n < 0 for n in item["shape"]):
            raise ValueError("invalid packed dtype/shape")
        size = math.prod(item["shape"]) * dtype.itemsize
        if item["offset"] != offset or item["bytes"] != size:
            raise ValueError("packed array layout mismatch")
        offset += size
    if payload.dtype != np.uint8 or payload.ndim != 1 or offset != payload.size:
        raise ValueError("packed payload length mismatch")
    product = _unpack(bundle)
    if product["algorithm"] != metadata["algorithm"]:
        raise ValueError("environment process algorithm header/tree mismatch")
    validate_product(product)


def _unpack(bundle):
    payload = bundle["arrays"]["payload"]
    layout = bundle["metadata"]["layout"]
    def decode(value):
        if isinstance(value, dict) and set(value) == {"array_index"}:
            item = layout[value["array_index"]]
            raw = payload[item["offset"]:item["offset"] + item["bytes"]]
            result = np.frombuffer(raw.tobytes(), dtype=item["dtype"]).reshape(item["shape"])
            if not np.isfinite(result).all():
                raise ValueError("nonfinite process payload")
            return result
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    return decode(bundle["metadata"]["tree"])


def save_product(product, path, validate_product):
    save_bundle(path, _pack(product, validate_product),
                validator=lambda bundle: _validate_bundle(bundle, validate_product))
    return file_sha256(path)


def product_identity(product, validate_product):
    return _pack(product, validate_product)["identity_sha256"]


def load_product(path, *, expected_sha256, validate_product):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=lambda bundle: _validate_bundle(bundle, validate_product))
    return _unpack(bundle)


def query_product(product, row, col):
    shape = product["context"]["height_m"].shape
    if not 0 <= row < shape[0] or not 0 <= col < shape[1]:
        raise ValueError("query outside completed product")
    result = {"schema": SCHEMA, "time_s": product["time_s"], "row": int(row), "col": int(col),
            "world_x_m": float(product["context"]["node_x_m"][row, col]),
            "world_z_m": float(product["context"]["node_z_m"][row, col]),
            "derived_height_m": float(product["context"]["height_m"][row, col]),
            "receiver": int(product["context"]["receiver"][row, col]),
            "external_handoff": bool(product["context"]["external_receiver_mask"][row, col]),
            "ocean": bool(product["context"]["ocean_mask"][row, col]),
            "states": {name: {key: np.asarray(value)[row, col].item() for key, value in state.items()}
                       for name, state in product["states"].items()}, "last_budget": deepcopy(product["last_budget"])}
    if "seasonal" in product:
        seasonal = product["seasonal"]
        origin = product["context"]["origin_native_xz"]
        base = seasonal["climate_driver"]["metadata"]["origin_native_xz"]
        sr, sc = row + origin[1] - base[1], col + origin[0] - base[0]
        result["seasonal"] = {key: float(seasonal[key][row, col])
                              for key in ("snow_swe_mm", "fast_mm", "slow_mm")}
        result["seasonal"].update(vapour_kg=float(seasonal["climate_state"]["arrays"]["vapour_kg"][sr, sc]),
                                  pending_et_kg=float(seasonal["pending_et_kg"][sr, sc]),
                                  network_policy=seasonal["network_policy"],
                                  driver_identity_sha256=seasonal["climate_driver"]["identity_sha256"],
                                  source_world_identity=product["sources"]["source_world_identity"],
                                  initial_swe_source=seasonal["initial_swe_source"])
        from terrain_pipeline.environment_material_source import query_material_source
        result["seasonal"]["material"] = query_material_source(seasonal["material_source"], row, col)
        if "land_cover" in seasonal:
            from terrain_pipeline.environment_land_cover_coupling import query as query_land_cover
            result["seasonal"]["land_cover"] = query_land_cover(product, row, col)
    return result

