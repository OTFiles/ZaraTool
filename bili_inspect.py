#!/usr/bin/env python3
"""
B站账号成分探查 + 风险评分 (完整版)
使用：python bili_inspect.py -c cookies.txt -u 用户UID
Cookie 文件支持：
  - 简单 key=value（每行一个，或分号分隔的单行）
  - 浏览器导出的 Netscape 标准格式
"""

import argparse
import hashlib
import json
import math
import re
import sys
import time
import datetime
from collections import defaultdict
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlencode

import requests

# ======================== 配置 ========================
AICU_MAX_PAGES = 3
AICU_PAGE_SIZE = 100
MAX_VIDEOS_RESOLVE = 25
MAX_COMMON_FOLLOW_PAGES = 5

# ------------------------ 实体词表 ------------------------
ENTITIES = [
    {"name": "原神", "domain": "手游", "camp": "米哈游系", "kw": ["原神", "genshin", "ys", "原批", "原魔", "原黑", "米黑", "米忽悠", "派蒙", "提瓦特", "枫丹", "纳塔", "须弥", "蒙德", "璃月", "稻妻", "钟离", "雷电将军", "胡桃", "草神", "芙宁娜"]},
    {"name": "崩坏:星穹铁道", "domain": "手游", "camp": "米哈游系", "kw": ["星铁", "崩铁", "星穹铁道", "hsr", "开拓者", "丹恒", "三月七", "流萤", "黄泉", "知更鸟", "镜流"]},
    {"name": "绝区零", "domain": "手游", "camp": "米哈游系", "kw": ["绝区零", "zzz", "绳匠", "邦布", "新艾利都", "艾莲", "朱鸢"]},
    {"name": "崩坏3", "domain": "手游", "camp": "米哈游系", "kw": ["崩坏3", "崩三", "琪亚娜", "女武神"]},
    {"name": "鸣潮", "domain": "手游", "camp": "库洛系", "kw": ["鸣潮", "鸣批", "漂泊者", "今州", "库洛", "库街区", "黎那汐塔", "椿", "守岸人", "今汐", "长离", "忌炎", "吟霖"]},
    {"name": "战双帕弥什", "domain": "手游", "camp": "库洛系", "kw": ["战双", "帕弥什", "构造体"]},
    {"name": "明日方舟", "domain": "手游", "camp": "鹰角系", "kw": ["明日方舟", "方舟", "ak", "舟批", "粥批", "鹰角", "鹰币", "干员", "罗德岛", "舟游", "泰拉", "阿米娅", "德克萨斯", "能天使"]},
    {"name": "蔚蓝档案", "domain": "手游", "camp": "蔚蓝档案", "kw": ["蔚蓝档案", "碧蓝档案", "ba批", "阿罗娜", "什亭之城", "白子", "星野", "爱丽丝", "日方", "国服档案"]},
    {"name": "碧蓝航线", "domain": "手游", "camp": "蛮啾", "kw": ["碧蓝航线", "蓝航", "舰娘"]},
    {"name": "阴阳师", "domain": "手游", "camp": "网易系", "kw": ["阴阳师", "式神", "平安京"]},
    {"name": "第五人格", "domain": "手游", "camp": "网易系", "kw": ["第五人格", "第五", "监管者", "求生者"]},
    {"name": "蛋仔派对", "domain": "手游", "camp": "网易系", "kw": ["蛋仔", "蛋仔派对"]},
    {"name": "王者荣耀", "domain": "手游", "camp": "腾讯系", "kw": ["王者荣耀", "王者", "农药", "荣耀战力", "农批", "农狗", "李白", "露娜", "安琪拉"]},
    {"name": "元梦之星", "domain": "手游", "camp": "腾讯系", "kw": ["元梦", "元梦之星"]},
    {"name": "逆水寒", "domain": "手游", "camp": "网易系", "kw": ["逆水寒", "逆水寒手游"]},
    {"name": "尘白禁区", "domain": "手游", "camp": "尘白禁区", "kw": ["尘白禁区", "尘白", "西山居"]},
    {"name": "重返未来1999", "domain": "手游", "camp": "重返1999", "kw": ["重返未来1999", "重返1999", "1999手游", "深蓝互动"]},
    {"name": "无限暖暖", "domain": "手游", "camp": "无限暖暖", "kw": ["无限暖暖", "暖暖", "叠纸"]},
    # 国乙
    {"name": "恋与深空", "domain": "国乙", "camp": "恋与深空", "kw": ["恋与深空", "深空", "黎深", "沈星回", "祁煜", "秦彻"]},
    {"name": "光与夜之约", "domain": "国乙", "camp": "光与夜之约", "kw": ["光与夜", "光夜", "陆沉", "齐司礼"]},
    {"name": "未定事件簿", "domain": "国乙", "camp": "未定", "kw": ["未定事件簿", "未定", "左然", "莫弈"]},
    {"name": "世界之外", "domain": "国乙", "camp": "世界之外", "kw": ["世界之外"]},
    # 端游/竞技
    {"name": "英雄联盟", "domain": "端游竞技", "camp": "LOL", "kw": ["英雄联盟", "lol", "撸啊撸", "lpl", "lck", "s赛", "uzi", "召唤师", "峡谷", "the shy"]},
    {"name": "无畏契约", "domain": "端游竞技", "camp": "VALORANT", "kw": ["无畏契约", "瓦罗兰特", "valorant", "val", "瓦不上"]},
    {"name": "CSGO/CS2", "domain": "端游竞技", "camp": "CS", "kw": ["csgo", "cs2", "反恐精英", "起狙", "ak47"]},
    {"name": "DOTA2", "domain": "端游竞技", "camp": "DOTA", "kw": ["dota", "刀塔", "ti赛"]},
    {"name": "永劫无间", "domain": "端游竞技", "camp": "永劫", "kw": ["永劫", "永劫无间"]},
    {"name": "三角洲行动", "domain": "端游竞技", "camp": "三角洲", "kw": ["三角洲", "烽火地带"]},
    # 主机/单机
    {"name": "黑神话悟空", "domain": "主机单机", "camp": "国产3A", "kw": ["黑神话", "悟空", "黑猴"]},
    {"name": "塞尔达", "domain": "主机单机", "camp": "任天堂", "kw": ["塞尔达", "旷野之息", "王国之泪", "林克"]},
    {"name": "宝可梦", "domain": "主机单机", "camp": "任天堂", "kw": ["宝可梦", "寶可夢", "精灵球", "皮卡丘"]},
    {"name": "艾尔登法环", "domain": "主机单机", "camp": "魂系", "kw": ["艾尔登", "老头环", "法环", "褪色者"]},
    {"name": "只狼/黑魂", "domain": "主机单机", "camp": "魂系", "kw": ["只狼", "黑魂", "魂系"]},
    {"name": "我的世界", "domain": "主机单机", "camp": "MC", "kw": ["我的世界", "minecraft", "mc", "苦力怕"]},
    # 二次元
    {"name": "二次元/番剧", "domain": "二次元", "camp": "二次元", "kw": ["番剧", "追番", "声优", "手办", "cos", "鬼灭", "jojo", "无职", "光棱坦克", "里区"]},
    # VTuber
    {"name": "A-SOUL", "domain": "VTuber", "camp": "A-SOUL", "kw": ["asoul", "a-soul", "嘉然", "向晚", "贝拉", "乃琳", "珈乐", "嘉心糖", "顶碗人", "奶淇琳", "皇珈骑士", "一个魂", "枝江", "嘉晚饭"]},
    {"name": "永雏塔菲", "domain": "VTuber", "camp": "塔菲", "kw": ["塔菲", "taffy", "塔畜", "谢谢喵", "雏草姬", "塔菲喵"]},
    {"name": "東雪蓮", "domain": "VTuber", "camp": "東雪蓮", "kw": ["東雪蓮", "东雪莲", "莲宝", "雪莲", "罕见"]},
    {"name": "星瞳", "domain": "VTuber", "camp": "星瞳", "kw": ["星瞳", "瞳宝", "瞳子", "瞳星结", "t畜"]},
    {"name": "EOE", "domain": "VTuber", "camp": "EOE", "kw": ["虞莫", "柚恩", "露早", "莞儿", "米诺", "eoe"]},
    {"name": "阿梓", "domain": "VTuber", "camp": "阿梓", "kw": ["阿梓", "小孩梓", "梓宝"]},
    {"name": "其他VTB", "domain": "VTuber", "camp": "VTB", "kw": ["vtuber", "vtb", "虚拟主播", "中之人", "皮套", "套皮", "拉胯"]},
    # 时政
    {"name": "时政话题", "domain": "时政", "camp": "时政", "kw": ["美国", "俄乌", "乌克兰", "巴以", "台湾", "台独", "核污水", "公知", "小粉红", "殖", "美分", "恨国", "五毛", "境外势力", "键政", "入关", "工业党", "殖人", "战狼", "台巴子", "1450", "这个国家"]},
    # 主机平台战
    {"name": "主机平台战", "domain": "主机单机", "camp": "主机战", "kw": ["索狗", "任豚", "软狗", "索尼", "任天堂", "微软", "xbox", "ps5", "switch", "主机党", "pc党", "云玩家"]},
    # 性别对立
    {"name": "性别对立", "domain": "性别议题", "camp": "性别", "kw": ["拳师", "女拳", "男拳", "田园女权", "普信男", "蝈蝻", "蝻", "母权", "彩礼", "捞女", "凤凰男", "妈宝男", "爹味", "女权", "男权"]},
    # 明星饭圈
    {"name": "内娱饭圈", "domain": "明星饭圈", "camp": "内娱", "kw": ["爱豆", "打投", "塌房", "站姐", "应援", "控评", "数据女工", "哥哥", "时代少年团", "内娱"]},
    # 其他
    {"name": "数码科技", "domain": "科技数码", "camp": "数码", "kw": ["显卡", "cpu", "苹果", "安卓", "华为", "小米", "评测", "编程", "ai绘画", "大模型"]},
    {"name": "体育", "domain": "体育", "camp": "体育", "kw": ["足球", "篮球", "nba", "世界杯", "梅西", "c罗", "国足"]},
    {"name": "汽车", "domain": "汽车", "camp": "汽车", "kw": ["新能源", "特斯拉", "比亚迪", "油车", "电车", "小米su7"]},
]

