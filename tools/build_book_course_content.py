#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path("/var/www/kangboacademy")
FRONTEND = ROOT / "frontend"
BACKUP_ROOT = ROOT / "backups"
BOOK_COURSES = FRONTEND / "book-courses.html"

WAVE_RANGES = [
    (1, 62), (63, 92), (93, 117), (118, 147), (148, 177),
    (178, 207), (208, 238), (239, 268), (269, 298), (299, 328),
    (329, 336), (337, 363), (364, 390), (391, 418), (419, 445),
    (446, 472), (473, 500),
]

CATEGORY_INFO = {
    "period": {
        "label": "周期理论",
        "icon": "",
        "lens": "用长周期、技术扩散和债务循环解释资产价格的季节变化",
        "assets": "权益指数、产业龙头、黄金、债券和现金仓位",
        "risk": "把短周期波动误判成长周期拐点",
        "question": "当前经济到底处在康波四季的哪一个位置",
    },
    "invest": {
        "label": "投资哲学",
        "icon": "",
        "lens": "用安全边际、能力圈、复利和资本配置理解长期回报",
        "assets": "优秀企业、指数基金、现金储备和再平衡纪律",
        "risk": "把大师语录当成万能公式，忽视估值与自身约束",
        "question": "什么样的决策规则能让投资者长期不被情绪击穿",
    },
    "risk": {
        "label": "风险管理",
        "icon": "",
        "lens": "用不确定性、尾部风险、反脆弱和杠杆约束管理生存概率",
        "assets": "现金、保险、分散组合、低相关资产和危机预案",
        "risk": "只追求收益曲线漂亮，却忽略一次极端事件的破坏力",
        "question": "在最坏场景中，组合是否仍有继续行动的能力",
    },
    "money": {
        "label": "货币金融",
        "icon": "",
        "lens": "用货币制度、利率、信用创造和财政约束理解流动性",
        "assets": "美元资产、人民币资产、黄金、债券和高现金流企业",
        "risk": "只看价格涨跌，不看背后的货币条件变化",
        "question": "谁在创造信用，谁在收缩信用，真实利率正在奖励谁",
    },
    "demo": {
        "label": "人口经济",
        "icon": "",
        "lens": "用年龄结构、迁移、城市化和消费生命周期识别慢变量",
        "assets": "医疗养老、教育、消费、地产、城市圈和养老金资产",
        "risk": "忽视人口变量的滞后性，过早或过晚下注",
        "question": "未来十年哪些需求会因为人口结构而持续增加或收缩",
    },
    "tech": {
        "label": "科技创新",
        "icon": "",
        "lens": "用技术范式、平台扩张、网络效应和生产率兑现理解新产业",
        "assets": "AI、半导体、软件平台、先进制造和科技指数",
        "risk": "把技术趋势直接等同于投资收益，忽视估值和商业化节奏",
        "question": "这项技术何时从概念变成现金流，从泡沫变成基础设施",
    },
    "china": {
        "label": "中国经济",
        "icon": "",
        "lens": "用地方政府、产业政策、城市化、房地产和制造业理解中国资产",
        "assets": "A股、港股、债券、房地产链、先进制造和消费龙头",
        "risk": "用海外模型机械套用中国，忽视制度结构和政策节奏",
        "question": "中国经济的增长动能正在从哪里转向哪里",
    },
    "behavior": {
        "label": "行为金融",
        "icon": "",
        "lens": "用认知偏差、群体叙事、损失厌恶和过度自信解释市场失衡",
        "assets": "决策日志、纪律清单、逆向指标和仓位上限",
        "risk": "明白道理却无法执行，最终被账户波动驱动",
        "question": "哪些偏差正在影响你的买入、卖出和持有",
    },
    "wealth": {
        "label": "财富管理",
        "icon": "",
        "lens": "用现金流、家庭资产负债表、生命周期和传承制度管理财富",
        "assets": "应急金、指数基金、保险、养老账户、教育基金和家族治理",
        "risk": "把财富管理简化为单一收益率，忽视家庭责任与流动性",
        "question": "家庭资产是否能在收入中断和市场回撤中保持稳定",
    },
    "inequality": {
        "label": "贫富分化",
        "icon": "",
        "lens": "用资本收益率、劳动收入、制度安排和教育机会理解分配结构",
        "assets": "教育、人力资本、长期股权、公共政策和社会韧性资产",
        "risk": "只看个人努力，不看资产所有权和制度激励",
        "question": "财富差距如何改变消费、政治、税收和资产估值",
    },
    "history": {
        "label": "经济金融史",
        "icon": "",
        "lens": "用历史案例识别金融泡沫、危机、制度变迁和大国兴衰",
        "assets": "跨市场分散、危机现金、黄金、指数和长期优质资产",
        "risk": "相信这次完全不一样，忘记人性与杠杆的重复性",
        "question": "历史上相似的局面最终如何收场，赢家为何能留下",
    },
    "global": {
        "label": "全球宏观",
        "icon": "",
        "lens": "用美元周期、资本流动、央行政策和全球产业分工理解资产轮动",
        "assets": "全球股票、美元债、黄金、新兴市场和商品资产",
        "risk": "只看本国市场，忽视外部流动性和汇率压力",
        "question": "全球资本正在流向哪里，又从哪里撤离",
    },
    "future": {
        "label": "未来经济",
        "icon": "",
        "lens": "用平台、数字货币、网络协同和制度创新观察新经济形态",
        "assets": "数字基础设施、平台企业、创新基金和新型支付网络",
        "risk": "被概念吸引，却没有验证真实需求和监管边界",
        "question": "哪些未来叙事已经具备可度量的用户、收入和制度入口",
    },
    "ai": {
        "label": "AI与认知",
        "icon": "",
        "lens": "用算力、数据、模型、代理系统和人机协作理解AI扩散",
        "assets": "半导体、云平台、AI应用、自动化工具和数据资产",
        "risk": "只买热门模型公司，忽略算力成本、竞争和监管",
        "question": "AI能力提升会改变哪个行业的成本结构和利润分配",
    },
    "bio": {
        "label": "生物科技",
        "icon": "",
        "lens": "用基因、药物研发、老龄化和医疗支付体系理解生命科学",
        "assets": "创新药、医疗器械、医疗服务、长寿经济和生物科技基金",
        "risk": "把科学突破直接等同于商业成功，忽视临床和监管节点",
        "question": "哪一类医疗需求会在老龄化和技术进步中持续扩大",
    },
    "energy": {
        "label": "能源气候",
        "icon": "",
        "lens": "用能源密度、储能、电网、碳价格和资源安全理解能源转型",
        "assets": "电网、储能、核能、新能源材料、传统能源和碳资产",
        "risk": "只看装机增长，忽视消纳、成本曲线和周期性产能过剩",
        "question": "能源系统中真正的瓶颈是供给、传输、储存还是定价机制",
    },
    "geo": {
        "label": "地缘安全",
        "icon": "",
        "lens": "用大国博弈、供应链、军事技术和资源安全理解风险溢价",
        "assets": "国防科技、能源资源、黄金、全球分散和供应链龙头",
        "risk": "低估制裁、战争、供应链断裂对资产估值的冲击",
        "question": "地缘冲突会改变哪些资源、技术和市场的控制权",
    },
    "science": {
        "label": "前沿科学",
        "icon": "",
        "lens": "用物理学、复杂系统、信息论和计算范式理解长期创新源头",
        "assets": "科研平台、硬科技、材料、量子、航天和高端制造",
        "risk": "把科学想象当成短期商业机会，忽视产业化路径",
        "question": "哪些基础科学正在为下一轮产业革命提供工具箱",
    },
    "east": {
        "label": "东方智慧",
        "icon": "",
        "lens": "用战略、修身、组织治理和历史周期理解人性与秩序",
        "assets": "个人原则、组织文化、长期治理、家庭传承和战略耐心",
        "risk": "把古典智慧当成口号，无法转化为现代决策流程",
        "question": "古典思想如何帮助投资者控制欲望、等待时机并建立秩序",
    },
}

