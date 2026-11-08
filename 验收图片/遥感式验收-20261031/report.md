# Project remote acceptance atlas

SYNTHETIC MODEL VISUALIZATION / NOT SATELLITE OBSERVATION

Run: `runtime/venv/Scripts/python.exe -B tools/render_project_acceptance.py --output <new-directory>`

## Figures

- [01-terrain-basis.png](01-terrain-basis.png): 42 km saved terrain basis and composition
- [02-current-irregular-rivers.png](02-current-irregular-rivers.png): 42 km current irregular river graph and modelled lakes
- [03-derived-bed.png](03-derived-bed.png): Derived bed and excavation (same saved 42 km source)
- [04-seasonal-temperature.png](04-seasonal-temperature.png): G3 synthetic seasonal temperature on real saved terrain
- [05-computed-precipitation.png](05-computed-precipitation.png): G4 actual vapour transport: controlled uplift comparison
- [06-ridge-climate-support.png](06-ridge-climate-support.png): G4 complete saved terrain support and computed thermal field
- [07-snow-seasonal-event.png](07-snow-seasonal-event.png): G7 saved snow event, initial and final
- [08-water-inventories.png](08-water-inventories.png): G5 / G11 saved water inventories
- [09-soil-vegetation.png](09-soil-vegetation.png): G2 / G6 / G9 / G15 material and vegetation response
- [10-environment-mechanisms.png](10-environment-mechanisms.png): G12 / G13 / G14 / G16 / G20 saved finite mechanisms
- [11-latest-delta-remote.png](11-latest-delta-remote.png): Latest corrected delta: saved bed and actual wet mask
- [12-delta-tidal-states.png](12-delta-tidal-states.png): G8 / G19 saved tidal water snapshots
- [13-joint-td-environment.png](13-joint-td-environment.png): Same TD window: soil allocation, root water and vegetation jointly consumed

## Limits

- No observed remote-sensing or spectral calibration; colour is cartographic.
- Seasonal-v4 elapsed time is three hours, not climate change.
- Old large-world-first-pass/disk-connected-lakes-v1 registry is D8 priority flood; excluded from current graph figure.
- No full-world hydrology, long-term climatic trend, natural delta emergence or game acceptance claimed.
- Some environment fields are constant/zero; figures preserve their actual magnitude and separate scenario identities.

All source hashes, world/algorithm identities, native resolutions, units, extents, shared comparison colour limits and physical scenarios are in manifest.json.