HARD_ATTACK = ["脑残", "恶心", "垃圾", "智障", "死全家", "恶臭", "蛆", "妈死", "你妈", "傻逼", "傻b", "煞笔", "煞b", "sb", "nmsl", "cnm", "tmd", "脑瘫", "弱智", "低能", "废物", "fw", "狗东西", "狗屎", "人渣", "杂种", "畜生", "畜牲", "死妈", "死爹", "贱人", "贱货", "婊", "蠢货", "蠢猪", "猪脑子", "脑子有病", "有病吗", "神经病", "变态", "恶臭", "傻", "蠢", "屑"]
MEME_WARFARE = ["急了", "赢麻", "赢学", "睿智", "带孝子", "啊对对对", "遥遥领先", "懂王", "理中客", "典中典", "remake", "拉爆", "阴阳怪气", "阴阳人", "老阴阳", "yygq", "精神胜利", "精神股东", "输不起", "战犯", "嘴臭", "出警", "拉踩", "踩一捧一", "捧一踩一", "捧杀", "带节奏", "引战", "扣帽子", "洗地", "洗白", "双标", "控评", "轮博", "水军", "黑粉", "毒唯", "恰烂钱", "恰钱", "营销号", "yxh", "云玩家", "云评", "优越感", "优越党", "键盘侠", "键政", "杠精", "喷子", "柠檬精", "暴躁老哥", "魔怔", "魔怔人", "mzr", "钓鱼", "反串", "挂人", "网暴", "出征", "玻璃心", "巨婴", "妈宝", "舔狗", "绿茶", "圣母", "走狗", "ky", "米卫兵", "米卫军", "米孝子", "狗托", "索狗", "任豚", "软狗", "蝗虫", "难民", "慕洋", "汉奸", "恨国党", "战狼", "精日", "精美", "拳师", "爹味"]
MEME_LIGHT = ["破防", "破大防", "逆天", "小丑", "红温", "气抖冷", "懂的都懂", "谜语人"]

MEME_AMBIGUOUS = {
    "急": ["急急急", "着急", "著急", "焦急", "急忙", "急救", "急诊", "急切", "急需", "急性", "急促", "紧急", "急事", "急件", "救急", "急招", "急于", "急剧", "危急", "急速", "别急", "不急", "莫急", "急人", "急刹", "急诊", "应急", "急躁", "急功近利"],
    "典": ["经典", "古典", "词典", "字典", "典礼", "典范", "典雅", "出典", "典藏", "恩典", "典型", "典故", "庆典", "盛典", "宝典", "法典", "药典", "典当", "典籍"],
    "孝": ["孝顺", "孝敬", "孝心", "尽孝", "忠孝", "孝道", "守孝", "孝服", "不孝", "孝亲", "孝敬", "行孝"],
    "绷": ["绷带", "紧绷", "绷紧", "绷直"],
    "就这": ["就这样", "就这么", "就这些", "就这点", "就这个", "就这里", "就这儿", "就这条", "就这般", "就这方面"],
}
HARD_AMBIGUOUS = {
    "滚": ["滚动", "滚筒", "翻滚", "滚烫", "滚圆", "滚轮", "滚珠", "滚水", "下滚", "上滚", "滚球", "滚落", "滚雪球", "滚瓜烂熟", "滚滚"],
    "唐": ["唐朝", "唐代", "唐人街", "唐三藏", "唐僧", "唐突", "荒唐", "唐诗", "大唐", "唐装", "唐山", "唐宁", "姓唐", "唐纳德", "唐老鸭", "颓唐", "唐卡", "盛唐", "唐宋"],
}

