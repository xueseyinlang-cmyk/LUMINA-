#!/usr/bin/env python3
"""在无头 Chrome/Edge 里跑 ``ui/index.html`` 内联引擎的单元测试。

思路：从 ``ui/index.html`` 里抽出 ``<script id="engine">`` 的源码（唯一来源，
不在测试里复制一份），拼进一个断言页，再用 ``--headless --dump-dom`` 读回结果。
没有 Node、没有 npm，也不改模块本身的构建方式。

    python tools/run_js_tests.py
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

ENGINE_RE = re.compile(
    r'<script id="engine">(.*?)</script>', re.DOTALL
)

CASES = r"""
const E = window.HeightForgeEngine;
const results = [];
function ok(name, cond, extra) {
  results.push({ name, pass: !!cond, extra: extra === undefined ? "" : String(extra) });
}
function near(a, b, eps) { return Math.abs(a - b) <= (eps === undefined ? 1e-4 : eps); }

// --- 立体浮雕网格 ---------------------------------------------------------
{
  const w = 8, h = 4, f = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) f[i] = (i % w) / (w - 1);   // 左低右高的斜坡
  const m = E.reliefMesh(f, w, h, { relief: 0.2, base: 0.05 });
  ok("浮雕：网格不超过原图", m.gw === 8 && m.gh === 4, `${m.gw}x${m.gh}`);
  const nTop = m.gw * m.gh;
  ok("浮雕：左低右高", m.positions[2] < m.positions[(m.gw - 1) * 3 + 2], `${m.positions[2]},${m.positions[(m.gw - 1) * 3 + 2]}`);
  ok("浮雕：最高点 = relief", Math.abs(Math.max(...Array.from({length: nTop}, (_, k) => m.positions[k * 3 + 2])) - 0.2) < 0.03);
  ok("浮雕：长边归一到 2", near(m.positions[0], -1) && near(m.positions[(m.gw - 1) * 3], 1));
  let maxIdx = 0; for (const v of m.indices) maxIdx = Math.max(maxIdx, v);
  ok("浮雕：索引不越界", maxIdx < m.positions.length / 3, maxIdx);
  ok("浮雕：斜坡法线朝左上", m.normals[3 * (m.gw + 3)] < 0 && m.normals[3 * (m.gw + 3) + 2] > 0);
  const big = E.reliefMesh(new Float32Array(1000 * 500), 1000, 500, { maxGrid: 100 });
  ok("浮雕：大图降采样", big.gw === 100 && big.gh === 50, `${big.gw}x${big.gh}`);
}
// --- 输入色阶 -------------------------------------------------------------
{
  const field = new Float32Array([0, 0.25, 0.5, 0.75, 1]);
  const out = E.mapField(field, 5, 1, {inLo: 0.25, inHi: 0.75, gamma: 1, contrast: 1, blur: 0, invert: false, outLo: 0, outHi: 1});
  ok("色阶：两端夹取", near(out[0], 0) && near(out[4], 1), `[${out[0]},${out[4]}]`);
  ok("色阶：中间线性", near(out[2], 0.5), out[2]);
  ok("色阶：单调", out[0] <= out[1] && out[1] <= out[2] && out[2] <= out[3] && out[3] <= out[4]);
}
// --- 输出量程 -------------------------------------------------------------
{
  const field = new Float32Array([0, 0.5, 1]);
  const out = E.mapField(field, 3, 1, {inLo: 0, inHi: 1, gamma: 1, contrast: 1, blur: 0, invert: false, outLo: 0.1, outHi: 0.5});
  ok("量程：下限", near(out[0], 0.1), out[0]);
  ok("量程：上限", near(out[2], 0.5), out[2]);
  ok("量程：中点", near(out[1], 0.3), out[1]);
}
// --- 反相 / 退化色阶 -------------------------------------------------------
{
  const field = new Float32Array([0, 0.3, 1]);
  const inv = E.mapField(field, 3, 1, {inLo: 0, inHi: 1, gamma: 1, contrast: 1, blur: 0, invert: true, outLo: 0, outHi: 1});
  ok("反相：端点互换", near(inv[0], 1) && near(inv[2], 0), `[${inv[0]},${inv[2]}]`);
  const thr = E.mapField(field, 3, 1, {inLo: 0.5, inHi: 0.5, gamma: 1, contrast: 1, blur: 0, invert: false, outLo: 0, outHi: 1});
  ok("退化色阶 → 二值", near(thr[0], 0) && near(thr[1], 0) && near(thr[2], 1), `[${thr[0]},${thr[1]},${thr[2]}]`);
}
// --- 亮度 / 颜色距离 / 饱和度 --------------------------------------------
{
  const rgba = new Uint8ClampedArray([255,255,255,255, 0,0,0,255, 200,20,20,255]);
  const luma = E.extractSource(rgba, "luma");
  ok("亮度：白=1 黑=0", near(luma[0], 1) && near(luma[1], 0), `[${luma[0]},${luma[1]}]`);
  const target = [200 / 255, 20 / 255, 20 / 255];
  const dist = E.extractSource(rgba, "color", target, 0.25);
  ok("颜色距离：目标色为峰值", near(dist[2], 1), dist[2]);
  ok("颜色距离：远处为 0", near(dist[1], 0, 1e-3), dist[1]);
  const sat = E.extractSource(new Uint8ClampedArray([128,128,128,255, 255,0,0,255]), "saturation");
  ok("饱和度：灰=0 纯红=1", near(sat[0], 0) && near(sat[1], 1), `[${sat[0]},${sat[1]}]`);
}
// --- gamma / 对比 ---------------------------------------------------------
{
  const field = new Float32Array([0.5]);
  const g = E.mapField(field, 1, 1, {inLo: 0, inHi: 1, gamma: 2, contrast: 1, blur: 0, invert: false, outLo: 0, outHi: 1});
  ok("gamma>1 压暗中间调", near(g[0], 0.25), g[0]);
  const flat = E.mapField(new Float32Array([0.25, 0.75]), 2, 1, {inLo: 0, inHi: 1, gamma: 1, contrast: 1, blur: 0, invert: false, outLo: 0, outHi: 1});
  ok("对比=1 不变", near(flat[0], 0.25) && near(flat[1], 0.75), `[${flat[0]},${flat[1]}]`);
  const punch = E.mapField(new Float32Array([0.25, 0.75]), 2, 1, {inLo: 0, inHi: 1, gamma: 1, contrast: 1.6, blur: 0, invert: false, outLo: 0, outHi: 1});
  ok("对比>1 拉开层次", punch[0] < 0.25 && punch[1] > 0.75, `[${punch[0].toFixed(3)},${punch[1].toFixed(3)}]`);
  ok("smoothstep 端点", near(E.smoothstep(0), 0) && near(E.smoothstep(1), 1) && near(E.smoothstep(0.5), 0.5));
}
// --- 模糊 -----------------------------------------------------------------
{
  const w = 32, h = 32;
  const src = new Float32Array(w * h);
  for (let i = 0; i < src.length; i++) src[i] = (i % 2 === 0) ? 0 : 1; // 棋盘噪声
  const blurred = E.blurField(src, w, h, 2);
  const v = (a) => { const m = E.stats(a).mean; let s = 0; for (const x of a) s += (x - m) ** 2; return s / a.length; };
  ok("模糊：方差下降", v(blurred) < v(src) * 0.5, `${v(src).toFixed(4)} → ${v(blurred).toFixed(4)}`);
  ok("模糊：均值基本不变", near(E.stats(blurred).mean, E.stats(src).mean, 0.02));
}
// --- 校验和 / PNG ---------------------------------------------------------
{
  const ascii = (s) => new TextEncoder().encode(s);
  ok("crc32 已知向量", E.crc32(ascii("123456789"), 0, 9) === 0xCBF43926, E.crc32(ascii("123456789"), 0, 9).toString(16));
  ok("adler32 已知向量", E.adler32(ascii("Wikipedia")) === 0x11E60398, E.adler32(ascii("Wikipedia")).toString(16));
}
{
  // 3×2 的高度场 → 16 位 PNG → 只解析 stored 块还原像素
  const w = 3, h = 2;
  const field = new Float32Array([0, 0.5, 1, 0.1, 0.2, 0.3]);
  const png = E.encodePng16(field, w, h);
  const sig = [0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a];
  ok("PNG 签名", sig.every((b, i) => png[i] === b));
  const dv = new DataView(png.buffer, png.byteOffset);
  ok("PNG 宽高", dv.getUint32(16) === w && dv.getUint32(20) === h);
  ok("PNG 位深 16 / 灰度", png[24] === 16 && png[25] === 0, `${png[24]}/${png[25]}`);

  // 找 IDAT
  let at = 8, idat = null;
  while (at < png.length) {
    const len = dv.getUint32(at);
    const type = String.fromCharCode(png[at + 4], png[at + 5], png[at + 6], png[at + 7]);
    if (type === "IDAT") idat = png.subarray(at + 8, at + 8 + len);
    at += 12 + len;
  }
  ok("PNG 有 IDAT", !!idat);
  // 解 stored deflate：0x78 0x01 + 若干块
  const raw = [];
  let p = 2;
  while (p < idat.length) {
    const header = idat[p];
    const final = header & 1;
    const len = idat[p + 1] | (idat[p + 2] << 8);
    for (let i = 0; i < len; i++) raw.push(idat[p + 5 + i]);
    p += 5 + len;
    if (final) break;
  }
  const stride = 1 + w * 2;
  ok("PNG 数据长度", raw.length === stride * h, `${raw.length}/${stride * h}`);
  let expect = [0, 0.5, 1, 0.1, 0.2, 0.3];
  let pixelOk = true;
  for (let y = 0; y < h; y++) {
    if (raw[y * stride] !== 0) pixelOk = false;         // filter = none
    for (let x = 0; x < w; x++) {
      const i = y * stride + 1 + x * 2;
      const value = (raw[i] << 8) | raw[i + 1];
      const want = Math.round(Math.min(1, Math.max(0, expect[y * w + x])) * 65535);
      if (value !== want) pixelOk = false;
    }
  }
  ok("PNG 像素往返一致", pixelOk);
}
// --- 统计 -----------------------------------------------------------------
{
  const s = E.stats(new Float32Array([0, 0.5, 1]));
  ok("统计 min/max/mean", near(s.min, 0) && near(s.max, 1) && near(s.mean, 0.5));
}

