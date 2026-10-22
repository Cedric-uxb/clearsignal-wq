# ClearSignal WQ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个无需 API 密钥即可运行的 Streamlit 原型，把公开水质传感器时序中的异常合并成事件，并以证据、限制和人工验证动作将事件分为四类。

**Architecture:** 使用 Python 单体项目。`data` 负责可复现下载、校验和时间切分；`detectors` 产生确定性的点级异常；`events` 合并事件；`reliability` 计算传感器可靠度与跨传感器一致性；`triage` 输出四类状态；`pipeline` 串联流程；根目录 `app.py` 只负责 Streamlit 界面。规则基线先落地，ARIMA 候选必须通过预注册门槛后才能进入最终流水线。

**Tech Stack:** Python 3.11/3.12、pandas、NumPy、statsmodels、Streamlit、Plotly、pytest、pytest-cov、Ruff、Playwright。

---

## 执行约束

- 所有命令均从仓库根目录 `xylem-water-quality/` 运行。
- 严格按任务顺序执行；每个行为变化先写失败测试，再写最小实现。
- `MainStreet2019.csv` 是主数据，`FranklinBasin2017.csv` 只做不调参的跨站点检查。
- 原始 CSV、模型缓存、测试报告、截图和本地环境不提交到 Git。
- 真实数据质量标签、合成场景和真实污染事件必须分别命名，禁止混写。
- 任何输出不得声称水可安全饮用，也不得声称污染已经确认。
- 每个任务完成后，在本计划勾选步骤，并在根目录 `../总纲.md` 记录完成证据、下一步和验收标准。

## 固定目录与接口

```text
.
├── app.py
├── pyproject.toml
├── README.md
├── THIRD_PARTY_NOTICES.md
├── data/
│   └── README.md
├── demo/
│   └── demo_script.md
├── scripts/
│   ├── download_data.py
│   └── run_evaluation.py
├── src/clearsignal_wq/
│   ├── __init__.py
│   ├── contracts.py
│   ├── data.py
│   ├── detectors.py
│   ├── events.py
│   ├── evaluation.py
│   ├── pipeline.py
│   ├── reliability.py
│   ├── scenarios.py
│   └── triage.py
└── tests/
    ├── fixtures/sample_sensor_data.csv
    ├── test_app_smoke.py
    ├── test_contracts.py
    ├── test_data.py
    ├── test_detectors.py
    ├── test_events.py
    ├── test_evaluation.py
    ├── test_pipeline.py
    ├── test_reliability.py
    ├── test_scenarios.py
    └── test_triage.py
```

核心接口固定为：

```python
def load_sensor_csv(path: Path) -> pd.DataFrame: ...
def chronological_split(frame: pd.DataFrame) -> DatasetSplit: ...
def detect_rule_anomalies(frame: pd.DataFrame) -> tuple[PointFlag, ...]: ...
def detect_arima_anomalies(train: pd.DataFrame, target: pd.DataFrame) -> tuple[PointFlag, ...]: ...
def group_flags_into_events(flags: tuple[PointFlag, ...]) -> tuple[DetectionEvent, ...]: ...
def assess_event(event: DetectionEvent, frame: pd.DataFrame) -> EventAssessment: ...
def triage_event(event: DetectionEvent, assessment: EventAssessment, provenance: DataProvenance) -> TriageEvent: ...
def evaluate_events(predicted: tuple[DetectionEvent, ...], labelled: tuple[DetectionEvent, ...], clean_days: float) -> EventMetrics: ...
def run_pipeline(frame: pd.DataFrame, provenance: DataProvenance, model: str = "rules") -> PipelineResult: ...
```

## Task 1：建立最小项目骨架与质量门

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/clearsignal_wq/__init__.py`
- Create: `tests/test_contracts.py`

- [x] 写第一个失败测试，确认包能导入并暴露版本号：

```python
from clearsignal_wq import __version__


def test_package_exposes_version() -> None:
    assert __version__ == "0.1.0"
```

- [x] 运行 `.venv/bin/python -m pytest tests/test_contracts.py -q`；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq'` 失败。
- [x] 创建 `pyproject.toml`，项目依赖固定为 `pandas`、`numpy`、`statsmodels`、`streamlit`、`plotly`，开发依赖固定为 `pytest`、`pytest-cov`、`ruff`、`playwright`；配置 `src` 布局、Ruff 和 `--strict-markers`。
- [x] 在 `src/clearsignal_wq/__init__.py` 中仅加入 `__version__ = "0.1.0"`。
- [x] 在 `.gitignore` 排除 `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`data/raw/`、`artifacts/`、`*.pkl`、`.env`、`playwright-report/` 和 `test-results/`。
- [x] 使用 Python 3.12 创建虚拟环境并安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

- [x] 运行 `.venv/bin/python -m pytest tests/test_contracts.py -q`；实际 `1 passed`。
- [x] 运行 `.venv/bin/python -m ruff check .`；实际 `All checks passed!`。
- [x] 提交：`d904d36 chore: scaffold ClearSignal WQ package`。

**完成证据（2026-10-12）：** Python 3.12.13 环境安装成功；真实 RED、`1 passed`、Ruff、wheel 构建和忽略规则验证均通过；规格审查与代码质量审查均为 `APPROVED`。

**下一步：** 实现不可变的输出契约；验收条件是四类状态、证据强度和事件输出均能序列化且拒绝空证据。

## Task 2：实现不可变输出契约

**Files:**
- Create: `src/clearsignal_wq/contracts.py`
- Modify: `tests/test_contracts.py`

- [x] 在 `tests/test_contracts.py` 添加失败测试，覆盖四个状态、不可变对象和空证据拒绝：

```python
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

