#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib import request as urlrequest

import edge_tts
from bs4 import BeautifulSoup


ROOT = Path("/var/www/kangboacademy")
FRONTEND = ROOT / "frontend"
BOOK_COURSES = FRONTEND / "book-courses.html"
BACKUP_ROOT = ROOT / "backups"
CACHE_ROOT = ROOT / "data" / "generated_book_courses"

TEMPLATE_PHRASES = [
    "这门课不把",
    "当作孤立的读书笔记",
    "观察第六轮康波",
    "当新闻每天改变叙事",
    "提供一个稳定的观察坐标",
    "重要著作从来不是凭空出现",
    "旧解释失效、新秩序尚未成形",
    "原书观点、现实证据、资产映射、反方证据",
    "不是读完就遗忘的知识消费",
]

CATEGORY_LABELS = {
    "period": "周期理论",
    "invest": "投资哲学",
    "risk": "风险管理",
    "money": "货币金融",
    "demo": "人口经济",
    "tech": "科技创新",
    "china": "中国经济",
    "behavior": "行为金融",
    "wealth": "财富管理",
    "inequality": "贫富分化",
    "history": "经济金融史",
    "global": "全球宏观",
    "future": "未来经济",
    "ai": "AI与认知",
    "bio": "生物科技",
    "energy": "能源气候",
    "geo": "地缘安全",
    "science": "前沿科学",
    "east": "东方智慧",
}

WAVE_RANGES = [
    (1, 62), (63, 92), (93, 117), (118, 147), (148, 177),
    (178, 207), (208, 238), (239, 268), (269, 298), (299, 328),
    (329, 336), (337, 363), (364, 390), (391, 418), (419, 445),
    (446, 472), (473, 500),
]


@dataclass
class BookCourse:
    n: int
    title: str
    author: str
    difficulty: int
    category: str


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<script\b[\s\S]*?</script>", "", fragment, flags=re.I)
    text = re.sub(r"<style\b[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_space(html.unescape(text))


def normalize_title(value: str) -> str:
    value = clean_space(html.unescape(value))
    value = re.sub(r"\s*—\s*投资经典精读.*$", "", value)
    value = re.sub(r"\s*—\s*康波研究院.*$", "", value)
    value = value.replace("《《", "《").replace("》》", "》")
    if not value:
        return "《未命名课程》"
    return value if value.startswith("《") else f"《{value}》"


def title_key(value: str) -> str:
    return normalize_title(value).replace("《", "").replace("》", "").strip()


def wave_of(n: int) -> int:
    for i, (start, end) in enumerate(WAVE_RANGES, 1):
        if start <= n <= end:
            return i
    return 0


def parse_courses() -> list[BookCourse]:
    text = BOOK_COURSES.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(r'\{n:(?P<n>\d+),t:"(?P<t>.*?)",a:"(?P<a>.*?)",d:(?P<d>\d+),c:"(?P<c>.*?)"\}')
    courses: dict[int, BookCourse] = {}
    expected = 1
    for match in pattern.finditer(text):
        raw_n = int(match.group("n"))
        n = raw_n if raw_n == expected else expected
        category = match.group("c")
        if category == "kk":
            category = "tech"
        if category not in CATEGORY_LABELS:
            category = "invest"
        courses[n] = BookCourse(
            n=n,
            title=normalize_title(match.group("t")),
            author=html.unescape(match.group("a")).strip() or "佚名",
            difficulty=max(1, min(5, int(match.group("d")))),
            category=category,
        )
        expected = n + 1

    for n in range(1, 501):
        if n in courses:
            continue
        page = FRONTEND / f"book{n}.html"
        if page.exists():
            raw = page.read_text(encoding="utf-8", errors="ignore")
            h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", raw, re.I)
            h2 = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", raw, re.I)
            title = normalize_title(strip_tags(h1.group(1)) if h1 else f"书目课程{n}")
            subtitle = strip_tags(h2.group(1)) if h2 else ""
            author = subtitle.split(" · ", 1)[0].strip() if " · " in subtitle else "佚名"
            courses[n] = BookCourse(n, title, author, 3, "invest")
        else:
            courses[n] = BookCourse(n, f"《书目课程{n}》", "康波研究院", 3, "invest")
    return [courses[n] for n in range(1, 501)]


def related_courses(course: BookCourse, courses: list[BookCourse], limit: int = 4) -> list[BookCourse]:
    same = [item for item in courses if item.category == course.category and item.n != course.n]
    same.sort(key=lambda item: (abs(item.n - course.n), item.n))
    return same[:limit]


def parse_ids(value: str) -> list[int]:
    if not value:
        return list(range(1, 501))
    ids: list[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = [int(x) for x in chunk.split("-", 1)]
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(chunk))
    return [n for n in sorted(dict.fromkeys(ids)) if 1 <= n <= 500]


def process_environ() -> dict[str, str]:
    values = dict(os.environ)
    try:
        pid = subprocess.check_output(
            ["systemctl", "show", "kangboacademy", "-p", "MainPID", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if pid and pid != "0":
            for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
                if b"=" not in item:
                    continue
                key, value = item.split(b"=", 1)
                values.setdefault(key.decode(), value.decode(errors="ignore"))
    except Exception:
        pass
    return values


def deepseek_config() -> tuple[str, str, str]:
    env = process_environ()
    key = env.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not available")
    base_url = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = env.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    return key, base_url, model


def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int, retries: int = 3) -> str:
    key, base_url, model = deepseek_config()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.42,
        "top_p": 0.88,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urlrequest.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content.strip()
            raise RuntimeError("DeepSeek returned empty content")
        except Exception as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DeepSeek request failed: {last_error}")


def extract_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text, strict=False)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0), strict=False)
    raise ValueError("Cannot parse JSON response")


