#!/usr/bin/env node
/**
 * 把官方 @lumina/workshop-sdk 的 ESM 产物内联成一个 IIFE，写进 ui/index.html。
 *
 * 为什么不用打包器：工坊要求模块运行时是「单文件、全部资源内联、无外链」，
 * 而本模块没有构建链（纯 HTML + 原生 JS）。SDK 只有 3 个 ESM 文件、且彼此只依赖
 * 同目录的 contracts.js，所以这里做一个最小的、确定性的 ESM→IIFE 转换：
 *   - 删掉 import 语句（同作用域拼接后符号已在作用域内）
 *   - 去掉 export 前缀
 *   - 包一层 IIFE，把公开符号挂到 window.LuminaWorkshop
 *
 * 产物可复现：只依赖 node_modules 里的 SDK 版本（由 package.json 的不可变
 * Release URL 安装，见 pnpm-lock.yaml 的 integrity），不联网、无时间戳；
 * 中间产物写到 .tmp/，不进仓库，也不从 vendor/ 之类的本地副本读取。
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PKG = join(ROOT, "node_modules", "@lumina", "workshop-sdk", "package.json");
const DIST = join(ROOT, "node_modules", "@lumina", "workshop-sdk", "dist");
const HTML = join(ROOT, "ui", "index.html");
const OUT_DIR = join(ROOT, ".tmp");
const OUT = join(OUT_DIR, "sdk.bundle.js");

const pkg = JSON.parse(readFileSync(PKG, "utf8"));
if (pkg.version !== "1.0.2") {
  throw new Error(`SDK 版本应为 1.0.2，实际 ${pkg.version}`);
}

/** 去掉 import 行与 export 前缀，得到可直接拼接的函数体。 */
function flatten(source, file) {
  return source
    .replace(/^\s*import\s+[^;]*?;\s*$/gm, "")
    .replace(/^export\s+(?=(const|let|var|function|class|async))/gm, "")
    .trim()
    .concat(`\n// <<< ${file}`);
}

const order = ["contracts.js", "theme.js", "client.js"];
const body = order.map((f) => flatten(readFileSync(join(DIST, f), "utf8"), f)).join("\n\n");

const api = [
  "connectWorkshop",
  "WorkshopClientError",
  "WORKSHOP_API_VERSION",
  "WORKSHOP_MANIFEST_VERSION",
  "WORKSHOP_RPC_VERSION",
  "WORKSHOP_PERMISSION_NAMES",
  "applyWorkshopUiState",
  "createRequestEnvelope",
];

const banner = `/* @lumina/workshop-sdk ${pkg.version} —— 由 tools/bundle_sdk.mjs 内联，请勿手改（改 package.json 后重跑 pnpm bundle） */`;
const bundle = `${banner}
(function () {
"use strict";
${body}

  window.LuminaWorkshop = { ${api.join(", ")} };
})();
`;

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(OUT, bundle, "utf8");
const digest = createHash("sha256").update(bundle).digest("hex").slice(0, 16);

// 注入 HTML
const html = readFileSync(HTML, "utf8");
const open = '<script id="lumina-sdk">';
const i = html.indexOf(open);
if (i < 0) throw new Error('ui/index.html 里找不到 <script id="lumina-sdk"> 占位');
const j = html.indexOf("</script>", i);
if (j < 0) throw new Error("lumina-sdk 占位缺少结束标签");
const next = `${html.slice(0, i + open.length)}\n${bundle}${html.slice(j)}`;
writeFileSync(HTML, next, "utf8");

const kb = (bundle.length / 1024).toFixed(1);
console.log(`[ok] SDK ${pkg.version} 已内联：${kb} KB（bundle sha256:${digest}…）`);