DEFAULT_CATEGORY = "invest"


@dataclass
class BookCourse:
    n: int
    title: str
    author: str
    difficulty: int
    category: str


def js_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def text_from_html(fragment: str) -> str:
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return html.unescape(re.sub(r"\s+", " ", fragment)).strip()


def normalize_title(title: str) -> str:
    title = html.unescape(title).strip()
    title = re.sub(r"\s*—\s*投资经典精读.*$", "", title)
    title = re.sub(r"\s*—\s*康波研究院.*$", "", title)
    title = title.replace("《《", "《").replace("》》", "》")
    title = re.sub(r"^《(.+?)》\s*—.*$", r"《\1》", title)
    if not title:
        return "《未命名课程》"
    if title.startswith("《"):
        return title
    return f"《{title}》"


def title_key(title: str) -> str:
    return normalize_title(title).replace("《", "").replace("》", "").replace("深度篇", "").strip()


def page_record(n: int) -> BookCourse | None:
    page = FRONTEND / f"book{n}.html"
    if not page.exists():
        return None
    raw = page.read_text(encoding="utf-8", errors="ignore")
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", raw, re.I)
    h2 = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", raw, re.I)
    title = normalize_title(text_from_html(h1.group(1)) if h1 else f"书目课程{n}")
    subtitle = text_from_html(h2.group(1)) if h2 else ""
    author = subtitle.split(" · ", 1)[0].strip() if " · " in subtitle else ""
    return BookCourse(n=n, title=title, author=author or "佚名", difficulty=3, category=DEFAULT_CATEGORY)