def clip_to_sentence(text: str, limit: int) -> str:
    text = clean_space(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。！？；，":
        idx = cut.rfind(mark)
        if idx >= limit * 0.65:
            return cut[: idx + 1]
    return cut.rstrip("，；、") + "。"


def normalize_audio_script(course: BookCourse, insights: dict) -> str:
    raw = clean_space(str(insights.get("audioScript") or ""))
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    key = title_key(course.title)
    central = clean_space(str(insights.get("centralQuestion") or "它如何帮助我们重新理解长期变量、风险边界和行动纪律"))
    thesis = clean_space(str(insights.get("thesis") or "把书中的思想转化为观察清单、复盘问题和更稳的决策节奏"))
    if len(raw) < 170:
        raw = (
            f"康波研究院书目精读第{course.n}课，《{key}》。"
            f"这本书的核心问题是：{clip_to_sentence(central, 58)}"
            f"学习时请抓住三个词：问题意识、因果链和风险边界。"
            f"读完后，把一个观点写进你的观察清单，再用真实数据和反方证据检验它。"
            f"这一课的目标不是记住结论，而是训练你把阅读变成可复盘的判断。"
        )
    if key not in raw:
        raw = f"康波研究院书目精读第{course.n}课，《{key}》。" + raw
    if len(raw) < 190:
        raw += "请在阅读后写下一条可观察指标、一条反方证据和一个下周可以复盘的行动。"
    if len(raw) <= 230:
        return raw
    clipped = clip_to_sentence(raw, 230)
    if len(clipped) >= 170:
        return clipped
    return raw[:229].rstrip("，；、") + "。"


def limit_title_mentions(fragment: str, key: str, keep: int = 22) -> str:
    if not key:
        return fragment
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        count += 1
        if count <= keep:
            return match.group(0)
        return "本书" if count % 2 else "这一框架"

    return re.sub(re.escape(key), repl, fragment)


def generation_prompts(course: BookCourse, courses: list[BookCourse], previous_error: str = "") -> tuple[str, str]:
    related = related_courses(course, courses)
    related_payload = [
        {"id": item.n, "title": item.title, "author": item.author, "category": CATEGORY_LABELS.get(item.category, item.category)}
        for item in related
    ]
    system_prompt = (
        "你是康波研究院的高级课程主笔，擅长把经济、投资、科技、历史和社会科学经典写成适合中文读者的课程。"
        "你的写作目标是原创课程讲义，不复制原书，不编造原书原文引语，不承诺收益，不给具体买卖指令。"
        "必须输出严格 JSON，键名和值都使用双引号，不要 Markdown，不要代码围栏。"
    )
    user_payload = {
        "task": "为一门书目精读课生成书籍洞察地图和课程导览音频稿",
        "course": {
            "id": course.n,
            "title": course.title,
            "author": course.author,
            "category": CATEGORY_LABELS.get(course.category, course.category),
            "difficulty": course.difficulty,
            "wave": wave_of(course.n),
        },
        "relatedCourses": related_payload,
        "insightRules": [
            "不要输出长篇 HTML。只输出结构化 JSON，程序会把洞察地图渲染成课程正文。",
            "所有内容必须围绕这本书的公开常识、核心主题、典型论点或方法论来写。",
            "不要编造章节名、页码、原文引语或具体数据。无法确定时用“本课采用公开常识层面的课程化解读”。",
            "不要使用这些旧模板短语：" + "、".join(TEMPLATE_PHRASES),
            "centralQuestion、thesis、context 必须明显区别于其他书，不能是通用投资鸡汤。",
            "coreIdeas 给 4 个，每个 explanation/application/caution 都要具体。",
            "kangboLinks 给 3 个，说明本书怎样帮助观察长周期、技术、债务、人口、制度或行为变量。",
            "portfolioActions 给 4 个，写成观察清单、仓位纪律、期限选择或风险预算，不给直接买卖指令。",
            "riskBoundaries 给 4 个，强调这本书可能被误用的条件。",
            "exercises 给 4 个，每个包含 title、prompt、scoring。",
        ],
        "audioRules": [
            "audioScript 写 150 到 220 个中文字符，适合慢速朗读 30 到 45 秒。",
            "音频稿必须具体提到这本书的核心问题或关键概念，不能写成通用导览。",
            "音频稿不要出现括号、项目符号、HTML 或舞台说明。",
        ],
        "jsonSchema": {
            "centralQuestion": "本书最值得带入课程的核心问题，40-70字",
            "thesis": "本课主论点，60-90字",
            "context": ["作者或时代问题意识1", "问题意识2", "问题意识3"],
            "coreIdeas": [
                {"name": "思想名称", "explanation": "解释", "application": "投资或认知应用", "caution": "误用提醒"}
            ],
            "kangboLinks": ["长周期关联1", "长周期关联2", "长周期关联3"],
            "portfolioActions": ["可执行观察或复盘动作1", "动作2", "动作3", "动作4"],
            "riskBoundaries": ["边界1", "边界2", "边界3", "边界4"],
            "readingPath": ["第一遍怎么读", "第二遍怎么读", "如何做笔记", "如何复盘"],
            "exercises": [
                {"title": "练习标题", "prompt": "任务", "scoring": "评分反馈要点"}
            ],
            "audioScript": "一段自然口播稿",
            "qualityNotes": ["本课最重要的三个改写抓手"],
        },
        "previousError": previous_error,
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False)


def list_values(data: dict, key: str, minimum: int, fallback: list[str]) -> list[str]:
    values = data.get(key)
    if not isinstance(values, list):
        values = []
    cleaned = [clean_space(str(item)) for item in values if clean_space(str(item))]
    while len(cleaned) < minimum:
        cleaned.append(fallback[len(cleaned) % len(fallback)])
    return cleaned


def dict_list_values(data: dict, key: str, minimum: int, fallback: list[dict]) -> list[dict]:
    values = data.get(key)
    if not isinstance(values, list):
        values = []
    cleaned: list[dict] = []
    for item in values:
        if isinstance(item, dict):
            cleaned.append({str(k): clean_space(str(v)) for k, v in item.items()})
    while len(cleaned) < minimum:
        cleaned.append(fallback[len(cleaned) % len(fallback)])
    return cleaned


def render_content_from_insights(course: BookCourse, courses: list[BookCourse], insights: dict) -> str:
    key = title_key(course.title)
    title = html.escape(course.title)
    author = html.escape(course.author)
    label = html.escape(CATEGORY_LABELS.get(course.category, course.category))
    central = clean_space(str(insights.get("centralQuestion") or f"本书帮助读者重新理解{label}中的关键变量如何影响长期决策。"))
    thesis = clean_space(str(insights.get("thesis") or f"本课把《{key}》转化为一套可复盘的观察框架，用来校准周期判断、风险边界和行动节奏。"))
    context = list_values(
        insights,
        "context",
        3,
        [
            f"{course.author}关注的不是单点预测，而是变量之间如何互相牵引。",
            f"本课采用公开常识层面的课程化解读，把书中思想放回{label}的决策场景。",
            "读者需要区分作者的核心洞见、时代限制和今天仍可迁移的方法。",
        ],
    )
    core_ideas = dict_list_values(
        insights,
        "coreIdeas",
        4,
        [
            {"name": "问题重构", "explanation": central, "application": "先把判断写成问题清单，再寻找证据。", "caution": "不要把结论当作可直接交易的指令。"},
            {"name": "因果链", "explanation": thesis, "application": "把观点拆成变量、传导机制和可观察指标。", "caution": "如果指标不可观察，就暂时不要进入仓位。"},
            {"name": "时间尺度", "explanation": "经典著作通常训练的是跨周期的判断。", "application": "区分短期噪音、中期趋势和长期结构。", "caution": "不要用长期逻辑解释所有短期价格。"},
            {"name": "风险边界", "explanation": "任何框架都需要写出失效条件。", "application": "为每个判断配置反方证据。", "caution": "框架越有解释力，越要防止确认偏差。"},
        ],
    )[:4]
    kangbo = list_values(
        insights,
        "kangboLinks",
        3,
        [
            f"本书可以帮助观察{label}如何在长周期中改变资产定价。",
            "它提醒读者把技术、债务、人口、制度和行为放在同一张图里。",
            "长周期不是单一预测，而是对多组慢变量的持续校准。",
        ],
    )
    actions = list_values(
        insights,
        "portfolioActions",
        4,
        [
            "把书中关键变量加入每周观察表。",
            "为相关资产设置仓位上限和再平衡条件。",
            "记录哪些证据会让自己降低原有判断的置信度。",
            "用一次真实决策复盘检验框架是否有效。",
        ],
    )
    risks = list_values(
        insights,
        "riskBoundaries",
        4,
        [
            "把作者观点直接当作交易信号。",
            "忽略时代背景和制度环境的差异。",
            "只吸收支持自己立场的证据。",
            "没有用仓位和现金流约束控制错误成本。",
        ],
    )
    reading_path = list_values(
        insights,
        "readingPath",
        4,
        [
            "第一遍只建立目录感和问题意识。",
            "第二遍提炼每章最重要的因果链。",
            "第三遍把观点迁移到自己的资产、职业或家庭财务场景。",
            "一个月后用数据和真实决策做复盘。",
        ],
    )
    exercises = dict_list_values(
        insights,
        "exercises",
        4,
        [
            {"title": "一句话问题", "prompt": f"用 80 字以内写出《{key}》最重要的问题意识。", "scoring": "好答案必须包含对象、变量和时间尺度。"},
            {"title": "因果链重建", "prompt": "写出一条变量 A 影响变量 B、最终改变资产或行为 C 的链条。", "scoring": "链条必须可以用公开数据或个人记录检验。"},
            {"title": "风险边界", "prompt": "列出三个会让本书框架失效的条件。", "scoring": "边界越具体，越能防止确认偏差。"},
            {"title": "行动清单", "prompt": "把本课转成未来 30 天的一个观察动作。", "scoring": "动作需要有频率、指标和复盘时间。"},
        ],
    )[:4]

    core_blocks = []
    for idx, idea in enumerate(core_ideas, 1):
        name = html.escape(idea.get("name") or f"核心思想{idx}")
        explanation = html.escape(idea.get("explanation") or "")
        application = html.escape(idea.get("application") or "")
        caution = html.escape(idea.get("caution") or "")
        core_blocks.append(
            f"<h3>{idx}. {name}</h3>\n"
            f"<p>{explanation} 这一点决定了读者不能只停在摘录层面，而要追问它解释了什么、遗漏了什么、在今天还能否成立。</p>\n"
            f"<p>放到康波研究院的学习框架里，它的应用方式是：{application} 这一步越具体，课程就越能从知识消费变成可执行的判断训练。</p>\n"
            f"<p>同时要记住边界：{caution} 任何经典一旦被当成免检结论，都会从工具变成偏见。</p>"
        )

    action_rows = "\n".join(
        f"<tr><td>动作{idx}</td><td>{html.escape(action)}</td><td>写入观察表，并在周复盘中标记证据变化。</td></tr>"
        for idx, action in enumerate(actions, 1)
    )
    risk_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in risks)
    path_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in reading_path)
    exercise_blocks = "\n".join(
        f'<div class="exercise"><h3>练习{idx}：{html.escape(item.get("title") or "课程练习")}</h3>'
        f'<p>{html.escape(item.get("prompt") or "")}</p>'
        f'<p><strong>评分反馈：</strong>{html.escape(item.get("scoring") or "")}</p></div>'
        for idx, item in enumerate(exercises, 1)
    )
    feedback_items = "\n".join(
        f"<li><strong>{html.escape(item.get('title') or f'练习{idx}')}：</strong>{html.escape(item.get('scoring') or '')}</li>"
        for idx, item in enumerate(exercises, 1)
    )

    content = f"""
<h2>一、课程入口：为什么今天还要读{title}</h2>
<p>{title}是康波研究院第{course.n}门推荐书目精读课，作者是{author}。本课的核心问题是：{html.escape(central)}</p>
<p>{html.escape(thesis)} 对投资者而言，真正重要的不是把书背熟，而是把它变成能检查假设、管理情绪和约束风险的学习工具。</p>
<blockquote><p><strong>本课主线：</strong>先理解作者的问题意识，再提炼可迁移框架，最后把框架放进资产配置、长期周期和个人行动中检验。</p></blockquote>

<h2>二、作者的问题意识：这本书在回应什么</h2>
<p>{html.escape(context[0])}</p>
<p>{html.escape(context[1])}</p>
<p>{html.escape(context[2])}</p>
<p>阅读这类经典时，最容易犯的错误是急着寻找结论。更有效的读法，是先问作者为什么要提出这个问题、他选择了哪些变量、他没有讨论哪些限制条件。这样读，书就不是观点集合，而是一套训练判断力的模型。</p>

<h2>三、核心思想：把本书拆成四个可复用框架</h2>
{chr(10).join(core_blocks)}

<h2>四、康波关联：放进长周期之后看见什么</h2>
<p>{html.escape(kangbo[0])}</p>
<p>{html.escape(kangbo[1])}</p>
<p>{html.escape(kangbo[2])}</p>
<p>康波视角不要求读者预测每一个拐点，而是要求读者持续识别慢变量：技术扩散是否进入生产率阶段，债务成本是否改变资产估值，人口结构是否重塑需求，制度调整是否改变风险溢价。读完本书后，你应该能把这些慢变量写进自己的观察清单。</p>

<h2>五、资产配置翻译：从观点到行动</h2>
<p>课程的关键不是让读者立刻交易，而是把抽象思想翻译成更清晰的观察动作。每一个动作都必须有证据来源、复盘频率和失败条件。</p>
<table class="data-table"><thead><tr><th>模块</th><th>行动要求</th><th>复盘方法</th></tr></thead><tbody>
{action_rows}
</tbody></table>
<p>如果一个观点不能改变你的观察表、仓位上限、现金流安排或风险预算，它就还停留在阅读层面。真正的学习，是让观点进入决策流程，但又不让观点越过风险纪律。</p>

<h2>六、风险边界：本书可能被误用在哪里</h2>
<p>经典著作的危险在于，它们常常太有解释力，容易让读者忽略反方证据。学习本课时，请先写下以下四类边界：</p>
<ul>
{risk_items}
</ul>
<p>边界不是为了否定作者，而是为了保护读者。只有知道框架在哪里可能失效，才能在真实世界里使用它。</p>

<h2>七、现实观察：把框架放进当下环境</h2>
<p>把本书放到 2026 年前后的环境中，最值得训练的是“慢变量意识”。市场每天都在变化，但真正影响长期结果的，往往是生产率、利率、人口、制度、组织能力和人性的共同作用。课程要求读者把这些变量拆开，而不是用单一叙事解释一切。</p>
<p>你可以选择一个熟悉场景来做迁移：一家公司如何获得现金流，一类资产为什么被重新定价，一个家庭为什么需要改变资产负债表，或者一个行业为什么会从高增长转向高竞争。只要能把书中的概念放进这些场景，就说明它已经开始进入你的判断系统。</p>
<p>这一节的输出不是“看多”或“看空”，而是一张证据表。证据表至少包含三列：支持本书框架的事实、挑战本书框架的事实、你需要继续观察的信号。只有三列同时存在，学习才不会变成确认偏差。</p>

<h2>八、阅读路线：三遍读法和一页纸输出</h2>
<ol>
{path_items}
</ol>
<p>一页纸输出建议分成四栏：核心问题、关键变量、现实证据、行动影响。四栏都写清楚，说明你已经把书中的知识变成了自己的判断工具；只写感想，说明学习还没有进入复盘层。</p>

<h2>九、互动练习</h2>
{exercise_blocks}

<h2>十、评分反馈与每日精进</h2>
<p>完成练习后，请先自评，再写一段 100 到 200 字反思。自评不是为了追求满分，而是为了发现自己在哪一步从证据跳到了结论。</p>
<ul>
{feedback_items}
</ul>
<p>如果你的答案能同时写出“我原来怎么想、这本书改变了什么、我接下来观察什么、什么证据会让我修正”，就可以记录到每日精进，并给自己一次“框架迁移”徽章进度。</p>

<h2>十一、反思模板：把阅读变成自己的系统</h2>
<p>课后反思建议从三个问题开始。第一，我原来对这个主题的默认判断是什么；第二，本书让我看见了哪个被忽略的变量；第三，我接下来准备用什么证据检验这个变量。三个问题都回答，才算完成从阅读到研究的转换。</p>
<p>如果你已经有投资、职业或家庭财务决策记录，可以选一次真实决策做复盘。复盘时不要只问结果对不对，而要问当时的信息是否充分、假设是否写清、风险是否可承受、是否提前设置了修正条件。</p>
<p>每日精进记录可以写得很短：今天更新了一个概念、一个指标、一个风险边界和一个行动。长期坚持后，你会形成自己的知识索引，而不是依赖临时情绪和市场噪音做判断。</p>

<h2>十二、笔记示范：把一条观点写完整</h2>
<p>一条合格笔记至少包含四句话。第一句写观点，不超过 40 字；第二句写证据，说明你从哪里观察到这个变量；第三句写边界，说明什么情况会让观点失效；第四句写行动，说明你下周会观察、阅读或复盘什么。</p>
<p>例如你可以这样组织：我认为某个长期变量正在改变行业利润分配；支持证据来自价格、成本、政策或用户行为；反方证据是变量没有继续扩散或被新的制度约束；行动是把这个变量加入每周观察表，并在月底检查它是否真的改善了判断。</p>
<p>这种笔记方法看起来慢，但它能防止阅读变成情绪强化。只要每门课都沉淀一条完整笔记，500 门书目课程最终会变成一套个人研究数据库。</p>

<h2>十三、推荐阅读</h2>
<p>读完本课后，建议继续沿同一问题链做交叉阅读，把单本书的洞见放进更大的知识网络中检验。</p>
"""
    keep_mentions = 8 if len(key) <= 2 else 22
    return limit_title_mentions(content, key, keep=keep_mentions)


