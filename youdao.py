#!/usr/bin/env python3
"""
有道翻译命令行工具
用法:
    echo "Hello" | python youdao.py
    python youdao.py "要翻译的文本"
    python youdao.py -f en -t zh "Hello"
    python youdao.py           # 进入交互模式，输入 q 退出
"""

import sys
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

# ---------- ANSI 颜色代码 ----------
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def colorize(text: str, color: str) -> str:
    """给文本添加颜色，若终端不支持可跳过"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.END}"

# ---------- 翻译核心 ----------
def translate(text: str, source: str = "AUTO", target: str = "AUTO", verbose: bool = False) -> dict:
    """
    调用有道翻译接口，返回结构化结果
    返回字典:
        translation: 翻译文本
        src_lang: 检测到的源语言
        phonetic: 音标（可能为None）
        explains: 词性+释义列表（可能为空）
        examples: 例句列表（可能为空）
    """
    url = "https://smartisandict.youdao.com/translate"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN",
        "Referer": "https://smartisandict.youdao.com/translate",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://smartisandict.youdao.com",
        "Connection": "keep-alive",
    }
    data = {
        "inputtext": text,
        "type": f"{source}2{target}" if source != "AUTO" and target != "AUTO" else "AUTO"
    }
    encoded_data = urlencode(data)

    try:
        resp = requests.post(url, headers=headers, data=encoded_data, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"请求失败: {e}"}

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. 翻译结果
    result_ul = soup.find("ul", id="translateResult")
    if not result_ul:
        return {"error": "未找到翻译结果，可能接口已变更。"}
    items = [li.get_text(strip=True) for li in result_ul.find_all("li")]
    translation = "\n".join(items) if items else "翻译结果为空"

    # 2. 源语言检测
    src_lang = "未知"
    lang_span = soup.find("span", class_="src-le"
                           ) or soup.find("span", class_="lang-src")
    if lang_span:
        src_lang = lang_span.get_text(strip=True)

    # 3. 音标（如果有）
    phonetic = None
    phonetic_span = soup.find("span", class_="phonetic")
    if phonetic_span:
        phonetic = phonetic_span.get_text(strip=True)

    # 4. 词典释义（词性 + 解释）
    explains = []
    explain_div = soup.find("div", id="webTrans") or soup.find("div", class_="trans-container")
    if explain_div:
        # 常见结构：<ul class="word-exp"><li><span class="pos">词性</span><span>释义</span></li></ul>
        for li in explain_div.find_all("li"):
            pos_span = li.find("span", class_="pos")
            pos = pos_span.get_text(strip=True) if pos_span else ""
            content = " ".join(span.get_text(strip=True) for span in li.find_all("span") if span != pos_span)
            if pos or content:
                explains.append(f"{pos} {content}".strip())

    # 5. 例句（如果有）
    examples = []
    example_div = soup.find("div", id="bilingual") or soup.find("div", class_="example-sents")
    if example_div:
        for p in example_div.find_all("p"):
            src_sent = p.find("span", class_="src")
            tgt_sent = p.find("span", class_="tgt")
            if src_sent and tgt_sent:
                examples.append((src_sent.get_text(strip=True), tgt_sent.get_text(strip=True)))

    return {
        "translation": translation,
        "src_lang": src_lang,
        "phonetic": phonetic,
        "explains": explains,
        "examples": examples,
    }

# ---------- 格式化输出 ----------
def print_result(result: dict, show_detail: bool = True):
    """彩色打印翻译结果"""
    if "error" in result:
        print(colorize(f"错误: {result['error']}", Colors.FAIL))
        return

    # 语言检测
    print(colorize(f"[{result['src_lang']}] → ", Colors.OKBLUE), end="")
    print(colorize(result["translation"], Colors.BOLD))

    # 音标
    if result.get("phonetic"):
        print(colorize(f"音标: {result['phonetic']}", Colors.OKCYAN))

    # 词典释义
    if show_detail and result.get("explains"):
        print(colorize("释义:", Colors.HEADER))
        for exp in result["explains"]:
            print(f"  {exp}")

    # 例句
    if show_detail and result.get("examples"):
        print(colorize("例句:", Colors.HEADER))
        for src, tgt in result["examples"][:3]:  # 最多显示3个例句
            print(f"  {src}")
            print(colorize(f"  {tgt}", Colors.OKGREEN))
            print()

# ---------- 主程序 ----------
def main():
    parser = argparse.ArgumentParser(
        description="有道翻译命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  echo "hello world" | python youdao.py
  python youdao.py "你好世界"
  python youdao.py -f en -t zh "hello"
  python youdao.py --no-color "hello"   # 禁用彩色输出
  python youdao.py -s "Hello"           # 仅显示翻译，不显示详细释义
        """
    )
    parser.add_argument("text", nargs="*", help="要翻译的文本（可被管道输入替代）")
    parser.add_argument("-f", "--from", dest="source", default="AUTO",
                        help="源语言 (默认自动检测)")
    parser.add_argument("-t", "--to", dest="target", default="AUTO",
                        help="目标语言 (默认自动，一般为中文)")
    parser.add_argument("-s", "--simple", action="store_true",
                        help="简洁模式，不显示词典释义和例句")
    parser.add_argument("--no-color", action="store_true",
                        help="禁用彩色输出")
    args = parser.parse_args()

    # 若指定 --no-color，替换颜色函数
    global colorize
    if args.no_color:
        def colorize(text, _): return text

    # 获取输入文本：命令行参数 > 管道输入 > 交互输入
    if args.text:
        query = " ".join(args.text)
    elif not sys.stdin.isatty():
        # 管道输入
        query = sys.stdin.read().strip()
    else:
        # 交互模式
        print(colorize("有道翻译 (输入 'q' 退出)", Colors.HEADER))
        while True:
            try:
                query = input(colorize(">>> ", Colors.OKGREEN)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if query.lower() == "q":
                print("再见！")
                break
            if not query:
                continue
            result = translate(query, args.source, args.target)
            print_result(result, show_detail=not args.simple)
            print()
        return

    if not query:
        print(colorize("请输入要翻译的文本", Colors.WARNING))
        sys.exit(1)

    result = translate(query, args.source, args.target)
    print_result(result, show_detail=not args.simple)


if __name__ == "__main__":
    main()