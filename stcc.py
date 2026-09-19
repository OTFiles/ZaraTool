#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stcc.py — SillyTavern Character Card Checker

快速鉴定一个 PNG 图片是否为 SillyTavern 角色卡。
仅依赖 Python 标准库（zlib / json / base64 / struct）。

原理（与 ~/SillyTavern/src/character-card-parser.js 对齐）：
  1. 遍历 PNG chunk，提取所有 tEXt 块
  2. 查找 keyword 为 "ccv3"（V3 优先）或 "chara"（V2/V1）的块
  3. 将其 text 按 base64 解码为 UTF-8 JSON
  4. 验证 JSON 结构：含 spec/spec_version/data（V2/V3）或 name（V1）

用法：
  python stcc.py <image.png> [image2.png ...]
  python stcc.py --json <image.png>     # 机器可读输出
  python stcc.py --dump <image.png>     # 导出卡片 JSON 到 stdout
  python stcc.py --all-text <image.png> # 列出所有 tEXt 块（调试用）
  cat raw.png | python stcc.py -        # 从 stdin 读取
"""

import sys
import json
import zlib
import base64
import struct
from io import BytesIO

# PNG 文件签名
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 角色卡 tEXt 关键字（小写比较，与 ST 的 findIndex(...toLowerCase()) 一致）
CARD_KEYWORDS = ("ccv3", "chara")

# 退出码
EXIT_YES = 0     # 是角色卡
EXIT_NO = 1      # 不是角色卡
EXIT_ERROR = 2   # 文件错误（非 PNG、损坏、IO 错误）


class PngError(Exception):
    """PNG 解析错误"""


def read_png_chunks(data):
    """解析 PNG 二进制数据，按顺序 yield (chunk_type, chunk_data)。"""
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("不是 PNG 文件（签名错误）")

    pos = len(PNG_SIGNATURE)
    while pos < len(data):
        if pos + 8 > len(data):
            raise PngError("chunk 头被截断")

        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        cdata_start = pos + 8
        cdata_end = cdata_start + length

        if cdata_end + 4 > len(data):
            raise PngError("chunk 数据被截断（length=%d）" % length)

        cdata = data[cdata_start:cdata_end]

        # CRC 校验（可选，损坏的元数据块不影响鉴定主流程则跳过）
        (crc,) = struct.unpack(">I", data[cdata_end:cdata_end + 4])
        if zlib.crc32(ctype + cdata) & 0xFFFFFFFF != crc:
            # CRC 不匹配：IDAT/IEND 损坏说明文件有问题；
            # 但有些生成器写的 tEXt CRC 有误，这里只对关键块报错
            if ctype in (b"IDAT", b"IEND", b"IHDR"):
                raise PngError("%s chunk CRC 校验失败" % ctype.decode("ascii", "replace"))

        yield ctype, cdata
        pos = cdata_end + 4

        if ctype == b"IEND":
            break


def extract_text_chunks(data, include_compressed=False):
    """提取 tEXt 块，返回 [(keyword, text), ...]。

    tEXt 布局: keyword\0text（ISO 8859-1 / Latin-1 编码）。
    角色卡的 keyword 是 ASCII，payload 是 base64（也是 ASCII），
    因此用 latin-1 解码零损耗。

    include_compressed=True 时额外解析 zTXt 块（zlib 解压）。
    注：SillyTavern 官方解析器只读 tEXt，压缩块无法导入 ST，
    仅供诊断提示用。
    """
    texts = []
    for ctype, cdata in read_png_chunks(data):
        if ctype == b"tEXt":
            if b"\x00" not in cdata:
                continue  # 畸形块，跳过
            keyword, _, text = cdata.partition(b"\x00")
            texts.append((keyword.decode("latin-1"), text.decode("latin-1")))
        elif include_compressed and ctype == b"zTXt":
            if b"\x00" not in cdata:
                continue
            keyword, _, rest = cdata.partition(b"\x00")
            if len(rest) < 2:
                continue
            # rest[0] 是压缩方法（必须为 0），rest[1:] 是 zlib 数据
            try:
                text = zlib.decompress(rest[1:]).decode("latin-1")
                texts.append((keyword.decode("latin-1"), text))
            except zlib.error:
                continue
    return texts


def safe_b64decode(s):
    """宽容的 base64 解码：去除空白、补齐 padding。失败返回 None。"""
    s = "".join(s.split())
    if not s:
        return None
    try:
        # validate=False 容忍缺少 padding
        return base64.b64decode(s + "=" * (-len(s) % 4), validate=False)
    except Exception:
        return None


def validate_card_json(obj):
    """校验解码后的 JSON 是否像 SillyTavern 角色卡。

    返回 (is_card, card_spec, reasons)。
    与 ST importFromPng 的判断对齐：
      - obj.spec 存在 -> V2/V3 卡（chara_card_v2 / chara_card_v3）
      - obj.name 存在 -> V1 卡（最老格式）
    """
    reasons = []
    if not isinstance(obj, dict):
        return False, None, ["解码后的 JSON 不是对象"]

    spec = obj.get("spec")
    spec_ver = obj.get("spec_version")
    name = obj.get("name")
    data = obj.get("data")

    is_card = False
    card_spec = None

    if isinstance(spec, str) and spec:
        is_card = True
        card_spec = spec
        if spec.startswith("chara_card_v"):
            reasons.append("spec=%s" % spec)
        else:
            reasons.append("spec=%s（非标准 spec 字符串）" % spec)
        if isinstance(spec_ver, str):
            reasons.append("spec_version=%s" % spec_ver)
    elif isinstance(name, str) and name:
        # V1 卡：顶层只有 name/description 等字段
        is_card = True
        card_spec = "v1 (legacy)"
        reasons.append("存在 name=%r，无 spec 字段（V1 旧版卡）" % name)

    # 加分项：V2/V3 卡应有 data 对象
    if is_card and isinstance(data, dict):
        dname = data.get("name")
        if isinstance(dname, str) and dname:
            reasons.append("data.name=%r" % dname)
        v1_fields = [f for f in ("description", "first_mes") if isinstance(data.get(f), str) and data.get(f)]
        if v1_fields:
            reasons.append("data 含字段：%s" % ", ".join(v1_fields))
    elif is_card and not isinstance(data, dict) and spec is not None:
        reasons.append("警告：有 spec 但缺少 data 对象（可能被裁剪过）")

    return is_card, card_spec, reasons


def check_png(data):
    """鉴定 PNG 数据。

    返回 dict:
      is_card: bool
      spec: 卡类型字符串 或 None
      keyword: 命中的 tEXt keyword（ccv3/chara）
      reasons: 判定依据列表
      card_json: 解析出的卡片 JSON 对象（仅命中时）
      all_text: 所有 tEXt 关键字列表（调试）
    """
    result = {
        "is_card": False,
        "spec": None,
        "keyword": None,
        "reasons": [],
        "card_json": None,
        "all_text": [],
        "error": False,
    }

    try:
        texts = extract_text_chunks(data)
    except PngError as e:
        result["reasons"].append("PNG 解析错误：%s" % e)
        result["error"] = True
        return result

    result["all_text"] = [kw for kw, _ in texts]

    # 诊断：zTXt 压缩块中的 chara/ccv3（ST 官方解析器读不到）
    try:
        for kw, _ in extract_text_chunks(data, include_compressed=True):
            if kw.lower() in CARD_KEYWORDS and kw not in result["all_text"]:
                result["reasons"].append(
                    "警告：发现压缩 zTXt 块 %r（SillyTavern 无法导入 zTXt 卡）" % kw
                )
                break
    except PngError:
        pass

    # 候选块：ccv3 优先于 chara（与 ST read() 逻辑一致）
    candidates = []
    for kw, text in texts:
        lk = kw.lower()
        if lk in CARD_KEYWORDS:
            # ccv3 排前面
            candidates.append((0 if lk == "ccv3" else 1, lk, kw, text))
    candidates.sort(key=lambda t: t[0])

    if not candidates:
        result["reasons"].append(
            "未找到 'chara'/'ccv3' tEXt 块"
            + ("（存在 tEXt 块：%s）" % ", ".join(result["all_text"]) if result["all_text"] else "（完全没有 tEXt 块）")
        )
        return result

    last_err = None
    for _, lk, kw, text in candidates:
        raw = safe_b64decode(text)
        if raw is None:
            last_err = "块 %r：base64 解码失败" % kw
            continue
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            last_err = "块 %r：JSON 解析失败（%s）" % (kw, e)
            continue

        is_card, card_spec, reasons = validate_card_json(obj)
        if is_card:
            result["is_card"] = True
            result["spec"] = card_spec
            result["keyword"] = kw
            result["reasons"] = reasons
            result["card_json"] = obj
            return result
        # JSON 合法但结构不像角色卡
        result["reasons"].append("块 %r：JSON 合法但结构不像角色卡（%s）" % (kw, "；".join(reasons)))

    if last_err:
        result["reasons"].append(last_err)
    return result


def human_report(path, r):
    """生成人类可读报告（中文）。"""
    lines = []
    lines.append("=" * 60)
    lines.append("文件：%s" % path)
    if r.get("error"):
        lines.append("结论：错误 — %s" % "；".join(r["reasons"]))
        lines.append("=" * 60)
        return "\n".join(lines)

    verdict = "是 — SillyTavern 角色卡" if r["is_card"] else "否 — 不是角色卡"
    lines.append("结论：%s" % verdict)
    if r["is_card"]:
        lines.append("  类型：%s（tEXt 关键字 '%s'）" % (r["spec"], r["keyword"]))
        for reason in r["reasons"]:
            lines.append("  - %s" % reason)
        obj = r.get("card_json") or {}
        dname = (obj.get("data") or {}).get("name") or obj.get("name")
        if dname:
            lines.append("  角色名：%s" % dname)
    else:
        for reason in r["reasons"]:
            lines.append("  - %s" % reason)
        if r["all_text"]:
            lines.append("  （tEXt 关键字：%s）" % ", ".join(r["all_text"]))
    lines.append("=" * 60)
    return "\n".join(lines)


def json_report(path, r):
    out = {
        "file": path,
        "is_card": r["is_card"],
        "spec": r["spec"],
        "keyword": r["keyword"],
        "reasons": r["reasons"],
        "text_keywords": r["all_text"],
        "error": bool(r.get("error")),
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


def main(argv):
    args = argv[1:]
    mode_json = False
    mode_dump = False
    mode_alltext = False
    paths = []

    for a in args:
        if a in ("--json", "-j"):
            mode_json = True
        elif a in ("--dump", "-d"):
            mode_dump = True
        elif a in ("--all-text", "-t"):
            mode_alltext = True
        elif a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            paths.append(a)

    if not paths:
        print(__doc__.strip(), file=sys.stderr)
        return EXIT_ERROR

    any_card = False
    any_error = False

    for path in paths:
        # 读文件
        if path == "-":
            data = sys.stdin.buffer.read()
            display = "<stdin>"
        else:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                display = path
            except OSError as e:
                sys.stderr.write("错误：无法读取 %s：%s\n" % (path, e))
                any_error = True
                continue

        r = check_png(data)

        if mode_alltext:
            try:
                for kw, text in extract_text_chunks(data, include_compressed=True):
                    print("%-20s len=%d head=%r" % (kw, len(text), text[:60]))
            except PngError as e:
                sys.stderr.write("错误：%s\n" % e)
                any_error = True
            continue

        if mode_dump:
            if r["is_card"]:
                print(json.dumps(r["card_json"], ensure_ascii=False, indent=2))
            else:
                sys.stderr.write("错误：%s 不是角色卡：%s\n" % (display, "；".join(r["reasons"])))
                any_error = True
            continue

        if mode_json:
            print(json_report(display, r))
        else:
            print(human_report(display, r))

        if r["is_card"]:
            any_card = True
        if r.get("error"):
            any_error = True

    if any_error:
        return EXIT_ERROR
    if mode_alltext:
        # 调试模式：成功列出即退出 0（all-text 分支先于 dump 处理）
        return EXIT_YES
    return EXIT_YES if any_card else EXIT_NO


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:
        sys.exit(EXIT_ERROR)
