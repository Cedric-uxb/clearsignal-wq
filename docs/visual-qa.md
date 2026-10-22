# ClearSignal WQ 视觉验收

## 验收环境

- 日期：2026-10-22
- Streamlit：1.65.0
- Playwright：1.63.0
- Chromium：153.0.8010.12
- 数据模式：`single_sensor_drift_v1`、`correlated_shift_v1`
- 截图目录：`artifacts/visual-check/`，已由 Git 忽略，不进入公开仓库

## 自动检查

| 视口 | 场景 | 页面宽度 | 横向溢出 | Plotly 非空折线 | 主区布局 |
| --- | --- | ---: | --- | ---: | --- |
| 1440×900 | 单传感器漂移 | 1440px | 无 | 4 | 三栏同一基线 |
| 390×844 | 多传感器相关变化 | 390px | 无 | 4 | 事件队列、时间线、证据依次堆叠 |

移动视口三个主区的顶部位置依次为 `781.48px`、`1281.47px`、`1879.06px`，宽度均为 `358px`。顺序稳定，未发现互相覆盖。两个视口的摘要元素均通过 `scrollWidth <= clientWidth + 1` 检查。

## 人工截图检查

- `desktop-drift-top.png`：站点与模式控件完整；三栏不重叠；漂移事件显示橙色符号、文字状态和校准建议；四传感器图均可见。
- `mobile-correlated-top.png`：标题、控件、来源和运行摘要完整换行。
- `mobile-correlated-queue.png`：来源提示和事件队列按单列布局显示。
- `mobile-correlated-timeline.png`：事件表与时间线分区清晰，图例与折线非空。
- `mobile-correlated-evidence.png`：时间线结束后显示证据区；绿色符号、状态文字、受影响传感器和结构化证据没有重叠。

## 发现与修复

首次截图发现 `st.metric` 会截断 `Synthetic scenario / 合成场景`。已改为可换行、无卡片的状态文本，并重新执行 AppTest、E2E、桌面截图和移动截图。复测未再发现文字截断或横向溢出。

## 结论

Task 13 通过。浏览器主流程、两个关键场景和两个目标视口均有可重复证据；视觉验收没有改变检测或分诊逻辑。

下一步：执行 Task 14，补齐英文公开 README、第三方许可、中文操作提示加英文口播的短演示稿，并从干净环境验证运行说明。