TID_DOMAIN = {
    17: "单机游戏", 171: "电竞", 172: "手游", 65: "网游", 173: "桌游棋牌", 121: "GMV", 136: "音游", 4: "游戏",
    1: "动画", 24: "动画", 25: "动画", 47: "动画", 210: "动画", 86: "动画", 253: "动画", 13: "番剧", 167: "国创", 168: "国创",
    201: "科普", 124: "科普", 228: "知识", 207: "知识", 208: "知识", 36: "知识", 188: "数码", 95: "数码", 230: "科技",
    138: "搞笑", 21: "生活", 163: "生活", 174: "生活", 160: "生活", 211: "美食", 217: "动物",
    202: "资讯", 203: "资讯", 204: "资讯", 205: "资讯", 206: "资讯", 51: "资讯",
    181: "影视", 182: "影视", 183: "影视", 85: "影视", 145: "影视",
    3: "音乐", 28: "音乐", 31: "音乐", 59: "音乐", 193: "音乐",
    129: "舞蹈", 20: "舞蹈", 119: "鬼畜", 155: "时尚", 234: "运动", 223: "汽车", 245: "汽车",
}

KNOWN_ACCOUNTS = [
    {"camp": "米哈游系", "name": "原神", "uids": [401742377, 1872522256, 1593381854], "lottery": ["互动抽奖 #原神", "#米哈游#", "#miHoYo#"]},
    {"camp": "米哈游系", "name": "崩坏3", "uids": [27534330], "lottery": ["互动抽奖 #崩坏"]},
    {"camp": "米哈游系", "name": "星穹铁道", "uids": [1340190821, 508103429], "lottery": ["互动抽奖 #崩坏星穹铁道"]},
    {"camp": "米哈游系", "name": "绝区零", "uids": [1636034895], "lottery": ["互动抽奖 #绝区零"]},
    {"camp": "腾讯系", "name": "王者荣耀", "uids": [57863910, 392836434], "lottery": ["互动抽奖 #王者荣耀"]},
    {"camp": "鹰角系", "name": "明日方舟", "uids": [161775300], "lottery": ["互动抽奖 #明日方舟", "危机合约"]},
    {"camp": "库洛系", "name": "鸣潮", "uids": [1955897084], "lottery": ["互动抽奖 #鸣潮"]},
    {"camp": "库洛系", "name": "战双帕弥什", "uids": [382651856], "lottery": ["互动抽奖 #战双帕弥什"]},
    {"camp": "蔚蓝档案", "name": "蔚蓝档案", "uids": [3493265644980448], "lottery": ["互动抽奖 #蔚蓝档案"]},
    {"camp": "VALORANT", "name": "无畏契约", "uids": [2071691173], "lottery": ["互动抽奖 #无畏契约"]},
    {"camp": "LOL", "name": "英雄联盟赛事", "uids": [50329118], "lottery": ["互动抽奖 #英雄联盟"]},
    {"camp": "三角洲", "name": "三角洲行动", "uids": [3494376565115651], "lottery": ["互动抽奖 #三角洲行动"]},
    {"camp": "DOTA", "name": "DOTA2", "uids": [17561885], "lottery": ["互动抽奖 #dota2"]},
    {"camp": "CS", "name": "CS2", "uids": [474595627], "lottery": ["互动抽奖 #cs2"]},
    {"camp": "永劫", "name": "永劫无间", "uids": [349984754], "lottery": ["互动抽奖 #永劫无间"]},
    {"camp": "蛮啾", "name": "碧蓝航线", "uids": [233114659], "lottery": ["互动抽奖 #碧蓝航线"]},
    {"camp": "网易系", "name": "阴阳师", "uids": [30973654], "lottery": ["互动抽奖 #阴阳师"]},
    {"camp": "网易系", "name": "第五人格", "uids": [211005705], "lottery": ["互动抽奖 #第五人格"]},
    {"camp": "网易系", "name": "蛋仔派对", "uids": [1306451842], "lottery": ["互动抽奖 #蛋仔派对"]},
    {"camp": "网易系", "name": "逆水寒", "uids": [21619102], "lottery": ["互动抽奖 #逆水寒"]},
    {"camp": "腾讯系", "name": "元梦之星", "uids": [3494368275073228], "lottery": ["互动抽奖 #元梦之星"]},
    {"camp": "尘白禁区", "name": "尘白禁区", "uids": [1409863611], "lottery": ["互动抽奖 #尘白禁区"]},
    {"camp": "重返1999", "name": "重返未来1999", "uids": [1197454103], "lottery": ["互动抽奖 #重返未来1999"]},
    {"camp": "恋与深空", "name": "恋与深空", "uids": [699603717], "lottery": ["互动抽奖 #恋与深空"]},
    {"camp": "光与夜之约", "name": "光与夜之约", "uids": [434391603], "lottery": ["互动抽奖 #光与夜之约"]},
    {"camp": "无限暖暖", "name": "无限暖暖", "uids": [3461576715667734], "lottery": ["互动抽奖 #无限暖暖"]},
    {"camp": "A-SOUL", "name": "A-SOUL", "uids": [703007996, 547510303, 672328094, 672342685, 672353429, 672346917, 351609538]},
    {"camp": "塔菲", "name": "永雏塔菲", "uids": [1265680561]},
    {"camp": "東雪蓮", "name": "東雪蓮", "uids": [1437582453]},
    {"camp": "星瞳", "name": "星瞳", "uids": [2122506217]},
    {"camp": "EOE", "name": "EOE", "uids": [2018113152, 2079856185, 2099637441, 2079856395, 2072114791]},
    {"camp": "阿梓", "name": "阿梓", "uids": [7706705]},
]

# ======================== 工具函数 ========================
def load_cookies_from_file(path):
    """加载 Cookie 文件，兼容分号分隔和 Netscape 格式"""
    session = requests.Session()
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        f.seek(0)
        if first_line.startswith("# Netscape HTTP Cookie File"):
            cj = MozillaCookieJar(path)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
            return session

        raw = f.read()
        # 按分号或换行拆分
        pairs = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";") if ";" in line else [line]
            for part in parts:
                part = part.strip()
                if "=" in part:
                    key, value = part.split("=", 1)
                    pairs.append((key.strip(), value.strip()))
        for key, value in pairs:
            session.cookies.set(key, value)
    return session