// === 与桌面版对齐的新增能力 ===============================================
function rgbaOf(r, g, b, a) {
  const n = r.length;
  const out = new Uint8ClampedArray(n * 4);
  for (let i = 0; i < n; i++) {
    out[i * 4] = r[i]; out[i * 4 + 1] = g[i]; out[i * 4 + 2] = b[i]; out[i * 4 + 3] = a ? a[i] : 255;
  }
  return out;
}

// --- 新来源：luma_linear / alpha / color_distance 别名 ---------------------
{
  const px = rgbaOf([26, 26], [26, 26], [26, 26]);
  const lin = E.extractSource(px, "luma_linear");
  const luma = E.extractSource(px, "luma");
  ok("来源 luma_linear：暗部被压低", lin[0] < luma[0], `${lin[0].toFixed(4)} < ${luma[0].toFixed(4)}`);
  const same = E.extractSource(px, "luma_linear");
  ok("来源 luma_linear：整幅一致", near(lin[0], same[0]) && near(lin[1], same[1]));
}
{
  const px = rgbaOf([200, 200], [100, 100], [50, 50], [255, 0]);
  const a = E.extractSource(px, "alpha");
  ok("来源 alpha：透明 = 0、不透明 = 1", near(a[0], 1) && near(a[1], 0), `[${a[0]},${a[1]}]`);
}
{
  const px = rgbaOf([255, 0], [0, 128], [0, 255]);
  const d = E.extractSource(px, "color_distance", [1, 0, 0], 0.5);
  const c = E.extractSource(px, "color", [1, 0, 0], 0.5);
  ok("来源 color_distance 与 color 同义", near(d[0], c[0]) && near(d[1], c[1]), `${d[0].toFixed(3)}/${c[0].toFixed(3)}`);
  ok("来源 color_distance：命中色最高", d[0] > 0.99 && d[1] < d[0], `${d[0].toFixed(3)} vs ${d[1].toFixed(3)}`);
}