from clearsignal_wq.contracts import (
    DataProvenance,
    EvidenceItem,
    EvidenceStrength,
    TriageEvent,
    TriageStatus,
)


def test_triage_event_requires_evidence_and_is_immutable() -> None:
    event = TriageEvent(
        event_id="evt-001",
        start_at=datetime(2019, 1, 1, tzinfo=timezone.utc),
        end_at=datetime(2019, 1, 1, 0, 30, tzinfo=timezone.utc),
        triage_status=TriageStatus.SENSOR_FAULT_OR_DRIFT,
        evidence_strength=EvidenceStrength.HIGH,
        affected_sensors=("ph",),
        evidence=(EvidenceItem(code="stuck", message="pH 连续卡值", sensor="ph"),),
        recommended_action="清洁并校准 pH 传感器",
        data_provenance=DataProvenance.SYNTHETIC_SCENARIO,
        limitations=("不能证明真实污染",),
    )
    assert event.triage_status.value == "sensor_fault_or_drift"
    assert {status.value for status in TriageStatus} == {
        "possible_water_quality_event",
        "sensor_fault_or_drift",
        "data_integrity_issue",
        "insufficient_evidence",
    }
    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"
    with pytest.raises(ValueError, match="evidence"):
        replace(event, evidence=())
```

- [x] 运行测试；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq.contracts'` 失败。
- [x] 实现 `str, Enum` 类型的 `TriageStatus`、`EvidenceStrength`、`DataProvenance`，以及 `frozen=True, slots=True` 的 `EvidenceItem`、`PointFlag`、`DetectionEvent`、`EventAssessment`、`TriageEvent`、`EventMetrics`、`PipelineResult`。
- [x] 在契约边界验证 UTC 时间、枚举、不可变集合、来源一致性、必需字符串和标量类型；统一 `contract_to_dict` 将时间和枚举稳定转换为 JSON 安全值。
- [x] 运行 `.venv/bin/python -m pytest tests/test_contracts.py -q` 和 `.venv/bin/python -m ruff check .`；实际 `89 passed` 且 Ruff 通过。
- [x] 提交：`87fd381 feat: define water quality event contracts`，并以 `a2dcf0a`、`6b2c940`、`cd8486f`、`41f884d` 完成审查加固。

**完成证据（2026-10-13）：** 89 个契约测试通过；非法状态、可变列表、来源冲突、空白内容、非 UTC 时间和错误标量类型均被拒绝；JSON 序列化稳定；规格审查与代码质量审查均为 `APPROVED`。

**下一步：** 建立可复现数据下载和契约校验；验收条件是来源提交号与 SHA-256 可验证，且时间切分没有事件跨界。

## Task 3：实现可复现数据下载、校验与时间切分

**Files:**
- Create: `scripts/download_data.py`
- Create: `src/clearsignal_wq/data.py`
- Create: `data/README.md`
- Create: `tests/fixtures/sample_sensor_data.csv`
- Create: `tests/test_data.py`

固定上游版本：`AmberSJones/pyhydroqc@1260f16ae254abadcd43d71ee1705c3eea1ea2d4`。

固定 SHA-256：

```text
MainStreet2019.csv     752f04c363ac6e2667c0099dfdd3592d2ff99a25013dfeeac80a10bccbbdb7f8
FranklinBasin2017.csv  802b429e06b351a9289c8acfffe440c9a31c6c82a938553138454c00b2acdbc1
```

- [x] 创建人工构造测试样例，保留真实列名 `datetime,temp,temp_cor,temp_qual,cond,cond_cor,cond_qual,ph,ph_cor,ph_qual,do,do_cor,do_qual,turb,turb_cor,turb_qual`，不复制原始行。
- [x] 写失败测试：有效样例被解析为 UTC `DatetimeIndex`；缺列、重复时间戳、乱序和非数值传感器分别抛出包含字段名的 `DataContractError`。
- [x] 写失败测试：`chronological_split` 返回接近 60/20/20 的顺序切分，且质量事件连续区间不能跨越边界。
- [x] 运行 `.venv/bin/python -m pytest tests/test_data.py -q`；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq.data'` 失败。
- [x] 实现 `load_sensor_csv`：把 `NULL` 解析为缺失值、拒绝乱序和重复时间；按上游固定 MST（UTC-07:00）解释无时区墙上时间，再转换为 UTC；只保留原始值、校正值和质量列。
- [x] 实现 `chronological_split`：以行数计算 60/20/20 初始边界，从所有合法边界对中确定性选择最近组合；返回独立副本组成的冻结 `DatasetSplit`。
- [x] 实现下载脚本：只允许两个固定文件名，使用固定 commit 的 raw URL，30 秒超时并流式下载到临时文件；SHA-256 通过后原子替换，失败时保留原文件并清理临时文件。
- [x] 在 `data/README.md` 记录固定来源与哈希，区分 pyhydroqc 代码的 BSD-3-Clause 与关联 HydroShare 数据资源的 CC BY 4.0，并说明质量字段不是污染标签。
- [x] 运行全部数据测试和下载脚本；两个文件校验成功、首时间均正确转换为 `07:00Z`，且 Git 状态不出现原始 CSV。
- [x] 提交：`ccd6469 feat: add reproducible water sensor data pipeline`，并以 `434b99c` 完成时间、超时和许可审查修复。