def wbi_sign(params, img_key, sub_key):
    mixin_tab = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]
    orig = img_key + sub_key
    mixin = "".join(orig[i] for i in mixin_tab)[:32]
    params["wts"] = int(time.time())
    keys = sorted(params.keys())
    query = "&".join(f"{k}={params[k]}" for k in keys)
    params["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return params

def kw_hit(text, kw):
    """关键词匹配：英文缩写要求单词边界，中文直接包含"""
    if re.fullmatch(r"[a-z0-9+]+", kw, re.IGNORECASE):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text, re.IGNORECASE))
    return kw in text

# ======================== 分析函数 ========================
def match_entities(text):
    t = text.lower()
    hits = []
    for e in ENTITIES:
        if any(kw_hit(t, kw.lower()) for kw in e["kw"]):
            hits.append(e)
    return hits

def tone_of(raw):
    t = raw.lower()
    if not t:
        return {"hard": False, "memes": [], "light": []}
    hard = any(kw_hit(t, w) for w in HARD_ATTACK)
    if not hard:
        for term, safes in HARD_AMBIGUOUS.items():
            cleaned = t
            for s in safes:
                cleaned = cleaned.replace(s, "")
            if term in cleaned:
                hard = True
                break
    memes = [w for w in MEME_WARFARE if kw_hit(t, w)]
    for term, safes in MEME_AMBIGUOUS.items():
        cleaned = t
        for s in safes:
            cleaned = cleaned.replace(s, "")
        if term in cleaned:
            memes.append(term)
    light = [w for w in MEME_LIGHT if kw_hit(t, w)]
    return {"hard": hard, "memes": memes, "light": light}

def analyze_content(items, videos):
    entity_counts = defaultdict(float)
    entity_meta = {}
    camp_counts = defaultdict(float)
    domain_counts = defaultdict(float)
    hard_count = 0
    meme_count = 0
    light_count = 0
    off_cmt = 0.0
    n_cmt = 0
    off_live = 0.0
    n_live = 0
    matched_memes = defaultdict(int)
    evidence = []
    oid_camps = {}
    circle_counts = defaultdict(float)

    classified_video_weight = 0
    total_video_weight = 0
    for v in videos:
        w = v.get("weight", 1)
        total_video_weight += w
        hits = match_entities(v["title"])
        if hits:
            classified_video_weight += w
            camps = set()
            names = set()
            for e in hits:
                entity_counts[e["name"]] += w
                entity_meta[e["name"]] = {"domain": e["domain"], "camp": e["camp"]}
                domain_counts[e["domain"]] += w
                camps.add(e["camp"])
                names.add(e["name"])
            for c in camps:
                camp_counts[c] += w
            per_w = w / len(names)
            for nm in names:
                circle_counts[nm] += per_w
            oid_camps[v["oid"]] = camps
        else:
            dom = v.get("tname") or TID_DOMAIN.get(v.get("tid", 0), "其他")
            domain_counts[dom] += w
            circle_counts[dom] += w

    camp_stat = defaultdict(lambda: {"total": 0, "toxic": 0})
    camp_evidence = defaultdict(list)

    for it in items:
        raw = it["text"]
        tone = tone_of(raw)
        heavy = tone["hard"] or len(tone["memes"]) > 0
        light_only = not heavy and len(tone["light"]) > 0
        toxic = heavy

        if tone["hard"]:
            hard_count += 1
        if tone["memes"]:
            meme_count += len(tone["memes"])
            for w in tone["memes"]:
                matched_memes[w] += 1
        if tone["light"]:
            if light_only:
                light_count += 1
            for w in tone["light"]:
                matched_memes[w] += 1

        w2 = 1 if heavy else (0.5 if light_only else 0)
        if raw.strip():
            if it.get("live"):
                n_live += 1
                off_live += w2
            else:
                n_cmt += 1
                off_cmt += w2

        if (heavy or light_only) and len(raw.strip()) >= 2 and len(evidence) < 6:
            evidence.append(raw.strip()[:60])

        camps = set()
        for e in match_entities(raw):
            entity_counts[e["name"]] += 0.5
            entity_meta[e["name"]] = {"domain": e["domain"], "camp": e["camp"]}
            camps.add(e["camp"])
        for c in camps:
            camp_counts[c] += 0.5

        vcamps = oid_camps.get(it["oid"])
        if vcamps:
            for c in vcamps:
                camp_stat[c]["total"] += 1
                if toxic:
                    camp_stat[c]["toxic"] += 1
                    if len(camp_evidence[c]) < 3 and len(raw.strip()) >= 2:
                        camp_evidence[c].append(raw.strip()[:60])

    def attitude_of(camp):
        s = camp_stat[camp]
        if not s or s["total"] < 3:
            return {"label": "样本少", "hostile": False, "ratio": None, "total": s["total"] if s else 0}
        r = round(s["toxic"] / s["total"] * 100)
        if r >= 40:
            return {"label": "多为敌对/对线", "hostile": True, "ratio": r, "total": s["total"]}
        if r >= 18:
            return {"label": "偶有对线", "hostile": False, "mixed": True, "ratio": r, "total": s["total"]}
        return {"label": "大致友善/中性", "hostile": False, "ratio": r, "total": s["total"]}

    video_coverage = round(classified_video_weight / total_video_weight * 100) if total_video_weight else 0
    domain_slices = sorted(((k, round(v)) for k, v in domain_counts.items() if v > 0), key=lambda x: x[1], reverse=True)
    circle_slices = sorted(((k, round(v)) for k, v in circle_counts.items() if v > 0), key=lambda x: x[1], reverse=True)
    top_entities = sorted(
        [{"name": name, "count": round(count), "camp": entity_meta[name]["camp"], "domain": entity_meta[name]["domain"]} for name, count in entity_counts.items() if count > 0],
        key=lambda x: x["count"], reverse=True
    )
    camp_total = sum(camp_counts.values())
    camp_info = []
    for camp, w in sorted(camp_counts.items(), key=lambda x: x[1], reverse=True):
        camp_info.append({
            "camp": camp,
            "weight": round(w),
            "share": round(w / camp_total * 100) if camp_total else 0,
            "attitude": attitude_of(camp),
            "evidence": camp_evidence.get(camp, [])
        })
    hostile_camps = [c for c in camp_info if c["attitude"]["hostile"]]
    toxic_ratio = round((off_cmt / n_cmt) * 100) if n_cmt else 0
    live_toxic_ratio = round((off_live / n_live) * 100) if n_live else 0
    top_memes = sorted(matched_memes.items(), key=lambda x: x[1], reverse=True)[:8]

    return {
        "domainSlices": domain_slices,
        "circleSlices": circle_slices,
        "topEntities": top_entities,
        "campInfo": camp_info,
        "dominantCamp": camp_info[0]["camp"] if camp_info else None,
        "dominantShare": camp_info[0]["share"] if camp_info else 0,
        "hostileCamps": hostile_camps,
        "hardCount": hard_count,
        "memeCount": meme_count,
        "lightCount": light_count,
        "toxicRatio": toxic_ratio,
        "liveToxicRatio": live_toxic_ratio,
        "cmtSampleN": n_cmt,
        "liveSampleN": n_live,
        "topMemes": top_memes,
        "evidence": evidence,
        "totalTexts": n_cmt + n_live,
        "videoCoverage": video_coverage,
        "videoCount": len(videos),
    }

