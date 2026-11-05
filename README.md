# HeightForge 高度图 · Lumina 创意工坊模块

把一张图片转成高度图，并把结果交给 Lumina 做成浮雕 / 拼豆。
功能对齐桌面包 **HeightForge-1.3.1-win64**（能在浏览器沙箱里实现的部分）。

## 功能 / Features

- **10 种高度来源**：亮度（Rec.709 感知 / 线性光）、RGB 平均、最大通道、红/绿/蓝通道、
  透明度、饱和度、颜色距离（在图上点一下即可取色，选区算最高点）。
- **高低映射**：输入色阶（两条可拖的竖线 + 直方图 + 自动色阶 0.5%/99.5% 分位裁剪）、
  Gamma、S 曲线对比、高斯模糊、反相；越白越高、越黑越低。
- **输出量程**：输出下限/上限，把最低点与最高点钉在 0–100% 的任意高度；另提供物理高度
  （mm/cm/in），只影响交接的毫米尺寸与 OBJ，不改灰度值。
- **台阶化（区域分层）**：2–8 层亮度区间，每层单独设高度与边界羽化；亮度层按覆盖权重
  归一化平均。开启后 Gamma / 对比不参与，色阶仍决定区间位置。
- **预览**：并排 / 只看原图 / 只看高度图；默认**立体浮雕**（WebGL，可拖动旋转、调起伏夸张、
  切换单色材质 / 原图颜色），另有山体着色、灰度高度图、法线图（可调强度与绿通道翻转）。
- **导出**：16 位灰度 PNG、8 位灰度 PNG、法线图 PNG、OBJ 网格、参数 JSON（可附带）。
- **载入**：宿主原生选图、拖放文件、粘贴图片；无宿主时退化为本地选文件（独立模式）。

## 输出 / Output

- 「交给 Lumina」：标准 8 位 PNG，随宿主交接（`handoff.image`），并按物理高度给出
  `recommendedWidthMm` / `recommendedHeightMm`。
- 「导出」：浏览器内直接写 PNG（自研编码器，无外部依赖）或 OBJ / JSON。

## 隐私 / Privacy

模块只在本地处理像素：不上传图片、不访问网络、不写入任何凭据。申请的权限只有
`image.pick`（用户选图）与 `handoff.image`（把结果交给 Lumina），没有通用网络权限。

Everything runs locally in the sandboxed module frame. The module requests only
`image.pick` and `handoff.image`.

## 依赖 / Dependencies

宿主契约来自官方 `@lumina/workshop-sdk`，只通过公开仓库的**不可变 GitHub Release** 分发，
不发布 `latest`，也不上传 npm registry。依赖按要求锁到含确切版本的 Release URL（`--save-exact`）：

```json
"@lumina/workshop-sdk": "https://github.com/lumina-layer-studio/Lumina-Workshop-SDK/releases/download/v1.0.2/lumina-workshop-sdk-1.0.2.tgz"
```

```bash
pnpm install                # 按上面的 Release URL 拉取 1.0.2，并生成 pnpm-lock.yaml
node tools/bundle_sdk.mjs   # 把 SDK 内联进 ui/index.html（模块运行时必须自包含、无外链）
```

SDK 的 `connectWorkshop()` 负责握手（`lumina.workshop.ready` → `lumina.workshop.connect` + `MessagePort`）、
RPC 封装与超时/帧校验；模块侧只调用 `client.image.pick()`、`client.handoff.image()`、`client.lifecycle.ready()`。

## 构建 / Build

```bash
pnpm install                       # 首次：从 Release URL 拉取 SDK（版本固定）
node tools/bundle_sdk.mjs          # 内联 SDK 到 ui/index.html
python tools/build_package.py      # 产出 dist/*.lumina-workshop 并做静态检查
python tools/run_js_tests.py       # 引擎单测（无头浏览器）
python tests/test_registry_record.py
```

## 版本 / Version

1.2.0 — 对齐 HeightForge 1.3.1 的映射与导出能力；Workshop API `1.0.0` / Manifest `1`。
1.3.1 — 修四个验收问题：首次出图即可交接、已有图片时二次确认替换、宿主内收起无效导出并说明、台阶化后 Gamma/对比真正不参与且状态同步。
1.0.0 — 首个可安装版本（8 种来源、5 个预设、16 位 PNG 导出）。