**完成证据（2026-10-13）：** 专测 18 个、全量 107 个测试通过；真实文件 SHA-256、MST→UTC、数据契约、质量事件安全切分、下载超时/清理和 Git 忽略均验证；规格与代码质量审查均为 `APPROVED`。

**下一步：** 建立简单规则基线；验收条件是缺失、越界、卡值和突跳都能产生结构化点标记。

## Task 4：实现规则点检测器

**Files:**
- Create: `src/clearsignal_wq/detectors.py`
- Create: `tests/test_detectors.py`

- [x] 写参数化失败测试，覆盖：15 分钟缺口、重复值卡住至少 8 点、pH 超出 0–14、溶解氧为负、按训练段中位绝对偏差识别突跳。
- [x] 写防泄漏测试：修改验证段极值不得改变训练段拟合出的阈值。
- [x] 运行 `.venv/bin/python -m pytest tests/test_detectors.py -q`；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq.detectors'` 失败。
- [x] 实现冻结的 `RuleConfig`，默认 `expected_interval_minutes=15`、`stuck_run_points=8`、`jump_mad_multiplier=8.0`，数值范围只承担数据完整性检查，不承担饮用安全判断。
- [x] 实现 `fit_rule_detector(train)`，只从训练段计算每个传感器的一阶差分中位数与 MAD；验证段极值不会改变已拟合统计。
- [x] 实现 `detect_rule_anomalies(frame, fitted)`，输出按 `(timestamp, sensor, code)` 稳定排序的 `PointFlag` 元组；代码限定为 `missing_interval`、`out_of_physical_range`、`stuck_value`、`sudden_jump`。
- [x] 加固数据边界：训练与检测共用严格时序索引、真实数值类型、有限值和安全差分检查；卡值规则不依赖 MAD 是否可拟合，输入保持不变。
- [x] 运行专项测试、全量测试、Ruff 和 diff 检查；专项 `79 passed`、全量 `186 passed`，规格与代码质量审查均为 `APPROVED`。
- [x] 提交主实现 `ba7b6e6 feat: add deterministic sensor rule detector`；审查加固完成于 `d823dfd`。

**完成证据（2026-10-13）：** 四类规则产生稳定、冻结的 `PointFlag`；相同数据与配置结果一致，训练阈值不读取未来数据。非法时间索引、非数值、非有限值和无符号差分回绕均有回归测试；专项 79 个、全量 186 个测试通过，规格与代码质量审查均为 `APPROVED`。

**下一步：** 把点标记合并成可处理事件；验收条件是 30 分钟以内的相关标记合并，较远标记保持独立。

## Task 5：实现事件合并与标签提取

**Files:**
- Create: `src/clearsignal_wq/events.py`
- Create: `tests/test_events.py`

- [x] 写失败测试：同一传感器相隔 30 分钟以内的点合并；超过 30 分钟分开；不同传感器同一窗口进入同一事件；事件 ID 对同样输入保持稳定。
- [x] 写失败测试：`*_qual` 非空的连续片段被提取成“技术人员数据质量标签事件”，其标签不得命名为污染。
- [x] 运行 `.venv/bin/python -m pytest tests/test_events.py -q`；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq.events'` 失败。
- [x] 实现 `group_flags_into_events(flags, max_gap_minutes=30)`，事件 ID 使用开始时间、结束时间和排序后的传感器集合计算 SHA-256 前 12 位；相同主排序键使用证据内容确定性打破平局。
- [x] 实现 `labelled_quality_events(frame)`，仅从质量字段创建 `DetectionEvent`，并固定 `source_label="technician_data_quality"`；标签证据不使用污染或安全结论。
- [x] 运行专项测试、覆盖率、全量测试、Ruff、格式和 diff 检查；专项 `24 passed`、模块覆盖率 99%、全量 `210 passed`，主代理规格与代码质量审查通过。
- [x] 提交：`28fd8a7 feat: aggregate point flags into events`。

**完成证据（2026-10-13）：** 30 分钟边界、窗口外分离、跨传感器合并、稳定 ID、乱序输入、证据平局、非法窗口/索引、非 UTC 转换和输入不可变均有回归测试；技术人员标签按传感器连续片段提取并固定为 `technician_data_quality`，不会被误写为污染。