def parse_courses() -> list[BookCourse]:
    text = BOOK_COURSES.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(r'\{n:(?P<n>\d+),t:"(?P<t>.*?)",a:"(?P<a>.*?)",d:(?P<d>\d+),c:"(?P<c>.*?)"\}')
    by_id: dict[int, BookCourse] = {}
    expected = 1
    for match in pattern.finditer(text):
        raw_n = int(match.group("n"))
        if raw_n == expected:
            n = raw_n
        elif expected < raw_n <= 500 and raw_n - expected <= 3:
            while expected < raw_n:
                missing = page_record(expected)
                if missing:
                    by_id[expected] = missing
                expected += 1
            n = raw_n
        else:
            n = expected
        category = match.group("c")
        if category == "kk":
            category = "tech"
        if category not in CATEGORY_INFO:
            category = DEFAULT_CATEGORY
        by_id[n] = BookCourse(
            n=n,
            title=normalize_title(match.group("t")),
            author=html.unescape(match.group("a")).strip() or "佚名",
            difficulty=max(1, min(5, int(match.group("d")))),
            category=category,
        )
        expected = n + 1
    for n in range(1, 501):
        if n not in by_id:
            fallback = page_record(n)
            if fallback:
                by_id[n] = fallback
            else:
                by_id[n] = BookCourse(n=n, title=f"《书目课程{n}》", author="康波研究院", difficulty=3, category=DEFAULT_CATEGORY)
    return [by_id[n] for n in range(1, 501)]


def wave_of(n: int) -> int:
    for idx, (start, end) in enumerate(WAVE_RANGES, 1):
        if start <= n <= end:
            return idx
    return 0


def difficulty_label(difficulty: int) -> str:
    return ["入门", "基础", "进阶", "深度", "高阶"][max(1, min(5, difficulty)) - 1]


def audio_src(n: int) -> str:
    candidates = [FRONTEND / f"audio/books/lesson{n}.mp3", FRONTEND / f"audio/lesson{n}.mp3"]
    for path in candidates:
        if path.exists():
            return str(path.relative_to(FRONTEND))
    return f"audio/books/lesson{n}.mp3"


def book_purchase_card(title: str) -> str:
    safe_title = html.escape(title_key(title))
    return f"""
<div class="purchase-card">
  <h4>购买与延伸学习</h4>
  <p>如果你准备系统阅读《{safe_title}》，建议优先购买正版纸书或电子书，并把本课的练习题作为读书笔记模板。</p>
  <div class="buy-row">
    <a id="buy-jd" href="#" target="_blank" rel="nofollow">京东</a>
    <a id="buy-dd" href="#" target="_blank" rel="nofollow">当当</a>
    <a id="buy-db" href="#" target="_blank" rel="nofollow">豆瓣</a>
  </div>
</div>
<script>
(function(){{
  var t = {safe_title!r};
  var e = encodeURIComponent(t);
  document.getElementById('buy-jd').href = 'https://search.jd.com/Search?keyword=' + e + '&enc=utf-8';
  document.getElementById('buy-dd').href = 'http://search.dangdang.com/?key=' + e + '&act=input';
  document.getElementById('buy-db').href = 'https://book.douban.com/subject_search?search_text=' + e;
}})();
</script>
"""


def related_books(course: BookCourse, courses: list[BookCourse]) -> list[BookCourse]:
    same = [item for item in courses if item.category == course.category and item.n != course.n]
    same.sort(key=lambda item: (abs(item.n - course.n), item.n))
    return same[:4]


def reading_links(course: BookCourse, courses: list[BookCourse]) -> str:
    items = []
    for other in related_books(course, courses):
        items.append(f'<li><a href="book{other.n}.html">{html.escape(other.title)}</a> — {html.escape(other.author)}；与《{html.escape(title_key(course.title))}》同属{CATEGORY_INFO[course.category]["label"]}阅读线索。</li>')
    if not items:
        items.append('<li><a href="book-courses.html">返回书目课程中心</a> — 继续选择同领域课程。</li>')
    return "\n".join(items)


def concept_rows(course: BookCourse, info: dict) -> str:
    key = html.escape(title_key(course.title))
    label = info["label"]
    rows = [
        (f"{key}的核心问题", info["question"], f"先把《{key}》的问题意识写成一句话，再判断它解决的是周期、现金流还是行为问题。"),
        (f"{key}的分析镜头", info["lens"], f"阅读《{key}》时，把每个观点放回{label}的因果链，而不是只摘录结论。"),
        (f"{key}的资产映射", info["assets"], f"把《{key}》中的判断翻译成观察清单，再决定是否影响仓位、期限或风险预算。"),
        (f"{key}的风险边界", info["risk"], f"每次使用《{key}》的结论前，先写出一个可能证伪它的条件。"),
    ]
    return "\n".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>"
        for a, b, c in rows
    )