// --- 直方图 / 自动色阶 -----------------------------------------------------
{
  const f = new Float32Array(256);
  for (let i = 0; i < 256; i++) f[i] = i / 255;
  const h = E.histogram(f);
  let sum = 0;
  for (let i = 0; i < 256; i++) sum += h[i];
  ok("直方图：总数等于像素数", sum === 256, sum);
  ok("直方图：单峰位置正确", h[0] === 1 && h[255] === 1 && h[128] === 1);
}
{
  // 90% 像素压在 0.2~0.4，自动色阶应把黑场抬起来
  const n = 1000;
  const f = new Float32Array(n);
  for (let i = 0; i < n; i++) f[i] = i < 900 ? 0.2 + (i % 100) / 500 : 0.95;
  const lv = E.autoLevels(f, 0.005, 0.995);
  ok("自动色阶：黑场被抬起", lv.lo > 0.15 && lv.lo < 0.45, lv.lo.toFixed(3));
  ok("自动色阶：白场接近最亮值", lv.hi > 0.85, lv.hi.toFixed(3));
  ok("自动色阶：区间非退化", lv.hi - lv.lo > 0.002);
}

// --- 区域分层（台阶化） ----------------------------------------------------
{
  const f = new Float32Array([0.1, 0.4, 0.9]);
  const layers = [
    { lo: 0, hi: 0.33, height: 0.15, feather: 0 },
    { lo: 0.33, hi: 0.66, height: 0.5, feather: 0 },
    { lo: 0.66, hi: 1, height: 0.85, feather: 0 },
  ];
  const out = E.applyLayers(f, layers, 0);
  ok("分层：三档各就各位", near(out[0], 0.15) && near(out[1], 0.5) && near(out[2], 0.85), `[${out[0]},${out[1]},${out[2]}]`);
}
{
  const f = new Float32Array([0.5]);
  const same = E.applyLayers(f, [], 0.3);
  ok("分层：空层表不改动", near(same[0], 0.5), same[0]);
}
{
  const f = new Float32Array([0.5, 0.9]);
  const layers = [
    { lo: 0, hi: 0.6, height: 0.2, feather: 0 },
    { lo: 0.4, hi: 1, height: 0.8, feather: 0 },
  ];
  const out = E.applyLayers(f, layers, 0);
  ok("分层：重叠区按权重平均", near(out[0], 0.5, 1e-3), out[0].toFixed(3));
  ok("分层：只命中一层时取该层高度", near(out[1], 0.8, 1e-3), out[1].toFixed(3));
}
{
  const f = new Float32Array([0.5]);
  const hard = E.applyLayers(f, [{ lo: 0, hi: 1, height: 0.2, feather: 0 }, { lo: 0, hi: 0.45, height: 0.9, feather: 0 }], 0);
  const soft = E.applyLayers(f, [{ lo: 0, hi: 1, height: 0.2, feather: 0.1 }, { lo: 0.4, hi: 1, height: 0.9, feather: 0.1 }], 0);
  ok("分层：羽化让边界出现中间值", soft[0] > 0.2 && soft[0] < 0.9, `${hard[0].toFixed(3)} → ${soft[0].toFixed(3)}`);
}