def validate_generated(course: BookCourse, data: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    content = str(data.get("contentHtml") or "")
    audio = clean_space(str(data.get("audioScript") or ""))
    text = strip_tags(content)
    key = title_key(course.title)

    if len(text) < 3600:
        errors.append(f"正文过短：{len(text)}")
    if len(re.findall(r"<h2\b", content, flags=re.I)) < 6:
        errors.append("h2 不足")
    if len(re.findall(r"<h3\b", content, flags=re.I)) < 6:
        errors.append("h3 不足")
    if len(re.findall(r"<p\b", content, flags=re.I)) < 24:
        errors.append("段落不足")
    if "推荐阅读" not in text:
        errors.append("缺少推荐阅读")
    if not re.search(r"练习|反思|评分|反馈", text):
        errors.append("缺少互动练习或反馈")
    phrase_hits = [phrase for phrase in TEMPLATE_PHRASES if phrase in text]
    if phrase_hits:
        errors.append("仍含旧模板短语：" + "、".join(phrase_hits[:3]))
    if key and text.count(key) >= 35:
        errors.append(f"书名堆叠：{text.count(key)}")
    if len(audio) < 170 or len(audio) > 260:
        errors.append(f"音频稿长度异常：{len(audio)}")
    return not errors, errors


def generate_course(course: BookCourse, courses: list[BookCourse], cache_dir: Path, force: bool) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"book{course.n}.json"
    if cache_path.exists() and not force:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        ok, _ = validate_generated(course, data)
        if ok:
            return data

    previous_error = ""
    for attempt in range(4):
        system_prompt, user_prompt = generation_prompts(course, courses, previous_error)
        raw = call_deepseek(system_prompt, user_prompt, max_tokens=2200)
        try:
            data = extract_json(raw)
        except Exception as exc:
            previous_error = f"上次输出不是合法 JSON：{exc}。请只输出一个严格 JSON 对象，不要换行控制字符，不要注释。"
            continue
        data["audioScript"] = normalize_audio_script(course, data)
        data["contentHtml"] = render_content_from_insights(course, courses, data)
        ok, errors = validate_generated(course, data)
        if ok:
            data["_meta"] = {
                "id": course.n,
                "title": course.title,
                "author": course.author,
                "category": course.category,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        previous_error = "；".join(errors)
    raise RuntimeError(f"生成内容未达标：{previous_error}")


def related_links_html(course: BookCourse, courses: list[BookCourse]) -> str:
    items = []
    for other in related_courses(course, courses):
        items.append(
            f'<li><a href="book{other.n}.html">{html.escape(other.title)}</a> — '
            f'{html.escape(other.author)}；同属{html.escape(CATEGORY_LABELS.get(other.category, other.category))}线索。</li>'
        )
    if not items:
        items.append('<li><a href="book-courses.html">返回推荐书目课程</a> — 继续选择同领域课程。</li>')
    return (
        '<div class="related-course-links">\n'
        '<h3>继续学习</h3>\n'
        '<ul>\n' + "\n".join(items) + "\n</ul>\n"
        "</div>"
    )


def purchase_card_html(course: BookCourse) -> str:
    key = html.escape(title_key(course.title))
    return f"""
<div class="purchase-card">
  <h4>购买与延伸学习</h4>
  <p>准备系统阅读《{key}》时，建议优先购买正版纸书或电子书，并把本课练习作为读书笔记模板。</p>
  <div class="buy-row">
    <a id="buy-jd-{course.n}" href="#" target="_blank" rel="nofollow">京东</a>
    <a id="buy-dd-{course.n}" href="#" target="_blank" rel="nofollow">当当</a>
    <a id="buy-db-{course.n}" href="#" target="_blank" rel="nofollow">豆瓣</a>
  </div>
</div>
<script>
(function(){{
  var t = "{key}";
  var e = encodeURIComponent(t);
  var jd = document.getElementById('buy-jd-{course.n}');
  var dd = document.getElementById('buy-dd-{course.n}');
  var db = document.getElementById('buy-db-{course.n}');
  if (jd) jd.href = 'https://search.jd.com/Search?keyword=' + e + '&enc=utf-8';
  if (dd) dd.href = 'http://search.dangdang.com/?key=' + e + '&act=input';
  if (db) db.href = 'https://book.douban.com/subject_search?search_text=' + e;
}})();
</script>
"""


def sanitize_fragment(content_html: str, course: BookCourse, courses: list[BookCourse]) -> BeautifulSoup:
    soup = BeautifulSoup(content_html, "html.parser")
    for tag in soup(["script", "style", "audio", "iframe", "h1"]):
        tag.decompose()
    fragment = BeautifulSoup("", "html.parser")
    for child in list(soup.contents):
        fragment.append(child)
    if "推荐阅读" not in strip_tags(str(fragment)):
        fragment.append(BeautifulSoup("<h2>推荐阅读</h2><p>读完本课后，可以继续沿同一问题链做交叉阅读。</p>", "html.parser"))
    fragment.append(BeautifulSoup(related_links_html(course, courses), "html.parser"))
    fragment.append(BeautifulSoup(purchase_card_html(course), "html.parser"))
    fragment.append(
        BeautifulSoup(
            f'<hr><p><em>康波研究院 · 书目精读课程 · 第{course.n}课 · '
            f'{html.escape(course.title)} · 作者：{html.escape(course.author)} · '
            f'分类：{html.escape(CATEGORY_LABELS.get(course.category, course.category))}</em></p>',
            "html.parser",
        )
    )
    return fragment


def short_label(course: BookCourse, prefix: str) -> str:
    key = title_key(course.title)
    if len(key) > 18:
        key = key[:18] + "..."
    return f"{prefix}：{key}"


def update_bottom_nav(soup: BeautifulSoup, course: BookCourse, courses: list[BookCourse]) -> None:
    nav = soup.find("div", class_="bottom-nav")
    if not nav:
        return
    prev_link = nav.find("a", class_="prev")
    next_link = nav.find("a", class_="next")
    if prev_link:
        if course.n > 1:
            prev = courses[course.n - 2]
            prev_link["href"] = f"book{prev.n}.html"
            prev_link.string = "← " + short_label(prev, "上一课")
        else:
            prev_link["href"] = "book-courses.html"
            prev_link.string = "← 推荐书目课程"
    if next_link:
        if course.n < 500:
            nxt = courses[course.n]
            next_link["href"] = f"book{nxt.n}.html"
            next_link.string = short_label(nxt, "下一课") + " →"
        else:
            next_link["href"] = "book-courses.html"
            next_link.string = "推荐书目课程 →"


def write_page(course: BookCourse, courses: list[BookCourse], data: dict, backup_dir: Path) -> None:
    path = FRONTEND / f"book{course.n}.html"
    if not path.exists():
        raise FileNotFoundError(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / path.name)

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    content_div = soup.find("div", class_="content")
    if not content_div:
        raise RuntimeError(f"{path.name} missing .content")
    content_div.clear()
    fragment = sanitize_fragment(str(data["contentHtml"]), course, courses)
    for child in list(fragment.contents):
        content_div.append(child)

    for source in soup.find_all("source"):
        if source.get("type") == "audio/mpeg" or "lesson" in source.get("src", ""):
            source["src"] = f"audio/books/lesson{course.n}.mp3"
    desc = soup.find("meta", attrs={"name": "description"})
    if desc:
        desc["content"] = (
            f"康波研究院书目精读第{course.n}课：{course.title}，作者{course.author}，"
            f"从{CATEGORY_LABELS.get(course.category, course.category)}、康波周期和投资实践三个层面完成系统解读。"
        )
    update_bottom_nav(soup, course, courses)
    path.write_text(str(soup), encoding="utf-8")


async def synthesize_audio(text: str, target: Path, voice: str, rate: str, pitch: str, ffmpeg: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp3"
        for attempt in range(4):
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
                await communicate.save(str(raw))
                break
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(1.5 * (attempt + 1))
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-i",
                str(raw),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=9",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "48k",
                str(target),
            ],
            check=True,
        )


def ffprobe_duration(path: Path) -> float:
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            text=True,
        ).strip()
        return round(float(raw), 3)
    except Exception:
        return 0.0