def action_rows(course: BookCourse, info: dict) -> str:
    key = html.escape(title_key(course.title))
    label = info["label"]
    rows = [
        ("阅读前", f"写下你对《{key}》主题的原始判断", f"避免读完后只记住作者观点，忘记自己最初的假设。"),
        ("阅读中", f"标记《{key}》中能解释现实市场的三条因果链", f"每条因果链都要对应一个可观察指标。"),
        ("阅读后", f"把《{key}》转化成一页{label}投资备忘录", f"备忘录只保留结论、证据、风险和行动。"),
        ("复盘时", f"检查《{key}》的结论是否改变了你的仓位上限", f"如果没有改变行动，就说明还停留在知识消费。"),
    ]
    return "\n".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>"
        for a, b, c in rows
    )


def course_content(course: BookCourse, courses: list[BookCourse]) -> str:
    info = CATEGORY_INFO[course.category]
    key = html.escape(title_key(course.title))
    title = html.escape(course.title)
    author = html.escape(course.author)
    label = html.escape(info["label"])
    lens = html.escape(info["lens"])
    assets = html.escape(info["assets"])
    risk = html.escape(info["risk"])
    question = html.escape(info["question"])
    wave = wave_of(course.n)
    variant = course.n % 5
    seasonal = ["春初", "春末", "夏初", "秋前", "冬末"][variant]
    time_frame = ["三年", "五年", "十年", "一轮康波", "一个家庭生命周期"][variant]
    return f"""
<h2>一、课程定位：为什么要精读{title}</h2>
<p>{title}是康波研究院第{course.n}门书目精读课，作者为{author}。这门课不把{title}当作孤立的读书笔记，而是把它放进{label}、康波周期和个人资产配置三条线索中理解。你读完之后需要回答的不是“这本书好不好”，而是“{title}能否改变我的判断框架、仓位纪律和长期行动”。</p>
<p>围绕{title}观察第六轮康波的{seasonal}阶段，可以看到技术扩散、债务再定价、人口结构变化和地缘安全重估正在同时发生。{title}的价值正在于提供一个稳定的观察坐标：当新闻每天改变叙事时，{title}提醒我们回到更慢、更深、更能穿越噪音的结构变量。</p>
<blockquote><p><strong>{title}的核心问题：</strong>{question}。带着这个问题阅读{title}，你会更容易把知识转化为可执行的投资判断。</p></blockquote>

<h2>二、作者与时代背景：{author}在回应什么问题</h2>
<p>理解{title}，首先要理解{author}面对的时代命题。对{title}而言，重要著作从来不是凭空出现的，它通常是在旧解释失效、新秩序尚未成形时诞生。{author}之所以值得进入书目课程，是因为这本书能帮助读者在{label}领域建立一套可复用的思维工具，而不是只提供一次性的观点。</p>
<p>{title}背后的问题意识可以拆成三层：第一，现实世界出现了难以用旧模型解释的现象；第二，作者尝试建立新的因果链；第三，读者需要把这条因果链迁移到自己的决策场景。对阅读{title}的投资者来说，第三层最重要，因为只有能迁移的知识才会改变资产配置。</p>
<p>阅读{title}时，不要急着寻找“标准答案”。更好的方法是问：{author}看重哪些变量，忽略了哪些变量，哪些判断在今天仍然成立，哪些判断需要根据2026年前后的宏观环境重新校准。这样的读法能让{title}从一本书变成一套工具。</p>

<h2>三、核心思想：从{title}提炼四个判断框架</h2>
<h3>1. 问题框架：先问对问题，再寻找答案</h3>
<p>{title}最值得训练的是问题意识。阅读{title}时，投资者常常急于寻找买点、卖点和标的，却忽略了问题本身是否清楚。围绕{title}，你需要先界定研究对象、时间尺度、关键变量和失败条件。对{title}这门课来说，问题越清楚，后面的数据和观点越不容易变成噪音。</p>
<h3>2. 因果框架：把观点写成可以检验的链条</h3>
<p>{title}提供的不是口号，而是一组因果链。以{title}所在的{label}为例，{lens}。读者应当把{title}中的判断翻译成“如果A发生，B会受到影响，C资产可能被重估”的结构。只有这样，{title}才会从阅读材料变成投资研究材料。</p>
<h3>3. 组合框架：把思想落到资产和仓位</h3>
<p>{title}对组合管理的启发，是把抽象观点转化为资产映射。围绕{title}，本课重点关注的资产包括{assets}。你不需要因为读完{title}就立刻交易，但你应该知道它会提高哪些资产的关注度，降低哪些资产的容忍度，以及哪些情形会触发再平衡。</p>
<h3>4. 风险框架：提前写出这本书可能错在哪里</h3>
<p>{title}虽然重要，但任何经典都不是免检结论。{title}同样需要被放进现实环境中检验。对{title}涉及的{label}主题而言，最容易出现的误用是{risk}。成熟的读者会一边吸收{author}的洞见，一边为{title}里的每个重要结论写出证伪条件。</p>

<h2>四、精读拆解：把{title}变成一张操作地图</h2>
<table class="data-table"><thead><tr><th>模块</th><th>阅读重点</th><th>投资转化</th></tr></thead><tbody>
{concept_rows(course, info)}
</tbody></table>
<p>这张表的作用，是防止阅读停留在摘抄层面。你可以在读{title}时同步建立四列笔记：原书观点、现实证据、资产映射、反方证据。只要坚持这种方法，{title}就会成为你的研究系统的一部分，而不是读完就遗忘的知识消费。</p>

<h2>五、康波关联：{title}如何服务第六轮长波判断</h2>
<p>康波研究关注的是五十年以上的技术、资本、制度和人性循环。{title}与康波周期的关系，不在于它是否直接谈到长波，而在于它能否帮助我们解释一个长周期问题：为什么某些资产在特定时代被高估，某些能力在特定时代变得稀缺，某些制度在特定时代需要重构。</p>
<p>把{title}放进第{wave}波书目课程的阅读位置，可以看到一条清晰线索：{label}并不是独立学科，它会和货币条件、产业革命、人口结构、国际秩序、行为偏差共同作用。透过{title}看第六轮康波，核心不是单一行业上涨，而是一组新技术和新制度重新分配现金流、风险和定价权。</p>
<p>因此，读{title}时要保持双时间尺度：短期用它识别当下的政策、产业和市场信号，长期用它建立{time_frame}以上的战略耐心。{title}提供的短期信号帮助你避免迟钝，{title}沉淀的长期框架帮助你避免冲动。</p>

<h2>六、投资者应用：从阅读到组合管理</h2>
<p>{title}对投资者的第一层启发，是建立观察清单；第二层启发，是形成决策规则；第三层启发，是改变复盘方式。围绕{title}学习时，没有清单，阅读会散；没有规则，观点会飘；没有复盘，错误会反复出现。</p>
<table class="data-table"><thead><tr><th>阶段</th><th>围绕{title}要做的事</th><th>输出物</th></tr></thead><tbody>
{action_rows(course, info)}
</tbody></table>
<p>如果你只能从{title}带走一个动作，请完成一页纸备忘录：左侧写{author}的核心判断，右侧写你自己的仓位影响。凡是读完{title}后仍不能影响观察、仓位或风险预算的观点，都暂时放入“待验证”区，而不是直接变成投资行动。</p>

<h2>七、阅读路线：如何高效读完{title}</h2>
<p>第一遍读{title}，目标是建立目录感：知道{author}从哪里开始、如何推进、最后落到什么结论。第二遍读{title}，目标是提炼因果链：每一章只保留一个最关键判断。第三遍读{title}，目标是做迁移：把书中思想应用到你熟悉的资产、行业或家庭财务问题。</p>
<p>读{title}时建议搭配三类材料：一类是宏观数据，用来检验书中框架；一类是公司或资产案例，用来观察现金流变化；一类是自己的交易和阅读记录，用来发现行为偏差。三类材料结合后，{title}才会真正进入你的长期能力圈。</p>
<p>特别提醒：{title}不是投资建议，也不是买卖清单。它更像一套认知训练器。你越能把{title}变成自己的问题、自己的证据、自己的规则，它的价值就越高。</p>

<h2>八、课后练习</h2>
<div class="exercise"><h3>练习1：一句话提炼</h3><p>用不超过80个字概括{title}解决的核心问题，并说明这个问题为什么在第六轮康波中仍然重要。</p></div>
<div class="exercise"><h3>练习2：因果链重建</h3><p>从{title}中提炼一条“变量A影响变量B，最终改变资产C估值”的因果链，并为这条因果链找三个可观察指标。</p></div>
<div class="exercise"><h3>练习3：组合映射</h3><p>假设你管理一个100万元组合，读完{title}后，你会调整哪一类资产的权重？请写出调整幅度、理由和失败条件。</p></div>
<div class="exercise"><h3>练习4：反方论证</h3><p>为{author}在{title}中的核心判断写一段反方意见。围绕{title}做反方论证，重点不是反驳作者，而是训练自己识别边界条件。</p></div>
<div class="exercise"><h3>练习5：行动清单</h3><p>把{title}转化为未来30天的一份行动清单：读什么、查什么数据、复盘哪一次投资决策、更新哪一条规则。</p></div>

<h2>九、参考答案与反馈要点</h2>
<p><strong>练习1反馈：</strong>关于{title}的好答案会同时包含“主题、变量、时间尺度”。例如围绕{title}，你需要写清楚它讨论的是{label}中的哪一类结构问题，而不是只写“这本书很重要”。</p>
<p><strong>练习2反馈：</strong>因果链必须可以观察。围绕{title}的分析，如果无法对应到利率、现金流、估值、政策、产业数据或行为指标，就还没有进入投资研究层面。</p>
<p><strong>练习3反馈：</strong>组合映射要有仓位语言。读完{title}后，如果你只是说“更看好某方向”，还不够；你需要说明是从5%到8%，还是从20%降到15%，以及为什么。</p>
<p><strong>练习4反馈：</strong>{title}的反方论证是避免确认偏差的关键。真正理解{title}的人，不会把{author}当成权威背诵，而会知道这套框架在哪些环境下可能失效。</p>
<p><strong>练习5反馈：</strong>行动清单越具体越好。建议把{title}对应的三个指标加入你的每周观察表，并在一个月后复盘这些指标是否真的帮助你提高判断质量。</p>

<h2>十、推荐阅读</h2>
<p>读完{title}后，建议继续阅读同一知识线索下的书目，形成交叉验证：</p>
<ul>
{reading_links(course, courses)}
</ul>
{book_purchase_card(course.title)}
<hr>
<p><em>康波研究院 · 书目精读课程 · 第{course.n}课 · {title} · 作者：{author} · 分类：{label} · 建议阅读时间45-60分钟</em></p>
"""