// --- 预览：法线图 / 山体着色 ----------------------------------------------
{
  const w = 3, h = 3;
  const flat = new Float32Array(w * h).fill(0.5);
  const n = E.normalRGBA(flat, w, h, 1, false);
  ok("法线：平面 = (128,128,255)", Math.abs(n[4] - 128) <= 1 && Math.abs(n[5] - 128) <= 1 && n[6] === 255, `${n[4]},${n[5]},${n[6]}`);
  const ramp = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) ramp[y * w + x] = x / (w - 1);
  const nr = E.normalRGBA(ramp, w, h, 1, false);
  const ng = E.normalRGBA(ramp, w, h, 1, true);
  ok("法线：X 方向坡度改变红通道", nr[4] !== 128);
  ok("法线：绿通道可翻转", Math.abs(nr[5] - 128) !== Math.abs(ng[5] - 128) || (nr[5] === 128 && ng[5] === 128));
}
{
  const w = 4, h = 2;
  const f = new Float32Array(w * h);
  for (let i = 0; i < f.length; i++) f[i] = i / (f.length - 1);
  const s = E.shadeRGBA(f, w, h);
  ok("着色：输出尺寸与不透明", s.length === w * h * 4 && s[3] === 255);
  const top = s[(w * (h - 1) + w - 1) * 4], bottom = s[0];
  ok("着色：高差带来明暗差别", Math.abs(top - bottom) > 0, `${bottom} → ${top}`);
}