**下一步：** 建立事件级评价和规则基线报告；验收条件是指标计算可手算验证，并生成训练/验证两段结果。

## Task 6：建立事件级评价与规则基线

**Files:**
- Create: `src/clearsignal_wq/evaluation.py`
- Create: `scripts/run_evaluation.py`
- Create: `tests/test_evaluation.py`
- Modify: `../总纲.md`

- [x] 写失败测试，用三个预测事件和两个标签事件手算 `recall=0.5`、`precision=1/3`、检测延迟和每干净日无效告警率。
- [x] 写失败测试：零标签、零预测、零干净天数都返回有限值或明确异常，不产生 `NaN`。
- [x] 运行测试；实际因 `ModuleNotFoundError: No module named 'clearsignal_wq.evaluation'` 失败。
- [x] 实现区间重叠匹配：一个预测事件最多匹配一个标签事件，按开始时间稳定贪心匹配；计算 `EventMetrics`，并按 UTC 日期计算干净天数。
- [x] 实现 `run_evaluation.py --model rules --split train|validation`，输出稳定排序 JSON 到 `artifacts/metrics/rules-<split>.json`，包含数据哈希、配置、事件数、四项指标和 Git commit。
- [x] 运行训练与验证基线：

```bash
python scripts/run_evaluation.py --model rules --split train
python scripts/run_evaluation.py --model rules --split validation
```

- [x] 在 `../总纲.md` 写入真实数值，并在运行 ARIMA 前锁定候选晋级公式。由于规则验证召回已为 `1.0`，把不可达到的字面 `baseline + 0.05` 做候选运行前的上限修正：召回至少为 `min(1.0, baseline + 0.05)`；无效告警率不超过规则基线 `+0.10/天`；精确率不得下降超过 `0.05`。
- [x] 运行专项测试、100% 模块覆盖率、全量测试、Ruff、格式和 diff 检查；专项 `22 passed`、全量 `232 passed`。
- [x] 提交：子仓库 `ade3a97 feat: evaluate event-level rule baseline`，输入契约测试加固 `b14678d`；父仓库单独提交门槛与真实数值。

**完成证据（2026-10-13）：** 训练：召回 `0.6086956522`、精确率 `0.0100214746`、无效告警 `13.4271844660/天`、平均检测延迟 `36.4285714286` 分钟；验证：召回 `1.0`、精确率 `0.0135135135`、无效告警 `7.3/天`、平均检测延迟 `0.0` 分钟。两次重复生成的文件 SHA-256 一致；总纲含固定门槛和生成命令。

**下一步：** 实现 ARIMA 动态阈值候选；验收条件是先做验证集晋级判断，再且仅在晋级后读取冻结测试集。

## Task 7：实现 ARIMA 动态阈值候选与晋级判断

**Files:**
- Modify: `src/clearsignal_wq/detectors.py`
- Modify: `scripts/run_evaluation.py`
- Modify: `tests/test_detectors.py`
- Modify: `../总纲.md`

- [x] 写失败测试：模型只接收训练帧；输出残差超过训练残差中位数加 `6 × MAD` 的点；常数序列或拟合失败时返回带 `model_fallback` 证据的规则结果。
- [x] 写失败测试：模型选择函数只接受训练与验证指标，参数类型中不存在测试指标。
- [x] 运行相关测试；实际因缺少 `ArimaConfig` 和 `arima_meets_gate` 在收集阶段失败。
- [x] 为每个传感器实现固定阶数 `ARIMA(2, 1, 2)`；阈值只从训练残差计算，不搜索阶数，不使用测试数据。
- [x] 将连续 ARIMA 点按 Task 5 的事件逻辑合并，并让评价脚本支持 `--model arima`；测试段在数据加载前强制检查冻结模型决定。
- [x] 运行训练与验证候选：

```bash
python scripts/run_evaluation.py --model arima --split train
python scripts/run_evaluation.py --model arima --split validation
```

- [x] 按 Task 6 门槛作单次判断：ARIMA 验证召回 `0.8`、精确率 `0.0110803324`、无效告警 `7.14/天`，未达到召回 `1.0` 门槛；最终保留规则基线，ARIMA 仅作实验记录。
- [x] ARIMA 测试路径被程序拒绝；仅运行 `rules` 冻结测试，得到召回 `0.7368421053`、精确率 `0.0425531915`、无效告警 `8.2894736842/天`、平均延迟 `142.5` 分钟；未根据测试结果更改模型选择。
- [x] 运行专项测试、全量测试、Ruff、格式和 diff 检查；相关专项 `108 passed`、全量 `239 passed`。
- [x] 提交：子仓库 `94bca9a feat: evaluate ARIMA anomaly candidate`，诊断加固 `1c3143a`；父仓库单独记录模型决定。