def full_page(course: BookCourse, courses: list[BookCourse]) -> str:
    title = html.escape(course.title)
    key = html.escape(title_key(course.title))
    author = html.escape(course.author)
    info = CATEGORY_INFO[course.category]
    prev_href = f"book{course.n - 1}.html" if course.n > 1 else "book-courses.html"
    prev_label = "上一课" if course.n > 1 else "书目课程中心"
    next_href = f"book{course.n + 1}.html" if course.n < 500 else "book-courses.html"
    next_label = "下一课" if course.n < 500 else "书目课程中心"
    audio = html.escape(audio_src(course.n))
    content = course_content(course, courses)
    badge_class = "badge-beginner" if course.difficulty <= 2 else ("badge-core" if course.difficulty == 3 else "badge-advanced")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — 书目精读 — 康波研究院</title>
<meta name="description" content="康波研究院书目精读第{course.n}课：{title}，作者{author}，从{html.escape(info['label'])}、康波周期和投资实践三个层面完成系统解读。">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700;900&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#07070a;--bg2:#0d0d14;--card:#15151c;--card2:#1c1c24;--card3:#1e1e27;--border:#2c2c38;--border2:#3a3a48;--text:#f5f5f7;--text2:#b5b5c2;--text3:#7a7a88;--gold:#e2b64f;--gold-light:#f0d478;--gold-dark:#b8922e;--green:#22c55e;--blue:#3b82f6;--purple:#a78bfa;--serif:'Noto Serif SC',serif;--sans:'Inter',-apple-system,sans-serif;--radius:14px;--radius-lg:20px}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.95;font-size:17px;-webkit-font-smoothing:antialiased}}
a{{color:var(--gold);text-decoration:none}}
.nav{{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(7,7,10,.88);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border-bottom:1px solid rgba(255,255,255,.06);height:60px;display:flex;align-items:center}}
.nav-inner{{max-width:960px;margin:0 auto;padding:0 28px;width:100%;display:flex;align-items:center;justify-content:space-between}}
.nav-brand{{display:flex;align-items:center;gap:8px;font-family:var(--serif);font-size:.95rem;font-weight:700;color:var(--gold)}}
.nav-info{{font-size:.78rem;color:var(--text3);background:var(--card2);padding:4px 14px;border-radius:20px}}
.progress-bar{{position:fixed;top:60px;left:0;right:0;height:3px;background:var(--border);z-index:99}}
.progress-fill{{height:100%;background:linear-gradient(90deg,var(--gold),var(--gold-light));transition:width .1s;width:0}}
.main{{max-width:800px;margin:0 auto;padding:90px 28px 60px}}
.lesson-header{{text-align:center;margin-bottom:48px}}
.lesson-phase{{display:inline-block;font-size:.7rem;font-weight:600;color:var(--gold);background:rgba(226,182,79,.08);border:1px solid rgba(226,182,79,.15);padding:5px 16px;border-radius:20px;margin-bottom:16px;letter-spacing:.08em;text-transform:uppercase}}
.lesson-header h1{{font-family:var(--serif);font-size:clamp(1.8rem,4.5vw,2.6rem);font-weight:900;line-height:1.25;margin-bottom:14px;background:linear-gradient(135deg,var(--text) 30%,var(--gold-light));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.lesson-meta{{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;color:var(--text3);font-size:.82rem}}
.lesson-meta span{{display:flex;align-items:center;gap:5px}}
.lesson-meta .badge{{padding:3px 10px;border-radius:6px;font-size:.7rem;font-weight:500}}
.lesson-meta .badge-beginner{{background:rgba(34,197,94,.1);color:#4ade80}}
.lesson-meta .badge-core{{background:rgba(59,130,246,.1);color:#60a5fa}}
.lesson-meta .badge-advanced{{background:rgba(139,92,246,.1);color:#a78bfa}}
.audio-player{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px 22px;margin:28px 0;display:flex;align-items:center;gap:14px;transition:border-color .3s}}
.audio-player:hover{{border-color:rgba(226,182,79,.2)}}
.audio-player audio{{width:100%;height:36px;filter:sepia(100%) saturate(300%) hue-rotate(350deg)}}
.audio-label{{font-size:.78rem;color:var(--text3);margin-bottom:2px}}
.audio-title-mini{{font-size:.9rem;font-weight:600;color:var(--text)}}
.content h2{{font-family:var(--serif);font-size:1.35rem;font-weight:700;color:var(--text);margin:40px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}}
.content h2::before{{content:'';width:3px;height:20px;background:var(--gold);border-radius:2px;flex-shrink:0}}
.content h3{{font-size:1.1rem;font-weight:600;color:var(--gold-light);margin:28px 0 10px}}
.content h4{{font-size:1rem;font-weight:600;color:var(--gold);margin:0 0 12px}}
.content p{{color:var(--text2);font-size:1rem;margin-bottom:12px;line-height:1.9}}
.content strong{{color:var(--text);font-weight:600}}
.content blockquote{{background:linear-gradient(135deg,rgba(226,182,79,.06),rgba(226,182,79,.02));border-left:3px solid var(--gold);padding:16px 20px;margin:20px 0;border-radius:0 10px 10px 0;color:var(--text);font-size:.95rem;line-height:1.9}}
.content ul,.content ol{{padding-left:24px;margin:12px 0;color:var(--text2)}}
.content li{{margin:8px 0}}
.content li::marker{{color:var(--gold-dark)}}
.data-table{{width:100%;border-collapse:collapse;margin:20px 0;font-size:.9rem;border-radius:10px;overflow:hidden}}
.data-table thead{{background:var(--card3)}}
.data-table th{{padding:12px 16px;text-align:left;font-weight:600;color:var(--gold);font-size:.82rem;border-bottom:1px solid var(--border)}}
.data-table td{{padding:10px 16px;border-bottom:1px solid var(--border);color:var(--text2);vertical-align:top}}
.data-table tbody tr:hover{{background:rgba(255,255,255,.02)}}
.exercise{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 18px;margin:12px 0}}
.exercise h3{{margin-top:0}}
.purchase-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:24px 28px;margin:32px 0}}
.buy-row{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}
.buy-row a{{display:inline-flex;align-items:center;background:var(--card2);color:var(--text);padding:9px 18px;border-radius:10px;font-size:.85rem;font-weight:600;border:1px solid var(--border)}}
.buy-row a:first-child{{background:#c00;color:#fff;border-color:#c00}}
.bottom-nav{{display:flex;justify-content:space-between;align-items:center;padding:40px 0;margin-top:48px;border-top:1px solid var(--border);gap:8px;flex-wrap:wrap}}
.bottom-nav a{{display:flex;align-items:center;gap:8px;padding:12px 20px;border-radius:12px;font-weight:500;transition:all .25s;font-size:.88rem}}
.bottom-nav .prev{{color:var(--text3);border:1px solid var(--border)}}
.bottom-nav .prev:hover{{border-color:var(--gold);color:var(--gold)}}
.bottom-nav .next{{background:var(--gold);color:#1a1a0a}}
.bottom-nav .next:hover{{background:var(--gold-light);transform:translateY(-1px)}}
@media(max-width:600px){{.main{{padding:80px 18px 40px}}.audio-player{{display:block}}.bottom-nav{{flex-direction:column}}.bottom-nav a{{width:100%;justify-content:center}}}}
</style>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="index.html" class="nav-brand">
      <svg width="24" height="24" viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="12" stroke="#e2b64f" stroke-width="1.5"/><path d="M6 18c2-6 4-8 8-10s6 2 8 6" stroke="#e2b64f" stroke-width="1.5" fill="none"/><circle cx="14" cy="12" r="2" fill="#e2b64f"/></svg>
      康波研究院
    </a>
    <div class="nav-info">第{course.n}课</div>
  </div>
</nav>
<div class="progress-bar"><div class="progress-fill" id="pf"></div></div>
<main class="main">
  <div class="lesson-header">
    <div class="lesson-phase">{html.escape(info['icon'])} 推荐书目精读</div>
    <h1>{title}</h1>
    <div class="lesson-meta">
      <span>作者：{author}</span>
      <span><span class="badge {badge_class}">{difficulty_label(course.difficulty)}</span></span>
      <span>分类：{html.escape(info['label'])}</span>
      <span>波次：第{wave_of(course.n)}波</span>
      <span>含练习</span>
    </div>
  </div>
  <div class="audio-player">
    <div>
      <div class="audio-label">课程音频</div>
      <div class="audio-title-mini">{key}</div>
    </div>
    <audio controls><source src="{audio}" type="audio/mpeg">您的浏览器不支持音频播放。</audio>
  </div>
  <div class="content">
{content}
  </div>
  <div class="bottom-nav">
    <a href="{prev_href}" class="prev">← {prev_label}</a>
    <a href="courses.html" style="color:var(--text3);font-size:.82rem">主干课程</a>
    <a href="books.html" style="color:var(--text3);font-size:.82rem">推荐书目</a>
    <a href="book-courses.html" style="color:var(--text3);font-size:.82rem">书目课程</a>
    <a href="{next_href}" class="next">{next_label} →</a>
  </div>
</main>
<script>
addEventListener('scroll',()=>document.getElementById('pf').style.width=(scrollY/(document.documentElement.scrollHeight-innerHeight)*100)+'%');
</script>
</body>
</html>
"""


def new_course_array(courses: list[BookCourse]) -> str:
    lines = ["var COURSES = ["]
    for course in courses:
        lines.append(
            f'  {{n:{course.n},t:"{js_escape(course.title)}",a:"{js_escape(course.author)}",d:{course.difficulty},c:"{course.category}"}},'
        )
    lines.append("];")
    return "\n".join(lines)


def new_cat_tabs() -> str:
    entries = [
        ("all", "全部"),
        ("period", "周期理论"),
        ("invest", "投资哲学"),
        ("risk", "风险管理"),
        ("money", "货币金融"),
        ("demo", "人口经济"),
        ("tech", "科技创新"),
        ("china", "中国经济"),
        ("behavior", "行为金融"),
        ("wealth", "财富管理"),
        ("inequality", "贫富分化"),
        ("history", "经济金融史"),
        ("global", "全球宏观"),
        ("future", "未来经济"),
        ("ai", " AI与认知"),
        ("bio", " 生物科技"),
        ("energy", "能源气候"),
        ("geo", "地缘安全"),
        ("science", "前沿科学"),
        ("east", "东方智慧"),
    ]
    body = ['<div class="cat-tabs" id="catTabs">']
    for idx, (key, label) in enumerate(entries):
        active = " active" if idx == 0 else ""
        body.append(f'<button class="cat-tab{active}" onclick="filterCat(\'{key}\')">{label}</button>')
    body.append("</div>")
    return "\n".join(body)


def new_wave_tabs() -> str:
    body = ['<div class="wave-tabs" id="waveTabs">', '<button class="wave-tab active" onclick="filterWave(0)">全部十七波</button>']
    for idx, (start, end) in enumerate(WAVE_RANGES, 1):
        body.append(f'<button class="wave-tab" onclick="filterWave({idx})">第{idx}波 ({start}-{end})</button>')
    body.append("</div>")
    return "\n".join(body)


def update_book_courses_page(courses: list[BookCourse], backup_dir: Path) -> None:
    text = BOOK_COURSES.read_text(encoding="utf-8", errors="ignore")
    shutil.copy2(BOOK_COURSES, backup_dir / BOOK_COURSES.name)
    text = re.sub(r"精读课程 · \d+本经典深度解读", "精读课程 · 500本经典深度解读", text)
    text = re.sub(r"\d+本经典著作的深度解读", "500本经典著作的深度解读", text)
    text = text.replace("328本，构建完整的投资知识体系", "500本，构建完整的投资知识体系")
    text = text.replace("328本经典深度解读", "500本经典深度解读")
    text = text.replace("328</div><div class=\"hero-stat-label\">精读课程", "500</div><div class=\"hero-stat-label\">精读课程")
    text = text.replace("13</div><div class=\"hero-stat-label\">知识领域", "19</div><div class=\"hero-stat-label\">知识领域")
    text = text.replace("10</div><div class=\"hero-stat-label\">波次扩展", "17</div><div class=\"hero-stat-label\">波次扩展")
    text = text.replace("分十波逐步扩展", "分十七波逐步扩展")
    text = text.replace("全部十波", "全部十七波")
    text = text.replace("336门课", "500门课")
    text = text.replace("328门课", "500门课")
    text = re.sub(r'<div class="cat-tabs" id="catTabs">[\s\S]*?</div>\s*\n\s*<div class="wave-tabs"', new_cat_tabs() + "\n\n<div class=\"wave-tabs\"", text, count=1)
    text = re.sub(r'<div class="wave-tabs" id="waveTabs">[\s\S]*?</div>\s*\n\s*<div id="courseContainer"', new_wave_tabs() + "\n\n<div id=\"courseContainer\"", text, count=1)
    text = re.sub(r"var COURSES = \[[\s\S]*?\n\];", new_course_array(courses), text, count=1)
    BOOK_COURSES.write_text(text, encoding="utf-8")


def main() -> int:
    courses = parse_courses()
    backup_dir = BACKUP_ROOT / f"book-course-content-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    changed = []
    for course in courses:
        path = FRONTEND / f"book{course.n}.html"
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
        path.write_text(full_page(course, courses), encoding="utf-8")
        changed.append(path.name)
    update_book_courses_page(courses, backup_dir)

    categories = Counter(course.category for course in courses)
    print(f"backup_dir={backup_dir}")
    print(f"changed_pages={len(changed)}")
    print("categories=" + ",".join(f"{key}:{value}" for key, value in sorted(categories.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