def analyze_activity(items):
    times = [it["time"] for it in items if it.get("time")]
    times.sort(reverse=True)
    if len(times) < 2:
        return {"note": "样本过少", "burst": False, "spanH": 0, "sample": len(times), "uniqueVideos": 0}
    span_h = (times[0] - times[-1]) / 3600
    recent = times[:20]
    burst = False
    for i in range(len(recent)):
        cnt = 0
        for j in range(i, len(recent)):
            if recent[i] - recent[j] <= 3600:
                cnt += 1
        if cnt >= 10:
            burst = True
            break
    unique_videos = len(set(it["oid"] for it in items if it.get("oid")))
    return {"spanH": round(span_h, 1), "sample": len(times), "burst": burst, "uniqueVideos": unique_videos}

def novice_probability(card):
    p = 0
    lvl = card["level"]
    if lvl <= 0: p += 35
    elif lvl == 1: p += 30
    elif lvl == 2: p += 22
    elif lvl == 3: p += 12
    elif lvl == 4: p += 4
    if card["fans"] < 5: p += 20
    elif card["fans"] < 50: p += 12
    elif card["fans"] < 500: p += 4
    if card["archiveCount"] == 0: p += 12
    if not card["sign"]: p += 6
    if card["fans"] < 50 and card["following"] > card["fans"] * 3 and card["following"] > 30: p += 8
    if card["official"]: p -= 30
    if card["vip"]: p -= 5
    p = max(0, min(100, p))
    band = "偏高" if p >= 60 else "中等" if p >= 30 else "偏低"
    return {"p": p, "band": band}

def compute_allegiance(follow_uids, medal_ids, dyn_text, live_upuids):
    follow_set = set(follow_uids or [])
    medal_set = set(medal_ids or [])
    live_set = set(live_upuids or [])
    out = []
    for a in KNOWN_ACCOUNTS:
        signals = []
        if any(u in follow_set for u in a["uids"]):
            signals.append("关注官方")
        if any(u in medal_set for u in a["uids"]):
            signals.append("粉丝牌")
        if a.get("lottery") and dyn_text and any(k in dyn_text for k in a["lottery"]):
            signals.append("参与官方抽奖")
        if any(u in live_set for u in a["uids"]):
            signals.append("直播互动(新)")
        if signals:
            out.append({"camp": a["camp"], "name": a["name"], "signals": signals})
    by_camp = {}
    for o in out:
        if o["camp"] not in by_camp:
            by_camp[o["camp"]] = {"camp": o["camp"], "names": [], "signals": set()}
        by_camp[o["camp"]]["names"].append(o["name"])
        by_camp[o["camp"]]["signals"].update(o["signals"])
    return [{"camp": v["camp"], "names": v["names"], "signals": list(v["signals"])} for v in by_camp.values()]

def analyze_live(live_data):
    rooms = live_data["rooms"]
    analyzed_rooms = []
    for r in rooms:
        hostile = 0
        for t in r["texts"]:
            tone = tone_of(t)
            if tone["hard"] or tone["memes"]:
                hostile += 1
        ratio = round(hostile / len(r["texts"]) * 100) if r["texts"] else 0
        camp = None
        name = None
        for a in KNOWN_ACCOUNTS:
            if r["upuid"] in a["uids"]:
                camp = a["camp"]
                name = a["name"]
                break
        analyzed_rooms.append({**r, "hostileRatio": ratio, "camp": camp, "name": name})
    agg = defaultdict(lambda: {"total": 0, "hostile": 0})
    for r in analyzed_rooms:
        if r["camp"]:
            agg[r["camp"]]["total"] += len(r["texts"])
            agg[r["camp"]]["hostile"] += round(r["hostileRatio"] / 100 * len(r["texts"]))
    live_attitude = {}
    for camp, s in agg.items():
        ratio = round(s["hostile"] / s["total"] * 100) if s["total"] else 0
        live_attitude[camp] = {"ratio": ratio, "hostile": ratio >= 40, "mixed": 18 <= ratio < 40, "total": s["total"]}
    return {"rooms": analyzed_rooms, "liveAttitude": live_attitude, "total": live_data["total"], "latestTs": live_data["latestTs"]}

def cross_check_allegiance(allegiance, content, live_attitude):
    by_camp = {ci["camp"]: ci for ci in content.get("campInfo", [])}
    checked = []
    for a in allegiance:
        att = None
        src = ""
        if a["camp"] in live_attitude and live_attitude[a["camp"]]["total"] >= 3:
            att = live_attitude[a["camp"]]
            src = "直播"
        elif a["camp"] in by_camp and by_camp[a["camp"]]["attitude"]["total"] >= 3:
            att = by_camp[a["camp"]]["attitude"]
            src = "留言"
        if att is None or att.get("ratio") is None:
            checked.append({**a, "consistency": "unknown", "note": "发言中几乎未涉及此圈，无法佐证"})
        elif att["hostile"]:
            checked.append({**a, "consistency": "conflict", "ratio": att["ratio"], "src": src, "note": f"在此圈{src}发言 {att['ratio']}% 带攻击性，与「粉」矛盾"})
        elif att.get("mixed"):
            checked.append({**a, "consistency": "weak", "ratio": att["ratio"], "src": src, "note": f"{src}态度中性偏对线 {att['ratio']}%"})
        else:
            checked.append({**a, "consistency": "consistent", "ratio": att["ratio"], "src": src, "note": f"{src}发言与粉丝身分相符"})
    conflict = [c for c in checked if c["consistency"] == "conflict"]
    suspect = None
    if conflict:
        suspect = {"level": "high", "camps": [c["camp"] for c in conflict]}
    elif checked and all(c["consistency"] == "unknown" for c in checked):
        suspect = {"level": "low"}
    return {"checked": checked, "suspect": suspect}

