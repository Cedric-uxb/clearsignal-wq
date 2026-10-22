# ClearSignal WQ 数据

## 来源与许可

本项目使用 `AmberSJones/pyhydroqc` 仓库 `LRO_data` 目录中的公开水质传感器数据，并固定到提交：

`1260f16ae254abadcd43d71ee1705c3eea1ea2d4`

`pyhydroqc` GitHub 代码仓库采用 BSD-3-Clause 许可证。与这些 CSV 关联的 [CUAHSI HydroShare 教学数据资源](https://www.hydroshare.org/resource/451c4f9697654b1682d87ee619cd7924/) 标为 CC BY 4.0；代码许可与数据资源许可应分别遵守，不能将数据笼统视为仅受 BSD-3-Clause 约束。

固定文件及 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `MainStreet2019.csv` | `752f04c363ac6e2667c0099dfdd3592d2ff99a25013dfeeac80a10bccbbdb7f8` |
| `FranklinBasin2017.csv` | `802b429e06b351a9289c8acfffe440c9a31c6c82a938553138454c00b2acdbc1` |

## 下载

在仓库根目录运行：

```bash
.venv/bin/python scripts/download_data.py
```

也可以指定目标目录：

```bash
.venv/bin/python scripts/download_data.py --destination data/raw
```

脚本只接受上表中的两个文件名，下载后验证 SHA-256，并在校验成功后原子写入目标文件。原始 CSV 保存在 `data/raw/`，该目录已被 Git 忽略，不应提交到仓库。

## 列语义

- `datetime`：上游说明为 Mountain Standard Time。CSV 中无时区标记的墙上时间按固定 UTC-07:00 解释，再转换为 UTC 时间索引；不使用会随夏令时变化的时区规则。
- `temp`、`cond`、`ph`、`do`、`turb`：温度、电导率、pH、溶解氧和浊度的原始传感器读数。
- `*_cor`：与对应传感器相关的校正值。
- `*_qual`：技术人员记录的传感器或数据质量异常标注。

`*_qual` 不是污染标签，也不能证明水体受污染、可安全饮用或满足任何监管标准。它只用于识别已记录的传感器或数据异常，并支持后续人工复核。