// --- 编码：8 位 / 16 位灰度、RGB ------------------------------------------
{
  const f = new Float32Array([0, 0.5, 1, 0.25]);
  const png16 = E.encodePngGray(f, 2, 2, 16);
  const png8 = E.encodePngGray(f, 2, 2, 8);
  const ihdr = (buf) => Array.from(buf.slice(24, 29)); // 跳过签名(8)+长度(4)+类型(4)+宽(4)+高(4)
  ok("PNG8：位深 8、灰度色型", ihdr(png8)[0] === 8 && ihdr(png8)[1] === 0, ihdr(png8).join(","));
  ok("PNG16：位深 16、灰度色型", ihdr(png16)[0] === 16 && ihdr(png16)[1] === 0, ihdr(png16).join(","));
  const legacy = E.encodePng16(f, 2, 2);
  ok("PNG16：encodePngGray(16) 与 encodePng16 等长", png16.length === legacy.length, `${png16.length}/${legacy.length}`);
}
{
  const rgba = new Uint8ClampedArray([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255]);
  const png = E.encodePngRgb(rgba, 2, 2);
  ok("PNG RGB：色型 2、位深 8", png[24] === 8 && png[25] === 2, `${png[24]},${png[25]}`);
  ok("PNG RGB：签名正确", png[0] === 0x89 && png[1] === 0x50 && png[2] === 0x4e && png[3] === 0x47);
}

// --- OBJ 网格 --------------------------------------------------------------
{
  const w = 5, h = 5;
  const f = new Float32Array(w * h);
  for (let i = 0; i < f.length; i++) f[i] = i / (f.length - 1);
  const obj = E.buildObj(f, w, h, { widthMm: 100, heightMm: 100, heightScale: 10, maxSide: 5 });
  const vs = obj.split("\n").filter((l) => l.startsWith("v "));
  const fs = obj.split("\n").filter((l) => l.startsWith("f "));
  ok("OBJ：顶点数 = 网格点", vs.length === 25, vs.length);
  ok("OBJ：面数 = (n-1)^2", fs.length === 16, fs.length);
  const first = vs[0].split(" ").slice(1).map(Number);
  ok("OBJ：首顶点在原点、Z 为高度", near(first[0], 0) && near(first[2], 0) && near(first[1], 0), vs[0]);
  const last = vs[vs.length - 1].split(" ").slice(1).map(Number);
  ok("OBJ：末顶点 Z = 最高 × 缩放", near(last[1], 10), vs[vs.length - 1]);
}