**完成证据（2026-10-13）：** `do` 未收敛并明确回退规则，`cond/ph/temp/turb` 成功拟合；ARIMA 验证文件重复生成 SHA-256 稳定为 `2f10d183670048185ec3f9590ee5ac3f41977be5de657e4abe79eb3e1eb9253b`。候选未晋级，程序阻止 ARIMA 读取测试段；规则测试文件 SHA-256 为 `5893f05ee10a7fe7d15e54f26e2211af38fc4d03cc0d26f155b97593bbe1babf`，不含事后调参。

**下一步：** 增加可靠度和跨传感器证据；验收条件是单传感器故障不会因自身异常分数高而被提升为疑似水质事件。

## Task 8：实现传感器可靠度与跨传感器一致性

**Files:**
- Create: `src/clearsignal_wq/reliability.py`
- Create: `tests/test_reliability.py`

- [x] 写失败测试：缺失、卡值、越界和质量标签分别降低单个传感器可靠度；分数限制在 `[0, 1]`；相同输入结果完全相同。
- [x] 写失败测试：30 分钟窗口内至少两个可靠传感器同向变化时 `corroborating_sensor_count >= 2`；仅单个低可靠度传感器异常时为 0。
- [x] 运行测试；实际因缺少 `clearsignal_wq.reliability` 在收集阶段失败。
- [x] 实现 `sensor_reliability(frame, flags, window)`：从 1.0 开始，按固定权重扣除近期缺失、卡值、越界和质量标签比例，并裁剪到 `[0, 1]`。
- [x] 实现 `assess_event(event, frame, flags)`，返回受影响传感器、可靠度映射、跨传感器数量、是否含数据完整性证据和结构化证据项。
- [x] 完成边界加固：完全缺失或完全质量标签必须跌破 `0.6` 可靠阈值；传感器特定最小变化量排除数值噪声；事件与上下文 flags 合并，且不丢失早期完整性证据。
- [x] 运行测试与 Ruff；Task 8 专项 `20 passed`、模块覆盖率 `90%`、全量 `259 passed`，Ruff、格式与 diff 检查通过，最终只读审查无 P1/P2。
- [x] 提交：`c4e3922 feat: assess sensor reliability and corroboration`。

**完成证据（2026-10-16）：** 事件证据已区分“异常强”与“传感器可信”；只有达到可靠阈值、且在 30 分钟内超过各自最小变化量的同向传感器才计入佐证。数据完整性证据保持结构化，同一输入产生确定性结果。

**下一步：** 实现四类确定性分诊；验收条件是优先级、证据强度、动作和限制都由结构化证据生成。

## Task 9：实现分诊引擎与解释模板

**Files:**
- Create: `src/clearsignal_wq/triage.py`
- Create: `tests/test_triage.py`

- [x] 写表驱动失败测试，覆盖以下固定优先级：

```text
1. 时间戳缺口、重复、无效范围 -> data_integrity_issue
2. 单一低可靠度传感器持续异常 -> sensor_fault_or_drift
3. 至少两个可靠传感器同窗一致变化 -> possible_water_quality_event
4. 其他异常 -> insufficient_evidence
```

- [x] 写文案失败测试：所有状态必须含建议动作和限制；输出不得出现 `safe`、`drinkable`、`confirmed contamination`、`水安全`、`可以饮用` 或 `污染已确认`。
- [x] 运行测试；实际因缺少 `clearsignal_wq.triage` 在收集阶段失败。
- [x] 实现 `triage_event`，按上述优先级返回 `TriageEvent`；证据强度只允许 low/medium/high，不伪装为概率。
- [x] 固定动作模板：检查数据链路、清洁并校准传感器、现场复测并视结果送实验室、继续观察并安排复测。
- [x] 固定限制模板：`本结果不是饮用安全或污染确认结论`；合成场景额外写明 `本事件由版本化场景生成器注入`。
- [x] 加固事件契约：拒绝空 flags、传感器集合或时间边界不一致，同时间重复 flag 不算持续异常；`model_fallback` 从 event 或 assessment 都以固定安全文案保留。
- [x] 运行测试与 Ruff；Task 9 专项 `24 passed`、模块覆盖率 `95%`、全量 `283 passed`，Ruff、格式、diff 和敏感信息检查通过，最终只读审查无 P1/P2。
- [x] 提交：`3853fb7 feat: triage water sensor events with evidence`。

**完成证据（2026-10-19）：** 四类状态的边界和优先级已由表驱动测试锁定；缺口、重复时间戳和无效范围的完整性规则优先于传感器故障与跨传感器佐证。动作、限制和证据文案全部由固定模板生成，不依赖 LLM，不回显上游任意结论。

**下一步：** 建立三个可复现合成场景；验收条件是每个场景稳定落入预期分诊且不会修改输入帧。

## Task 10：实现版本化合成场景

**Files:**
- Create: `src/clearsignal_wq/scenarios.py`
- Create: `tests/test_scenarios.py`
- Modify: `src/clearsignal_wq/reliability.py`
- Modify: `src/clearsignal_wq/triage.py`
- Modify: `tests/test_reliability.py`