# ======================== 风险评分 ========================
def calc_risk_score(res):
    content = res.get("content", {})
    novice = res.get("novice", {"p": 0})
    activity = res.get("activity", {"burst": False})
    reverse = res.get("reverseSuspect")
    reverse_score = 100 if reverse and reverse.get("level") == "high" else 0
    toxic_ratio = content.get("toxicRatio", 0)
    hard_count = content.get("hardCount", 0)
    meme_count = content.get("memeCount", 0)
    total_attacks = hard_count + meme_count
    attack_score = min(100, 15 * math.log2(total_attacks + 1)) if total_attacks > 0 else 0
    novice_score = novice.get("p", 0)
    burst_score = 100 if activity.get("burst") else 0
    num_hostile = len(content.get("hostileCamps", []))
    hostile_score = 100 if num_hostile >= 3 else 60 if num_hostile == 2 else 30 if num_hostile == 1 else 0
    total = (reverse_score * 0.25 + toxic_ratio * 0.30 + attack_score * 0.15 +
             novice_score * 0.10 + burst_score * 0.10 + hostile_score * 0.10)
    return round(total, 1)

# ======================== 数据抓取 ========================
class BiliInspector:
    def __init__(self, session):
        self.session = session
        self.wbi_keys = None

    def _get(self, url, params=None):
        headers = {
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        resp = self.session.get(url, params=params, timeout=15, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def fetch_card(self, mid):
        j = self._get("https://api.bilibili.com/x/web-interface/card",
                      {"mid": mid, "photo": "false"})
        if j["code"] != 0:
            raise Exception(f"card 失败 code={j['code']}")
        c = j["data"]["card"]
        return {
            "name": c["name"],
            "face": c["face"],
            "sex": c["sex"],
            "sign": c.get("sign", ""),
            "level": c.get("level_info", {}).get("current_level", 0),
            "fans": c.get("fans", 0),
            "following": c.get("attention", c.get("friend", 0)),
            "official": (c.get("official_verify", {}).get("desc") if c.get("official_verify", {}).get("type") == 0 else "") or c.get("Official", {}).get("title", ""),
            "vip": c.get("vip", {}).get("label", {}).get("text", ""),
            "archiveCount": j["data"].get("archive_count", 0),
            "likeNum": j["data"].get("like_num", 0),
        }

    def fetch_aicu_replies(self, mid):
        texts, items, total = [], [], 0
        for pn in range(1, AICU_MAX_PAGES + 1):
            j = self._get("https://api.aicu.cc/api/v3/search/getreply",
                          {"uid": mid, "pn": pn, "ps": AICU_PAGE_SIZE, "mode": 0})
            if j["code"] != 0:
                break
            d = j.get("data", {})
            total = d.get("cursor", {}).get("all_count", total)
            for r in d.get("replies", []):
                msg = r.get("message", "")
                texts.append(msg)
                items.append({"text": msg, "time": r.get("time", 0),
                              "oid": str(r.get("dyn", {}).get("oid", ""))})
            if not d.get("replies") or d.get("cursor", {}).get("is_end"):
                break
        return total, texts, items

    def fetch_aicu_danmaku(self, mid):
        texts, items, total = [], [], 0
        for pn in range(1, AICU_MAX_PAGES + 1):
            j = self._get("https://api.aicu.cc/api/v3/search/getvideodm",
                          {"uid": mid, "pn": pn, "ps": AICU_PAGE_SIZE})
            if j["code"] != 0:
                break
            d = j.get("data", {})
            total = d.get("cursor", {}).get("all_count", total)
            for r in d.get("videodmlist", []):
                content = r.get("content", "")
                texts.append(content)
                items.append({"text": content, "time": r.get("ctime", 0),
                              "oid": str(r.get("oid", ""))})
            if not d.get("videodmlist") or d.get("cursor", {}).get("is_end"):
                break
        return total, texts, items

    def fetch_aicu_live_danmaku(self, mid):
        rooms = {}
        total, latest_ts, texts = 0, 0, []
        for pn in range(1, AICU_MAX_PAGES + 1):
            j = self._get("https://api.aicu.cc/api/v3/search/getlivedm",
                          {"uid": mid, "pn": pn, "ps": AICU_PAGE_SIZE})
            if j["code"] != 0:
                break
            d = j.get("data", {})
            total = d.get("cursor", {}).get("all_count", total)
            for room in d.get("list", []):
                ri = room.get("roominfo", {})
                key = ri.get("upuid") or ri.get("roomid") or ri.get("upname")
                if not key:
                    continue
                if key not in rooms:
                    rooms[key] = {
                        "upuid": int(ri.get("upuid", 0)),
                        "upname": ri.get("upname", ""),
                        "roomid": ri.get("roomid", ""),
                        "roomname": ri.get("roomname", ""),
                        "texts": [],
                        "count": 0
                    }
                for dm in room.get("danmu", []):
                    txt = dm.get("text", "")
                    rooms[key]["texts"].append(txt)
                    rooms[key]["count"] += 1
                    texts.append(txt)
                    if dm.get("ts", 0) > latest_ts:
                        latest_ts = dm["ts"]
            if not d.get("list") or d.get("cursor", {}).get("is_end"):
                break
        room_list = sorted(rooms.values(), key=lambda x: x["count"], reverse=True)
        return total, room_list, texts, latest_ts

    def _get_wbi_keys(self):
        if self.wbi_keys:
            return self.wbi_keys
        j = self._get("https://api.bilibili.com/x/web-interface/nav")
        img_url = j["data"]["wbi_img"]["img_url"]
        sub_url = j["data"]["wbi_img"]["sub_url"]
        img_key = img_url.split("/")[-1].split(".")[0]
        sub_key = sub_url.split("/")[-1].split(".")[0]
        self.wbi_keys = (img_key, sub_key)
        return self.wbi_keys

    def fetch_followings(self, mid):
        try:
            img_key, sub_key = self._get_wbi_keys()
            params = wbi_sign({"vmid": mid, "pn": 1, "ps": 50, "order": "desc",
                               "order_type": "attention"}, img_key, sub_key)
            j = self._get(f"https://api.bilibili.com/x/relation/followings?{urlencode(params)}")
            if j["code"] == 0:
                data = j["data"]
                return {"status": "ok", "total": data.get("total", 0),
                        "list": [u["uname"] for u in data.get("list", [])],
                        "uids": [u["mid"] for u in data.get("list", [])]}
            if j["code"] in (22115, 22007):
                return {"status": "private"}
            return {"status": "unavailable", "code": j["code"]}
        except Exception as e:
            return {"status": "unavailable", "code": str(e)}

    def fetch_medals(self, mid):
        try:
            j = self._get(f"https://api.live.bilibili.com/xlive/web-ucenter/user/MedalWall?target_id={mid}")
            if j["code"] == 0 and j["data"]:
                if j["data"].get("close_space_medal") == 1:
                    return {"status": "private", "ids": []}
                ids = [m["medal_info"]["target_id"] for m in j["data"].get("list", [])
                       if "medal_info" in m]
                return {"status": "ok", "ids": ids}
            return {"status": "unavailable", "ids": [], "code": j["code"]}
        except Exception:
            return {"status": "unavailable", "ids": []}

    def fetch_dynamics_text(self, mid):
        try:
            img_key, sub_key = self._get_wbi_keys()
            params = wbi_sign({"host_mid": mid, "timezone_offset": -480,
                               "platform": "web", "features": "itemOpusStyle"},
                              img_key, sub_key)
            j = self._get(f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?{urlencode(params)}")
            if j["code"] == 0 and j["data"] and j["data"].get("items"):
                return {"status": "ok",
                        "text": json.dumps(j["data"]["items"], ensure_ascii=False)}
            return {"status": "unavailable", "text": "", "code": j["code"]}
        except Exception:
            return {"status": "unavailable", "text": ""}

    def fetch_common_followings(self, mid):
        list_data, total, mutual = [], 0, 0
        for pn in range(1, MAX_COMMON_FOLLOW_PAGES + 1):
            try:
                j = self._get(f"https://api.bilibili.com/x/relation/same/followings?vmid={mid}&pn={pn}&ps=50")
            except Exception:
                if pn == 1:
                    return {"status": "unavailable", "list": [], "total": 0, "mutual": 0}
                break
            if not j or j["code"] != 0:
                if pn > 1:
                    break
                if j and j["code"] == -101:
                    return {"status": "nologin", "list": [], "total": 0, "mutual": 0}
                return {"status": "unavailable", "code": j["code"] if j else None,
                        "list": [], "total": 0, "mutual": 0}
            d = j.get("data", {})
            total = d.get("total", total)
            items = d.get("list", [])
            for it in items:
                is_mutual = it.get("attribute") == 6
                list_data.append({"uname": it["uname"], "mid": it["mid"], "mutual": is_mutual})
                if is_mutual:
                    mutual += 1
            if len(items) < 50:
                break
        return {"status": "ok", "total": total or len(list_data), "list": list_data,
                "mutual": mutual}

    def fetch_video_info(self, oid):
        try:
            j = self._get(f"https://api.bilibili.com/x/web-interface/view?aid={oid}")
            if j["code"] != 0:
                return None
            d = j["data"]
            return {"oid": oid, "title": d.get("title", ""),
                    "tid": d.get("tid", 0), "tname": d.get("tname", "")}
        except Exception:
            return None

    def resolve_top_videos(self, items):
        freq = defaultdict(int)
        for it in items:
            if it["oid"]:
                freq[it["oid"]] += 1
        sorted_oids = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:MAX_VIDEOS_RESOLVE]
        video_infos = []
        for oid, weight in sorted_oids:
            info = self.fetch_video_info(oid)
            if info:
                info["weight"] = weight
                video_infos.append(info)
        return video_infos

# ======================== 主流程 ========================
def inspect_user(session, mid):
    inspector = BiliInspector(session)
    card = inspector.fetch_card(mid)
    reply_total, reply_texts, reply_items = inspector.fetch_aicu_replies(mid)
    dm_total, dm_texts, dm_items = inspector.fetch_aicu_danmaku(mid)
    live_total, live_rooms, live_texts, live_latest_ts = inspector.fetch_aicu_live_danmaku(mid)
    followings = inspector.fetch_followings(mid)
    medals = inspector.fetch_medals(mid)
    dyn = inspector.fetch_dynamics_text(mid)
    common_follow = inspector.fetch_common_followings(mid)

    cmt_items = reply_items + dm_items
    live_items = [{"text": t, "time": 0, "oid": "", "live": True} for t in live_texts]
    all_items = cmt_items + live_items
    videos = inspector.resolve_top_videos(all_items)

    live_analyzed = analyze_live({"rooms": live_rooms, "total": live_total, "latestTs": live_latest_ts})
    live_upuids = [r["upuid"] for r in live_analyzed["rooms"] if r["upuid"]]

    novice = novice_probability(card)
    allegiance_raw = compute_allegiance(
        followings.get("uids", []),
        medals.get("ids", []),
        dyn.get("text", ""),
        live_upuids
    )
    content = analyze_content(all_items, videos)
    activity = analyze_activity(reply_items + dm_items)
    aleg_check = cross_check_allegiance(allegiance_raw, content, live_analyzed["liveAttitude"])

    result = {
        "mid": mid,
        "card": card,
        "novice": novice,
        "content": content,
        "activity": activity,
        "allegiance": aleg_check["checked"],
        "reverseSuspect": aleg_check["suspect"],
        "live": live_analyzed,
        "replyTotal": reply_total,
        "danmakuTotal": dm_total,
        "followings": followings,
        "medals": medals,
        "commonFollow": common_follow,
        "riskScore": None
    }
    result["riskScore"] = calc_risk_score(result)
    
    # ----- 保存原始数据到本地文件 -----
    raw_data = {
        "mid": mid,
        "card": card,
        "replies": reply_items,
        "danmaku": dm_items,
        "live_rooms": live_rooms,
        "followings": followings,
        "medals": medals,
        "dynamics": dyn,
        "common_follow": common_follow
    }
    save_history(mid, raw_data)
    # ---------------------------------
    
    return result

def save_history(mid, raw_data):
    """将原始探查数据追加写入 bilibili.history.txt"""
    try:
        with open("bilibili.history.txt", "a", encoding="utf-8") as f:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n{'='*60}\n")
            f.write(f"探查时间: {now}   UID: {mid}\n")
            f.write(f"{'='*60}\n")

            # 1. 基本资料
            card = raw_data.get("card", {})
            f.write(f"昵称: {card.get('name','')}  Lv.{card.get('level','')}\n")
            f.write(f"粉丝: {card.get('fans','')}  关注: {card.get('following','')}\n")
            f.write(f"签名: {card.get('sign','')}\n")
            if card.get('official'):
                f.write(f"认证: {card['official']}\n")
            f.write("\n")

            # 2. 评论区留言（最多50条）
            replies = raw_data.get("replies", [])
            f.write(f"[评论区留言] 共{len(replies)}条，显示前50条:\n")
            for i, r in enumerate(replies[:50]):
                text = r.get("text", "").replace("\n", " ")
                f.write(f"  {i+1}. {text}\n")
            f.write("\n")

            # 3. 视频弹幕（最多50条）
            danmaku = raw_data.get("danmaku", [])
            f.write(f"[视频弹幕] 共{len(danmaku)}条，显示前50条:\n")
            for i, d in enumerate(danmaku[:50]):
                text = d.get("text", "").replace("\n", " ")
                f.write(f"  {i+1}. {text}\n")
            f.write("\n")

            # 4. 直播弹幕（按房间，每个房间最多10条）
            live_rooms = raw_data.get("live_rooms", [])
            f.write(f"[直播弹幕] 涉及{len(live_rooms)}个直播间:\n")
            for room in live_rooms:
                f.write(f"  主播: {room.get('upname','')} (UID:{room.get('upuid','')})  弹幕数: {room.get('count','')}\n")
                for i, t in enumerate(room.get("texts", [])[:10]):
                    text = t.replace("\n", " ")
                    f.write(f"    {i+1}. {text}\n")
            f.write("\n")

            # 5. 关注列表（显示前20个）
            followings = raw_data.get("followings", {})
            f.write(f"[关注列表] 状态: {followings.get('status','')}  总数: {followings.get('total','')}\n")
            if followings.get("list"):
                f.write("  前20个关注: " + ", ".join(followings["list"][:20]) + "\n")
            f.write("\n")

            # 6. 粉丝勋章
            medals = raw_data.get("medals", {})
            f.write(f"[粉丝勋章] 状态: {medals.get('status','')}  数量: {len(medals.get('ids',[]))}\n")
            if medals.get("ids"):
                f.write(f"  IDs: {medals['ids']}\n")
            f.write("\n")

            # 7. 动态文本（前500字符）
            dynamics = raw_data.get("dynamics", {})
            dyn_text = dynamics.get("text", "")
            f.write(f"[动态原文] 状态: {dynamics.get('status','')}\n")
            if dyn_text:
                f.write(f"  内容(前500字): {dyn_text[:500]}\n")
            f.write("\n")

            # 8. 共同关注
            common = raw_data.get("common_follow", {})
            f.write(f"[共同关注] 状态: {common.get('status','')}  总数: {common.get('total','')}  互粉: {common.get('mutual','')}\n")
            if common.get("list"):
                names = [u["uname"] for u in common["list"][:15]]
                f.write("  前15个: " + ", ".join(names) + "\n")
            f.write("\n")
    except Exception as e:
        # 写入失败不影响主流程
        print(f"⚠️ 保存历史文件失败: {e}")

def print_report(res):
    c = res["card"]
    print(f"\n{'='*60}")
    print(f"UID: {res['mid']}  昵称: {c['name']}  Lv.{c['level']}")
    print(f"粉丝: {c['fans']}  关注: {c['following']}  投稿: {c['archiveCount']}")
    if c['sign']: print(f"签名: {c['sign']}")
    if c['official']: print(f"认证: {c['official']}")
    if c['vip']: print(f"会员: {c['vip']}")

    novice = res["novice"]
    print(f"\n🕵️ 疑似小号可能性: {novice['p']}% ({novice['band']})")

    content = res["content"]
    print(f"\n📊 评论区引战比例: {content['toxicRatio']}% (辱骂 {content['hardCount']}, 对线 {content['memeCount']}, 轻嘲讽 {content['lightCount']})")
    if content.get("liveSampleN"):
        print(f"   直播弹幕引战比例: {content['liveToxicRatio']}%")
    if content["topMemes"]:
        print("   高频黑话:", ", ".join(f"{w}({n})" for w, n in content["topMemes"]))

    print("\n🎯 活跃圈子与态度:")
    for ci in content.get("campInfo", [])[:5]:
        att = ci["attitude"]
        ratio_str = f" ({att['ratio']}%)" if att.get("ratio") is not None else ""
        print(f"   {ci['camp']} (关注度 {ci['share']}%) -> {att['label']}{ratio_str}")
    if content["hostileCamps"]:
        print(f"   敌对圈子: {', '.join(c['camp'] for c in content['hostileCamps'])}")

    act = res["activity"]
    print(f"\n📈 活动轨迹: 取样 {act.get('sample',0)} 条, 跨度 {act.get('spanH',0)} 小时, 爆发灌水: {'是' if act.get('burst') else '否'}")

    aleg = res["allegiance"]
    if aleg:
        print("\n✅ 认证归属:")
        for a in aleg:
            ratio_str = f" ({a['ratio']}%)" if a.get("ratio") is not None else ""
            print(f"   {a['camp']} ({', '.join(a['names'])}) {', '.join(a['signals'])} -> {a['consistency']}{ratio_str}")
    suspect = res.get("reverseSuspect")
    if suspect and suspect["level"] == "high":
        print(f"   ⚠️ 疑似反串: {', '.join(suspect['camps'])}")

    cf = res["commonFollow"]
    if cf["status"] == "ok" and cf["total"] > 0:
        print(f"\n🤝 共同关注: {cf['total']} 人 (互粉 {cf['mutual']} 人)")
        preview = ", ".join(u["uname"] for u in cf["list"][:6])
        if preview: print(f"   {preview}")
    elif cf["status"] == "nologin":
        print("\n🤝 共同关注: 需要登录态")

    fo = res["followings"]
    if fo["status"] == "ok":
        print(f"\n👥 关注列表: {fo['total']} 人, 最近: {', '.join(fo['list'][:8])}")
    elif fo["status"] == "private":
        print("\n👥 关注列表: 已隐私")

    risk = res["riskScore"]
    print(f"\n{'='*60}")
    print(f"🔴 综合风险评分: {risk} / 100")
    if risk >= 60:
        print("   判定: 高风险 (建议屏蔽)")
    else:
        print("   判定: 低风险")
    print(f"{'='*60}\n")

def main():
    parser = argparse.ArgumentParser(
        description="B站账号成分探查 + 风险评分",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cookie 文件格式示例：
  SESSDATA=abc123; bili_jct=xyz789
  或每行一个：
  SESSDATA=abc123
  bili_jct=xyz789
  也可使用浏览器导出的 Netscape 格式。
        """
    )
    parser.add_argument("-c", "--cookie", required=True, help="Cookie 文件路径")
    parser.add_argument("-u", "--uid", required=True, help="要探查的用户 UID")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出原始结果")
    args = parser.parse_args()

    session = load_cookies_from_file(args.cookie)
    try:
        res = inspect_user(session, args.uid)
    except Exception as e:
        print(f"探查失败: {e}")
        sys.exit(1)

    if args.json:
        output = {k: v for k, v in res.items()}
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(res)

if __name__ == "__main__":
    main()