// --- 台阶条几何 ------------------------------------------------------------
{
  const layers = [
    { lo: 0, hi: 0.33, height: 0.15, feather: 0 },
    { lo: 0.33, hi: 0.66, height: 0.5, feather: 0 },
    { lo: 0.66, hi: 1, height: 0.85, feather: 0 },
  ];
  const edges = E.stripEdges(layers);
  ok("台阶条：分界线含两端", edges.length === 4 && edges[0] === 0 && near(edges[3], 1), `[${edges}]`);
  ok("台阶条：内部边界取各层终点", near(edges[1], 0.33, 1e-6) && near(edges[2], 0.66, 1e-6));

  const nearEdge = E.stripHit(edges, 0.34, 0.03);
  ok("台阶条：靠近边界 → 改区间", nearEdge.kind === "edge" && nearEdge.edge === 1, JSON.stringify(nearEdge));

  const inside = E.stripHit(edges, 0.5, 0.03);
  ok("台阶条：块中间 → 改高度", inside.kind === "height" && inside.index === 1, JSON.stringify(inside));

  const left = E.stripHit(edges, 0.005, 0.02);
  ok("台阶条：最左边 → 外侧边", left.kind === "edge" && left.edge === 0, JSON.stringify(left));
}
{
  const layers = [
    { lo: 0, hi: 0.5, height: 0.2, feather: 0 },
    { lo: 0.5, hi: 1, height: 0.8, feather: 0 },
  ];
  // 边界只能在「前一层起点 + 1%」到「后一层终点 - 1%」之间移动
  ok("台阶条：边界下侧夹 1%", near(E.clampEdge(layers, 1, 0.0, 0.01), 0.01, 1e-9),
     E.clampEdge(layers, 1, 0.0, 0.01));
  ok("台阶条：边界上侧夹 1%", near(E.clampEdge(layers, 1, 1.0, 0.01), 0.99, 1e-9),
     E.clampEdge(layers, 1, 1.0, 0.01));
  // 两侧加起来比 2×minWidth 还窄时，边界原地不动（返回原值，不产生空层）
  const tight = [{ lo: 0.49, hi: 0.5, height: 0.2, feather: 0 }, { lo: 0.5, hi: 0.51, height: 0.8, feather: 0 }];
  ok("台阶条：太窄时不动", near(E.clampEdge(tight, 1, 0.2, 0.02), 0.5, 1e-9), E.clampEdge(tight, 1, 0.2, 0.02));
  ok("台阶条：外侧边不可拖", E.clampEdge(layers, 0, 0.3, 0.01) === null && E.clampEdge(layers, 2, 0.3, 0.01) === null);
  ok("台阶条：普通拖动原样返回", near(E.clampEdge(layers, 1, 0.4, 0.01), 0.4, 1e-9));
}
// --- 台阶化 × Gamma/对比：分层接管后曲线不参与（验收问题 4）----------------
{
  const src = new Float32Array([0.1, 0.35, 0.6, 0.9]);
  const layers = [
    { lo: 0, hi: 0.5, height: 0.15, feather: 0 },
    { lo: 0.5, hi: 1, height: 0.85, feather: 0 },
  ];
  const base = { inLo: 0, inHi: 1, blur: 0, invert: false, outLo: 0, outHi: 1 };
  const low = E.mapFieldBanded(src, 4, 1, Object.assign({}, base, { gamma: 0.2, contrast: 0.3 }), layers);
  const high = E.mapFieldBanded(src, 4, 1, Object.assign({}, base, { gamma: 3, contrast: 2.5 }), layers);
  ok("台阶化：Gamma/对比完全不参与",
     low.every((v, i) => Math.abs(v - high[i]) < 1e-9), `[${low}] vs [${high}]`);
  ok("台阶化：两档高度落到分层值",
     near(low[0], 0.15) && near(low[2], 0.85), `[${low[0]},${low[2]}]`);
  // 对照：不开台阶化时 Gamma 必须真的起作用，否则上面的断言等于没测
  const plainA = E.mapField(src, 4, 1, Object.assign({}, base, { gamma: 0.2, contrast: 1 }), 0);
  const plainB = E.mapField(src, 4, 1, Object.assign({}, base, { gamma: 3, contrast: 1 }), 0);
  ok("对照：非台阶化时 Gamma 生效", !near(plainA[0], plainB[0], 1e-3), `[${plainA[0]},${plainB[0]}]`);
}
// --- 台阶化 × 输入色阶 / 反相 / 输出量程 ------------------------------------
{
  const src = new Float32Array([0.3, 0.6, 0.9]);
  const layers = [{ lo: 0, hi: 0.5, height: 0.1, feather: 0 }, { lo: 0.5, hi: 1, height: 0.9, feather: 0 }];
  // 色阶 0.5–1.0 把 0.6 压到 0.2 → 落回第一档；不套色阶时 0.6 应该在第二档
  const p = { inLo: 0.5, inHi: 1.0, gamma: 2, contrast: 2, blur: 0, invert: false, outLo: 0, outHi: 1 };
  const out = E.mapFieldBanded(src, 3, 1, p, layers);
  ok("台阶化：色阶仍决定区间位置", near(out[0], 0.1) && near(out[1], 0.1) && near(out[2], 0.9), `[${out}]`);
  const raw = E.mapFieldBanded(src, 3, 1, Object.assign({}, p, { inLo: 0, inHi: 1 }), layers);
  ok("对照：不套色阶时 0.6 落在第二档", near(raw[1], 0.9), `[${raw}]`);
  const range = E.mapFieldBanded(src, 3, 1, Object.assign({}, p, { outLo: 0.1, outHi: 0.5 }), layers);
  ok("台阶化：输出量程照旧",
     near(range[0], 0.1 + 0.4 * 0.1) && near(range[2], 0.1 + 0.4 * 0.9), `[${range}]`);
  const inv = E.mapFieldBanded(src, 3, 1, Object.assign({}, p, { invert: true }), layers);
  ok("台阶化：反相交换两端", near(inv[0], 0.9) && near(inv[2], 0.1), `[${inv}]`);
}
// --- 宿主交接返回值分类（验收问题 2）--------------------------------------
{
  ok("交接：completed 记为成功", E.handoffOutcome({ status: "completed" }) === "completed");
  ok("交接：needs-confirmation 单独分类",
     E.handoffOutcome({ status: "needs-confirmation" }) === "needs-confirmation");
  ok("交接：缺省 status 视为 completed", E.handoffOutcome(undefined) === "completed"
     && E.handoffOutcome({}) === "completed");
  ok("交接：未知 status 不冒充成功", E.handoffOutcome({ status: "failed" }) === "unexpected");
}
// --- 交接按钮状态（验收问题 1：首次出图后必须可点）------------------------
{
  const off = E.handoffUiState({ connected: false, hasField: true, pending: false });
  ok("按钮：未连宿主禁用", off.disabled === true);
  const noField = E.handoffUiState({ connected: true, hasField: false, pending: false });
  ok("按钮：没有高度图禁用", noField.disabled === true);
  const ready = E.handoffUiState({ connected: true, hasField: true, pending: false });
  ok("按钮：连上且出图即可点", ready.disabled === false && ready.label === "交给 Lumina", ready.label);
  const pend = E.handoffUiState({ connected: true, hasField: true, pending: true });
  ok("按钮：待确认时提示确认替换", pend.disabled === false && pend.label === "确认替换" && pend.tone === "warn", pend.label);
}
// --- 独立导出的可用范围（验收问题 3）--------------------------------------
{
  const standalone = E.exportScope(false);
  ok("导出：独立打开时可用", standalone.available === true && standalone.formats.length === 5);
  const hosted = E.exportScope(true);
  ok("导出：宿主沙箱内收起", hosted.available === false && hosted.formats.length === 0
     && hosted.reason.indexOf("沙箱") >= 0, hosted.reason);
}
"""

HARNESS = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>engine tests</title></head>
<body><pre id="out">RUNNING</pre>
<script id="engine">{engine}</script>
<script>
(function () {{
{cases}
  const failed = results.filter((r) => !r.pass);
  const lines = results.map((r) => (r.pass ? "PASS " : "FAIL ") + r.name + (r.extra ? "  [" + r.extra + "]" : ""));
  lines.push("RESULT " + (failed.length ? "FAIL " + failed.length : "OK " + results.length));
  document.getElementById("out").textContent = lines.join("\\n");
}})();
</script>
</body></html>
"""


