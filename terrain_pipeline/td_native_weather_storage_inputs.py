"""Pure spatial-weather input contract for a separate v9 continuation acceptance."""
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.climate_forcing import load_native_storm


def load_weather_inputs(path,*,expected_sha256,hierarchy):
    path=Path(path)
    if path.stat().st_size>8*1024*1024 or file_sha256(path)!=expected_sha256:
        raise ValueError("weather index external SHA/budget mismatch")
    index=json.loads(path.read_text(encoding="utf-8"))
    if index.get("schema")!="td-native-storm-forcing-index-v1" or set(index["cases"])!={"eastward","westward"}:
        raise ValueError("weather index schema/directions mismatch")
    source=index["source"]
    if source["expected_identity"]!=hierarchy["metadata"]["source_identity_sha256"] or file_sha256(source["path"])!=source["expected_sha256"]:
        raise ValueError("weather source pin/hierarchy mismatch")
    cases={}
    for direction,case in index["cases"].items():
        saved=load_native_storm(**case["record"],source_record=source,expected_plan=case["plan"])
        plan=saved["metadata"]["plan"]
        rain=saved["arrays"]["rain_mm_h"]
        if (rain.shape!=(24,*hierarchy["arrays"]["height_m"].shape) or plan["dt_s"]!=3600 or plan["start_s"]!=0 or
                plan["spacing_m"]!=hierarchy["metadata"]["spacing_m"] or plan["origin_m_xz"]!=hierarchy["metadata"]["origin_m_xz"] or
                not np.array_equal(saved["arrays"]["valid_mask"],hierarchy["arrays"]["valid_mask"])):
            raise ValueError("weather native grid/time/coordinate mismatch")
        forcing_id=identity({"rain_mm_h":rain},{"dt_s":3600.})
        if forcing_id!=case["forcing_identity"] or forcing_id!=saved["metadata"]["forcing_identity"]:
            raise ValueError("weather full3D forcing identity mismatch")
        cases[direction]={"rain_mm_h":rain,"forcing_identity":forcing_id,"record":case["record"],"plan_identity":saved["metadata"]["plan_identity"]}
    if file_sha256(path)!=expected_sha256:
        raise ValueError("weather index changed while loading")
    return {"schema":"td-v9-spatial-weather-inputs-v1","index_pin":{"path":str(path),"sha256":expected_sha256},"source":source,"cases":cases,
            "acceptance_schema":"td-v9-spatial-weather-hour-pages-acceptance-v1","hydraulic_ready":False,"publishable":False}
