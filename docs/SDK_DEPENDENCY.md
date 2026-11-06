# SDK 依赖：按官方分发规范接入

> 本文件记录本仓库如何依赖 `@lumina/workshop-sdk`，以及一次可复现的核对过程。
> 规范原文要求：SDK 只经独立公开仓库的**不可变 GitHub Release** 分发；不发 `latest`、
> 不上 npm registry；依赖必须写成含确切版本的 Release URL；不得依赖本地 `vendor/`
> 目录、工作区 `workspace:` 路径或未发布的 SDK 源码。

## 1. 依赖声明（已符合规范）

`package.json`：

```json
"dependencies": {
  "@lumina/workshop-sdk": "https://github.com/lumina-layer-studio/Lumina-Workshop-SDK/releases/download/v1.0.2/lumina-workshop-sdk-1.0.2.tgz"
}
```

等价于规范给出的命令：

```bash
pnpm add --save-exact \
  https://github.com/lumina-layer-studio/Lumina-Workshop-SDK/releases/download/v1.0.2/lumina-workshop-sdk-1.0.2.tgz
```

`pnpm-lock.yaml` 把解析结果钉死到同一个 URL，并带完整性摘要：

```yaml
'@lumina/workshop-sdk@https://github.com/lumina-layer-studio/Lumina-Workshop-SDK/releases/download/v1.0.2/lumina-workshop-sdk-1.0.2.tgz':
  resolution: {integrity: sha512-UrkhqQvZubotsWIYN/rk/lIfz0tgHLDBiAluO9MnK1aXaZgfD6knkOeKf52WI5Tf0B74Yw8OoQrYDuMwARLZWg==, tarball: ...}
  version: 1.0.2
  engines: {node: '>=22'}
```

## 2. 资产核对（2026-11-06 实测）

用 GitHub API 读到的官方资产摘要，与仓库内的副本逐字节比对：

| 项目 | 值 |
| --- | --- |
| 资产名 | `lumina-workshop-sdk-1.0.2.tgz` |
| 大小 | 6,990 字节 |
| sha256（官方） | `f23f8d0b5181116e8173c0a6f4171405980269615f429be4805973ec4efa93ad` |
| sha256（仓库副本） | 同上，MATCH |
| tar 成员 | 11 项（`package/{LICENSE,README.md,package.json}` + `dist/{client,contracts,index,theme}.{js,d.ts}`） |
| 包内 `package.json` | `name=@lumina/workshop-sdk version=1.0.2 engines={node: '>=22'}` |
| 已安装版本 | `node_modules/@lumina/workshop-sdk` = 1.0.2 |

`tools/bundle_sdk.mjs` 只从 `node_modules/@lumina/workshop-sdk` 读 `dist/{contracts,theme,client}.js`，
做确定性 ESM→IIFE 转换后内联进 `ui/index.html` 的 `<script id="lumina-sdk">`；脚本里断言版本必须是
`1.0.2`，不对版本号做任何模糊匹配。

## 3. 本次修正：不再把构建产物放进 `vendor/`

以前 `bundle_sdk.mjs` 会把中间产物写到 `vendor/sdk.bundle.js`，而 `vendor/` 又被提交进了仓库
（里面还有一份解包的 SDK 与 tarball 副本）——这与「不得依赖本地 vendor 目录」的要求相抵触。

现在的做法：

- 中间产物改写到 `.tmp/sdk.bundle.js`（`.tmp/` 已在 `.gitignore`）；
- 删除仓库里的 `vendor/`；
- `.gitignore` 补上 `node_modules/`、`vendor/`、`build/`、`.test-tmp/`；
- 构建只依赖 `package.json` 声明的不可变 Release URL 经 `pnpm install` 得到的 `node_modules`。

改动前后 `ui/index.html` 的 sha256 完全一致（`07936a74…`），说明内联内容未变、构建可复现。

## 4. 复跑结果（改动后）

```text
$ python tools/build_package.py
197712 字节 / 解压 266920 字节 / 6 个文件
sha256=bccfe49619f38adcd99dd74c3c24938e1a29d3f7c20f206d2ec4fe9c972e9cb6
manifestSha256=da26be3c722a0d6f907dd45596b1533b12ab50019b2b3ef974f2ca4527bc61e8
（与改动前逐字节一致）

$ python tools/run_js_tests.py   → RESULT OK 83
$ python tests/test_registry_record.py → RESULT OK
$ python tools/verify_host_fixes.py    → RESULT OK 12
```

分发物本身不受影响：`.lumina-workshop` 包内仍只有 6 个白名单文件
（`manifest.json`、`ui/index.html`、`assets/icon.png`、`assets/gallery/screenshot.png`、
`README.md`、`LICENSE`），不含 `node_modules/` 与 `vendor/`。

## 5. 仍待完成（需要 git 才能做）

`node_modules/` 与 `vendor/` 此前已被提交进仓库，从工作区删除**不会**把它们移出 Git 索引，
需要在能执行 git 的环境里补一次：

```bash
git rm -r --cached node_modules vendor
git add .gitignore tools/bundle_sdk.mjs docs/SDK_DEPENDENCY.md
git commit -m "chore(sdk): consume @lumina/workshop-sdk 1.0.2 via immutable Release URL, drop committed node_modules/vendor"
git push origin main
```

（本机当前没有 `git` 可执行文件，也没有可用的 GitHub 凭据，因此这一步未执行。）