def find_browser() -> str:
    for candidate in BROWSERS:
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return found
    raise SystemExit("找不到 Chrome/Edge，无法运行浏览器内测试")


def main() -> int:
    source = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    match = ENGINE_RE.search(source)
    if not match:
        raise SystemExit("ui/index.html 里找不到 <script id=\"engine\">")
    engine = match.group(1)

    page = HARNESS.format(engine=engine, cases=CASES)
    workdir = ROOT / ".tmp"
    workdir.mkdir(parents=True, exist_ok=True)
    harness = workdir / "engine_tests.html"
    harness.write_text(page, encoding="utf-8")

    browser = find_browser()
    profile = workdir / "chrome-profile"
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=8000",
        "--dump-dom",
        harness.as_uri(),
    ]
    # 沙箱禁止为子进程建管道（CreatePipe → WinError 5），所以把浏览器输出写进文件再读
    dom_path = workdir / "dom.txt"
    with dom_path.open("w", encoding="utf-8", errors="replace") as sink:
        proc = subprocess.run(cmd, stdout=sink, stderr=subprocess.DEVNULL, timeout=120)
    dom = dom_path.read_text(encoding="utf-8", errors="replace")
    match_out = re.search(r"<pre id=\"out\">(.*?)</pre>", dom, re.DOTALL)
    if not match_out:
        print(dom[-2000:])
        print(f"[fail] 无法读取测试输出（浏览器退出码 {proc.returncode}）")
        return 1

    text = html.unescape(match_out.group(1))
    print(text)
    tail = [line for line in text.splitlines() if line.startswith("RESULT")]
    if not tail:
        print("[fail] 没有 RESULT 行")
        return 1
    return 0 if tail[-1].startswith("RESULT OK") else 1


if __name__ == "__main__":
    sys.exit(main())