- [x] 写失败测试：输入帧保持不变；相同种子字节级相同；不同种子只改变注入窗口；非法幅度、时长或未知场景抛出 `ValueError`。
- [x] 写失败测试，固定三个端到端预期：
  - `correlated_shift_v1` -> `possible_water_quality_event`
  - `single_sensor_drift_v1` -> `sensor_fault_or_drift`
  - `missing_interval_v1` -> `data_integrity_issue`
- [x] 运行测试；实际因缺少 `clearsignal_wq.scenarios` 在收集阶段失败。
- [x] 实现 `ScenarioConfig(name, seed=20261011, start_fraction=0.55, duration_points=16)` 和 `inject_scenario(frame, config)`，使用深拷贝并返回 `(modified_frame, ScenarioManifest)`。
- [x] 多传感器场景只改变 pH、电导率和溶解氧且保留现实量级；漂移场景只线性改变 pH；数据完整性场景删除连续 8 个时间点。
- [x] `ScenarioManifest` 记录名称、版本、种子、UTC 窗口、参数和 `synthetic_scenario` 来源。
- [x] 修正质量标签语义：质量标签继续降低传感器可靠度，但不再冒充时间戳缺口、重复时间戳或无效范围等数据完整性问题。
- [x] 运行测试与 Ruff；全量 `297 passed`，覆盖率 `93.32%`，Ruff、改动文件格式和 diff 检查通过。
- [x] 提交：`6d0bcf2 feat: add reproducible water quality scenarios`。

**完成证据（2026-10-21）：** 三个演示场景在相同种子下字节级复现，不修改输入帧；不同种子只移动注入窗口。`correlated_shift_v1`、`single_sensor_drift_v1`、`missing_interval_v1` 的全部输出事件分别稳定进入疑似水质事件、传感器故障或漂移、数据完整性问题。manifest 固定记录版本、种子、UTC 窗口、参数和合成来源。

**下一步：** 串联完整流水线与降级路径；验收条件是模型失败时不静默，并产出可供 UI 直接消费的结果。

## Task 11：串联流水线与模型降级

**Files:**
- Create: `src/clearsignal_wq/pipeline.py`
- Create: `tests/test_pipeline.py`
- Modify: `scripts/run_evaluation.py`

- [x] 写失败测试：公开数据与三种场景都返回按优先级排序的 `PipelineResult`；相同输入、配置和模型版本返回相同事件 ID 与分诊。
- [x] 写失败测试：ARIMA 拟合异常时回退规则检测，结果包含 `model_fallback` 证据并把证据强度降一级。
- [x] 写失败测试：缺少必需列时流水线停止并向调用方抛出可操作的 `DataContractError`，不返回空成功结果。
- [x] 运行测试；实际因缺少 `clearsignal_wq.pipeline` 在收集阶段失败。
- [x] 实现 `run_pipeline`：校验 -> 拟合/检测 -> 事件合并 -> 可靠度评估 -> 分诊 -> 稳定排序；模型名称只允许 `rules` 或 `rules_arima`，默认模型仍固定为已晋级的规则基线。
- [x] `PipelineResult` 记录训练与目标数据的稳定哈希、配置版本、模型版本、来源、事件和运行警告。
- [x] 让评价脚本调用同一流水线，删除独立的拟合、检测和事件合并逻辑；规则与 ARIMA 历史验证指标保持不变。
- [x] 运行 `python -m pytest --cov=clearsignal_wq --cov-report=term-missing --cov-fail-under=80`；全量 `306 passed`，总覆盖率 `93.50%`、流水线模块 `97%`，Ruff、改动文件格式和 diff 检查通过。
- [x] 提交：`383a33c feat: orchestrate explainable triage pipeline`。

**完成证据（2026-10-21）：** 唯一生产路径已同时服务公开数据、三个合成场景和评价脚本；相同输入返回相同哈希、事件 ID、分诊和优先级排序。ARIMA 拟合失败会回退现有规则证据，在事件和运行警告中保留 `model_fallback`，并把结果证据强度降一级。规则验证仍为召回 `1.0`、无效告警 `7.3/天`；ARIMA 验证仍为召回 `0.8`、无效告警 `7.14/天`，未改变既有晋级结论。

**下一步：** 构建 Streamlit 运营工作台；验收条件是无需营销首页即可完成“选择事件 -> 看证据 -> 分派动作”。

## Task 12：实现 Streamlit 运营工作台

**Files:**
- Create: `app.py`
- Create: `tests/test_app_smoke.py`

