# Third-Party Notices

## pyhydroqc and Logan River Observatory data

ClearSignal WQ uses public aquatic sensor data distributed by the following upstream project:

- Project: [AmberSJones/pyhydroqc](https://github.com/AmberSJones/pyhydroqc)
- Fixed commit: [`1260f16ae254abadcd43d71ee1705c3eea1ea2d4`](https://github.com/AmberSJones/pyhydroqc/tree/1260f16ae254abadcd43d71ee1705c3eea1ea2d4)
- Upstream software license: BSD 3-Clause
- Upstream copyright: Copyright (c) 2021, Amber Jones
- Files used at runtime: `LRO_data/MainStreet2019.csv` and `LRO_data/FranklinBasin2017.csv`

The upstream repository describes pyhydroqc as anomaly-detection and correction software for in-situ aquatic sensor data from the Logan River Observatory. It cites:

> Jones, A. S., Jones, T. L., and Horsburgh, J. S. (2022). Toward automated post processing of aquatic sensor data. Environmental Modelling & Software. https://doi.org/10.1016/j.envsoft.2022.105364

ClearSignal WQ does not vendor pyhydroqc source code and does not commit the upstream raw CSV files. Its independent implementation uses the published workflow as technical background and downloads the two allow-listed CSV files directly from the fixed upstream commit with SHA-256 verification.

## Associated HydroShare resource

The associated teaching resource is:

- Title: *Hydroinformatics Instruction Module Example Code: Sensor Data Quality Control with pyhydroqc*
- Author/citation: Jones, A. S. (2022), HydroShare
- Resource: https://www.hydroshare.org/resource/451c4f9697654b1682d87ee619cd7924/
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Contributors listed by HydroShare: Jeffery S. Horsburgh and Camilo J. Bastidas Pacheco

The resource states that the sensor files were obtained from the Logan River Observatory database and that each variable includes a raw value, a technician-corrected value, and a technician label/qualifier. ClearSignal WQ preserves that attribution and does not reinterpret technician quality labels as contaminant labels.

## Integrity records

| Upstream file | SHA-256 |
| --- | --- |
| `MainStreet2019.csv` | `752f04c363ac6e2667c0099dfdd3592d2ff99a25013dfeeac80a10bccbbdb7f8` |
| `FranklinBasin2017.csv` | `802b429e06b351a9289c8acfffe440c9a31c6c82a938553138454c00b2acdbc1` |

See the upstream [BSD 3-Clause license](https://github.com/AmberSJones/pyhydroqc/blob/1260f16ae254abadcd43d71ee1705c3eea1ea2d4/LICENSE) and the [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/) for the complete conditions.