async def main_async() -> int:
    global FRONTEND, BOOK_COURSES
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="", help="例如 1,9,151 或 1-50；默认 1-500")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true", help="忽略缓存，重新调用 DeepSeek")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--skip-content", action="store_true")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-8%")
    parser.add_argument("--pitch", default="-2Hz")
    parser.add_argument("--frontend", default=str(FRONTEND))
    parser.add_argument("--cache-dir", default=str(CACHE_ROOT))
    args = parser.parse_args()

    FRONTEND = Path(args.frontend)
    BOOK_COURSES = FRONTEND / "book-courses.html"
    courses = parse_courses()
    ids = parse_ids(args.ids)
    if args.limit:
        ids = ids[: args.limit]
    cache_dir = Path(args.cache_dir)
    backup_dir = BACKUP_ROOT / f"book-deepseek-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"

    ok_count = 0
    fail_count = 0
    for n in ids:
        course = courses[n - 1]
        try:
            data = generate_course(course, courses, cache_dir, args.force)
            if not args.skip_content:
                write_page(course, courses, data, backup_dir)
            if not args.skip_audio:
                target = FRONTEND / "audio" / "books" / f"lesson{n}.mp3"
                await synthesize_audio(clean_space(data["audioScript"]), target, args.voice, args.rate, args.pitch, ffmpeg)
                duration = ffprobe_duration(target)
            else:
                duration = 0.0
            ok_count += 1
            print(f"OK book{n} {course.title} audio={duration}s")
        except Exception as exc:
            fail_count += 1
            print(f"FAIL book{n} {course.title}: {exc}")
    print(f"done ok={ok_count} fail={fail_count} backup={backup_dir} cache={cache_dir}")
    return 0 if fail_count == 0 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