- [x] 写失败冒烟测试，使用 Streamlit `AppTest` 启动 `app.py`，断言页面标题、站点选择、模式选择、事件队列、时间线区域、证据区和限制文本存在。
- [x] 写失败测试：选择任一合成场景后页面始终显示“合成场景”；应用文本不含禁用安全结论。
- [x] 运行 `python -m pytest tests/test_app_smoke.py -q`；先因 `app.py` 不存在按预期失败。
- [x] 实现单屏工作台：顶部状态带、左侧事件队列、中间 Plotly 多传感器时间线、右侧证据与动作；不添加落地页或功能说明卡。
- [x] 使用图标、文字和颜色共同编码四类状态；卡片圆角不超过 8px；按钮使用 Streamlit 原生图标能力或简洁文字命令。
- [x] 加入公开真实数据和三个合成场景选择；真实数据模式显示来源、固定 commit 和数据质量限制。
- [x] 将“标记为待复测/待校准/待检查链路/已升级”保存在 `st.session_state`，明确标为演示会话状态，不写回源数据。
- [x] 所有模型逻辑都从 `clearsignal_wq.pipeline` 调用，`app.py` 不重新计算阈值或分诊。
- [x] 运行冒烟测试、全套 pytest、Ruff；冒烟测试 `1 passed`，全量 `308 passed`、总覆盖率 `93.50%`，Ruff、格式和 diff 检查通过。
- [x] 提交：`feat: build ClearSignal operations dashboard`。

**完成证据（2026-10-22）：** 本地工作台可完成“选择模式与事件 -> 查看四传感器时间线和结构化证据 -> 保存演示会话人工动作”的单一主流程。公开模式固定显示 pyhydroqc 来源 commit 与数据质量边界；三个合成模式始终显示“合成场景”，并聚焦注入窗口。真实 CSV 暴露的全空浮点质量列兼容问题已在共享场景注入器修复并加入回归测试。`AppTest` 实际切换四种模式、保存动作且不出现禁用安全结论；全量 `308 passed`，覆盖率 `93.50%`。

**下一步：** 做真实浏览器和视觉验收；验收条件是桌面与移动视口无重叠、无截断，关键交互可由 Playwright 重复执行。

## Task 13：完成浏览器端到端与视觉验收

**Files:**
- Create: `tests/e2e/test_dashboard.py`
- Create: `scripts/run_app.sh`
- Modify: `pyproject.toml`

- [x] 写 Playwright 失败测试：打开工作台，切换到 `single_sensor_drift_v1`，选择首个事件，断言分诊为传感器故障、显示校准动作和合成标识。
- [x] 写失败测试：切换 `correlated_shift_v1` 后状态改变为疑似水质事件，并显示现场复测/实验室确认动作。
- [x] 创建 `scripts/run_app.sh`，使用 `exec python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port "${PORT:-8501}"`。
- [x] 检查本机 Playwright Chromium；已安装版本 `153.0.8010.12`，无需重复下载，启动应用并执行 E2E。
- [x] 用 Playwright 在 `1440×900` 与 `390×844` 截图检查：文字不溢出、事件列表和证据区不重叠、时间线非空、移动端按稳定顺序堆叠。
- [x] 截图仅放 `artifacts/visual-check/`，不提交；把检查结果、视口、日期和发现写入 `docs/visual-qa.md`。
- [x] 修复顶部来源摘要截断后重新运行 E2E、全套 pytest、Ruff；E2E `2 passed`，全量 `310 passed`、覆盖率 `93.50%`，Ruff 通过。
- [x] 提交：`test: verify ClearSignal dashboard flow`。

**完成证据（2026-10-22）：** 两个关键场景均由 Playwright 从独立随机端口冷启动并完成真实浏览器交互。桌面 `1440×900` 和移动 `390×844` 均无横向溢出；移动端三个主区按设计顺序纵向堆叠；两个视口的 Plotly 图表均检测到 4 条非空折线。首次截图发现顶部来源摘要被 `st.metric` 截断，已改为可换行状态文本并复测通过。详细证据见 `docs/visual-qa.md`。

**下一步：** 补齐公开说明、第三方许可和短演示脚本；验收条件是新用户按 README 能在 10 分钟内运行应用。

## Task 14：完成 README、许可归属与演示材料

**Files:**
- Create: `README.md`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `demo/demo_script.md`
- Modify: `研究结论.md`
- Modify: `../总纲.md`

- [x] 写英文公开 README，结构固定为：问题、目标用户、演示、工作原理、数据来源、评价、安装运行、测试、限制、负责任使用、项目结构、团队。
- [x] README 明确区分：真实数据质量事件指标、合成场景回归结果、没有真实污染标签；不得把合成准确率宣传为现实污染检测准确率。
- [x] 在 `THIRD_PARTY_NOTICES.md` 记录 pyhydroqc 仓库、固定 commit、BSD-3-Clause、数据文件、原作者和本项目未复制原始数据。
- [x] 写中文操作提示加英文口播的短演示稿；共 279 个英文词，按 90 词/分钟约 3 分 06 秒口播，加操作等待目标约 3 分 20 秒。
- [x] 未把本地截图加入 README；视觉证据保留在 Git 忽略目录，公开材料敏感信息扫描只命中演示稿中的安全提醒。
- [x] 更新 `研究结论.md` 和 `../总纲.md`：记录实现状态、测试数量、覆盖率、最终模型选择、真实指标、演示材料路径、明确下一步；跨站点结果留待 Task 15 冻结检查。
- [x] 执行 README 命令的干净环境复现；临时 Python 3.12 环境完成安装、数据哈希校验、AppTest 和 Streamlit HTTP 200，实际耗时 `100.61` 秒。
- [x] 提交：子仓库 `docs: document ClearSignal WQ prototype`；父仓库 `docs: record ClearSignal prototype evidence`。

**完成证据（2026-10-22）：** README 在临时全新环境复现，第三方软件与数据许可分别归属，279 词演示稿按较慢语速仍低于 3 分 50 秒。公开文档本地链接全部存在，敏感信息扫描无凭证、邮箱或绝对路径；真实数据质量指标、合成场景和未建立现实污染检测准确率的边界均明确。

**下一步：** 执行发布前安全与完整性检查；验收条件是代码、文档、测试、演示和平台字段均有明确证据。

## Task 15：发布前验证与提交包准备

**Files:**
- Create: `SUBMISSION.md`
- Modify: `../总纲.md`

- [x] 运行完整质量门：全量 `311 passed`、覆盖率 `93.50%`，`ruff check .` 与 `git diff --check` 通过。

```bash
python -m pytest --cov=clearsignal_wq --cov-report=term-missing --cov-fail-under=80
python -m ruff check .
git diff --check
```

- [x] 运行敏感信息扫描：当前工作树只命中文档中的安全检查说明；未发现凭证、私人邮箱或绝对路径。历史作者审计发现最早 4 个提交含私人邮箱，首次公开前必须经用户批准后重写历史并复扫。

```bash
rg -n --hidden -g '!.git/**' -g '!.venv/**' \
  '(api[_-]?key|secret|token|password|BEGIN [A-Z ]+PRIVATE KEY|@drew\.edu|/Users/)' .
```

任何命中必须逐条判断：测试中的禁用词或文档规则可保留；真实凭证、邮箱和本地路径必须删除并重新扫描。

- [x] 从空的 `data/raw/` 开始执行下载、评价和应用启动；临时干净克隆下载两份文件、生成规则验证 JSON、返回 HTTP 200，且 Git 状态保持为空。
- [x] 对 `MainStreet2019` 冻结测试和 `FranklinBasin2017` 跨站点检查各运行一次。MainStreet 指标保持召回 `0.7368`、精确率 `0.0426`、无效告警 `8.2895/天`；Franklin 未调参验证为召回 `0.7727`、精确率 `0.1977`、无效告警 `9.0/天`、延迟 `20` 分钟。
- [x] 创建 `SUBMISSION.md`，已填写本地可证实字段；GitHub、演示、Slides/PDF 和平台 URL 明确标为待发布后填写，不伪造链接。
- [x] 运行 `git status --short`，确认没有原始数据、缓存、截图临时文件、`.env` 或未解释的改动。
- [ ] 更新 `../总纲.md` 为 `submission_ready`，记录 Git commit、测试结果、覆盖率、可运行 URL、视频时长和仍需用户完成的平台动作。
- [ ] 提交：子仓库 `git commit -m "docs: prepare ClearSignal WQ submission"`；父仓库 `git commit -m "docs: mark ClearSignal submission ready"`。
- [x] 用户已明确批准清理历史并公开 GitHub；仓库发布到 `https://github.com/Cedric-uxb/clearsignal-wq`。尚未授权或执行比赛平台 `Publish`。

**当前阻塞（2026-10-22）：** Git 历史已获授权清理，公开仓库与 7 页英文 Slides/PDF 已完成。提交包仍需演示视频和平台项目页 URL，尚未达到 `submission_ready`。

**完成证据：** 本地提交包达到 `submission_ready`，并能区分“材料准备完成”和“平台已发布”。

**Slides 完成证据（2026-10-22）：** 已生成 7 页英文公开演示稿 `presentation/ClearSignal-WQ-Deck.pptx` 与 PDF，使用真实 Streamlit 截图和冻结指标。PDF 为 16:9、7 页；全页渲染检查未发现空白页、文字越界、截图拉伸或元素重叠。责任边界明确保留“传感器数据质量标签不是污染确认”和“必须人工复核”。

**下一步：** 按 `demo/demo_script.md` 录制并上传 3-4 分钟演示视频；验收后填写平台项目页并保存成功回执。

## 最终验收清单

- [ ] 无 API 密钥、无 SWaT 访问权限、无硬件时仍可完整运行。
- [ ] 数据来源、固定 commit 和 SHA-256 可复核。
- [ ] 时间切分防止未来信息泄漏，冻结测试不参与模型选择。
- [ ] 规则与 ARIMA 的选择遵守预注册门槛。
- [ ] 四类分诊均有测试、证据、限制和人工下一步。
- [ ] 三个合成场景明确标注且可复现。
- [ ] 真实指标只描述传感器数据质量事件，不冒充污染检测表现。
- [ ] 单元、集成和浏览器测试通过，覆盖率至少 80%。
- [ ] 桌面与移动视口无内容重叠、截断或空白图表。
- [ ] README、演示脚本和提交字段一致。
- [ ] 仓库不含 token、邮箱、本地路径、原始数据或隐私信息。
- [ ] 只有平台成功回执出现后，总纲状态才改为 `submitted`。
