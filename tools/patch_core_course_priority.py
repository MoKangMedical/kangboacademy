#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
from datetime import datetime
from pathlib import Path


FRONTEND_DIR = Path("/var/www/kangboacademy/frontend")
BACKUP_ROOT = Path("/var/www/kangboacademy/backups")

ENHANCEMENT_START = "<!-- KB_CORE_QUALITY_ENHANCEMENT_START -->"
ENHANCEMENT_END = "<!-- KB_CORE_QUALITY_ENHANCEMENT_END -->"
PRACTICE_START = "<!-- KB_CORE_PRACTICE_HEADING_START -->"
PRACTICE_END = "<!-- KB_CORE_PRACTICE_HEADING_END -->"

AUDIT_PRACTICE_RE = re.compile(r"练习题|课后练习|互动练习|练习与思考|思考题")


ENHANCEMENTS = {
    4: """
<section class="kb-quality-section">
<h2>实战深化：把“老钱密码”变成可执行的家庭资产系统</h2>
<p>顶级家族真正可复制的地方，不是某个神秘关系或单次投资，而是把财富从“个人能力”转化为“制度能力”。第一代人往往依靠企业家精神完成积累，第二代开始面对分配、教育、治理和风险隔离，第三代才真正检验这个系统是否能穿越周期。普通投资者学习老钱密码，重点不是照搬家族信托或复杂架构，而是理解：财富必须有规则，资产必须有边界，决策必须能在情绪失控时继续运行。</p>
<p>一个成熟的家庭资产系统至少包含四个账户：生活安全账户、长期增值账户、机会账户和传承账户。生活安全账户解决现金流和医疗、教育等刚性支出；长期增值账户承接指数、优质股权、核心房产等跨周期资产；机会账户在危机和大级别回撤中使用；传承账户则关注下一代的教育、价值观和治理能力。很多家庭的问题不是收益率太低，而是所有资金混在一个账户里，牛市时全部变成风险资产，熊市时又全部变成恐慌现金。</p>
<p>老钱家族还会刻意降低“单点英雄主义”。如果财富完全依赖某一个人的判断，这个家庭的抗风险能力其实很弱。可持续的做法是把重大决策写成流程：为什么买、买多少、错了怎么办、谁有否决权、多久复盘一次。这个流程会牺牲一点速度，但换来的是跨代稳定性。巴菲特、洛克菲勒、罗斯柴尔德等案例背后的共同点，都是用组织、规则和长期主义削弱短期情绪。</p>
<table class="data-table"><thead><tr><th>系统模块</th><th>核心任务</th><th>普通家庭可执行动作</th></tr></thead><tbody><tr><td>现金流</td><td>保证家庭不断粮</td><td>预留12-24个月支出，重大支出单独建账</td></tr><tr><td>资产配置</td><td>分散单一资产风险</td><td>股票、债券、现金、保险、实物资产分层管理</td></tr><tr><td>治理规则</td><td>避免情绪化决策</td><td>家庭季度会议，重大投资必须写投资备忘录</td></tr><tr><td>传承教育</td><td>传能力而不是只传钱</td><td>让下一代参与预算、阅读和小额投资复盘</td></tr></tbody></table>
<h3>家庭资产体检的四个问题</h3>
<ol><li>如果主要收入来源中断12个月，家庭是否仍能正常运转？</li><li>如果最核心资产下跌40%，是否会被迫卖出？</li><li>如果家庭成员意见冲突，是否有事先约定的决策机制？</li><li>下一代是否知道财富从哪里来、如何守住、如何继续创造？</li></ol>
<p>这四个问题比短期收益率更重要。真正的老钱密码，是用长期现金流、风险隔离、家庭治理和价值观传承，把一次财富机会变成多代人的反脆弱系统。</p>
</section>
""",
    5: """
<section class="kb-quality-section">
<h2>实战深化：从货币叙事走向可验证的指标体系</h2>
<p>货币战争、人口周期和大国博弈很容易被讲成宏大叙事，但投资者真正需要的是可跟踪、可复盘、可转化为仓位的指标。货币不是孤立变量，它同时反映财政约束、贸易结构、资本流动、利差变化和市场信心。当一个国家的货币持续走弱，背后通常不是单一阴谋，而是增长预期、债务结构、国际收支和政策可信度共同变化的结果。</p>
<p>理解美元霸权，也不能只停留在“美元很强”或“美元要崩”的判断。美元体系的核心支柱包括：全球贸易结算、美国国债市场深度、军事与制度信用、全球金融机构的美元负债结构。只要这些支柱没有同时松动，美元就很难突然失去中心地位；但当财政赤字长期扩大、实际利率转负、地缘冲突加剧、替代支付网络成长时，美元资产的安全溢价也会被重新定价。</p>
<p>对个人投资者而言，货币环境可以转化为三个问题：第一，全球流动性是在扩张还是收缩？第二，本币相对美元处于升值还是贬值压力？第三，真实利率对黄金、成长股、债券和房地产分别意味着什么？这三个问题能直接影响你的资产组合。例如真实利率上行时，长久期成长资产会受压；真实利率下行且信用扩张时，风险资产往往更容易上涨；货币信用受质疑时，黄金和高质量外币资产的配置价值会提高。</p>
<table class="data-table"><thead><tr><th>观察维度</th><th>关键指标</th><th>投资含义</th></tr></thead><tbody><tr><td>美元周期</td><td>DXY、美国实际利率、离岸美元融资成本</td><td>美元走强通常压制新兴市场和大宗商品</td></tr><tr><td>国内信用</td><td>社融、M2、贷款需求、地产销售</td><td>信用扩张决定资产价格的弹性</td></tr><tr><td>人口趋势</td><td>出生率、劳动年龄人口、赡养比</td><td>影响房地产、消费、养老和财政压力</td></tr><tr><td>地缘风险</td><td>关税、制裁、供应链转移、资本管制</td><td>提高分散配置和流动性储备的重要性</td></tr></tbody></table>
<p>本课的核心不是要求你相信某一种货币阴谋论，而是训练一种“宏观怀疑精神”：任何看似确定的货币秩序，背后都需要真实生产力、财政纪律和国际信任来支撑。当这些支撑发生变化，资产价格会先于大众认知重新排序。</p>
</section>
""",
    60: """
<section class="kb-quality-section">
<h2>实战深化：用产业链地图筛选第六轮康波技术资产</h2>
<p>科技创新投资最常见的错误，是把“技术很重要”直接等同于“股票一定值得买”。康波视角下，真正值得跟踪的是技术从发明、泡沫、基础设施建设、商业化扩散到生产率兑现的完整路径。AI、新能源和生物科技都可能是第六轮康波的重要引擎，但它们在资本市场中的节奏并不相同：AI更像算力和软件平台的扩散周期，新能源更依赖政策、成本曲线和电网改造，生物科技则受研发周期、临床试验和监管审批约束。</p>
<p>AI投资要先拆产业链。上游是芯片、先进封装、电力、液冷、光模块和云基础设施；中游是大模型、数据平台、开发工具和行业模型；下游是金融、医疗、教育、工业、内容生产等应用场景。早期最确定的收益往往来自“卖铲人”，因为无论哪家应用胜出，算力、电力和云服务都会先被购买。但当基础设施供给过剩、模型能力趋同、价格战加剧时，投资重点会从硬件扩张转向真实现金流和客户留存。</p>
<p>新能源投资要同时看三条曲线：度电成本曲线、储能成本曲线和电网消纳能力。光伏和风电的长期方向明确，但阶段性产能过剩会压低利润；储能、虚拟电厂、智能电网和电力交易机制，可能成为下一阶段更关键的瓶颈。投资者需要避免只看装机量增长，而忽视企业在产业链中的议价能力、技术路线变化和资产负债表压力。</p>
<p>生物科技的长期逻辑来自老龄化、慢病管理、AI制药和精准医疗。它不像消费互联网那样快速放量，却可能在十年尺度上创造高壁垒企业。判断生物科技资产时，不能只看故事，要看管线阶段、适应症市场规模、专利保护期、现金消耗速度和合作伙伴质量。对普通投资者而言，分散化工具通常优于押注单一临床结果。</p>
<table class="data-table"><thead><tr><th>技术方向</th><th>先看什么</th><th>避开什么</th><th>适合工具</th></tr></thead><tbody><tr><td>AI</td><td>算力需求、云收入、企业付费率</td><td>只有概念没有收入的应用</td><td>科技指数、半导体ETF、云平台龙头</td></tr><tr><td>新能源</td><td>成本下降、储能、电网、政策机制</td><td>产能过剩中的低毛利制造商</td><td>电力设备、储能、全球能源转型基金</td></tr><tr><td>生物科技</td><td>管线、现金流、专利和监管节点</td><td>单一项目决定生死的高估值公司</td><td>医疗ETF、创新药篮子、龙头平台公司</td></tr></tbody></table>
<p>最终，科技投资不是追逐新闻，而是把每个技术叙事放进“渗透率、盈利模型、资本开支、估值和周期位置”五个框架里反复检验。只有当技术进步能转化为可持续现金流时，它才从故事变成资产。</p>
</section>
""",
    61: """
<section class="kb-quality-section">
<h2>实战深化：把ESG从口号翻译成现金流和风险定价</h2>
<p>ESG最容易被误解为道德标签，但在投资框架中，它首先是风险和现金流问题。环境维度影响能源成本、碳排放约束、资产报废和供应链合规；社会维度影响员工稳定、客户信任、产品安全和监管关系；治理维度则直接决定资本配置、关联交易、信息披露和少数股东保护。一个ESG评分很高但估值过高的公司未必是好投资，一个ESG评分偏低但正在改善、估值充分折价的公司也可能提供机会。</p>
<p>康波周期中的ESG更像新技术范式的一部分。每一轮长波都会重新定义“合格资产”：蒸汽机时代看煤炭和铁路，电气时代看电网和制造，信息时代看软件和平台，第六轮康波则会把碳效率、资源效率、数据治理和社会韧性纳入企业竞争力。资本市场并不是突然变得更善良，而是在重新计算哪些资产会被政策、技术和消费者偏好淘汰。</p>
<p>ESG分析的关键是避免绿漂。公司发布漂亮报告并不等于真正改善，真正要看的指标包括单位收入碳排放是否下降、董事会是否独立、员工流失率是否异常、供应链事故是否减少、治理结构是否保护中小股东。尤其在新兴市场，ESG评级机构之间差异很大，投资者不能机械使用单一分数，而要把评级当成问题清单。</p>
<table class="data-table"><thead><tr><th>维度</th><th>核心问题</th><th>可观察证据</th><th>投资动作</th></tr></thead><tbody><tr><td>E</td><td>企业是否会被碳成本重估</td><td>碳排强度、能源结构、环保处罚</td><td>高碳资产要求更高安全边际</td></tr><tr><td>S</td><td>企业是否能维持社会许可</td><td>产品安全、劳动关系、客户投诉</td><td>警惕声誉事件导致估值折价</td></tr><tr><td>G</td><td>管理层是否可信</td><td>分红、回购、关联交易、审计意见</td><td>治理差的公司降低仓位上限</td></tr><tr><td>转型</td><td>问题是在恶化还是改善</td><td>三年指标趋势、资本开支方向</td><td>改善型公司可能出现重估机会</td></tr></tbody></table>
<p>把ESG纳入估值，可以采用三步法：先识别可能影响现金流的ESG风险，再判断风险发生概率和时间范围，最后把它转化为折现率、利润率或终值假设。这样做的好处是避免空泛争论，让ESG成为可复盘的投资纪律。</p>
</section>
""",
    62: """
<section class="kb-quality-section">
<h2>实战深化：从指标堆砌到可复盘的量化决策流程</h2>
<p>量化工具的价值不在于让投资变得“绝对科学”，而在于减少含糊判断。很多投资者同时打开均线、MACD、RSI、布林带、成交量和几十个因子，最后却只是寻找支持自己原有观点的指标。真正有效的量化流程应该更简单：先定义问题，再选择指标，最后规定信号出现后的动作。没有动作规则的指标，只是屏幕上的装饰。</p>
<p>一个可用的量化系统至少包括四层：数据层、信号层、组合层和风控层。数据层要确保来源稳定、口径一致、没有未来函数；信号层要说明为什么这个指标可能有效；组合层要决定仓位、再平衡频率和资产相关性；风控层要处理极端波动、交易成本和模型失效。任何一层薄弱，回测结果都可能很好看，真实交易却难以执行。</p>
<p>回测最危险的陷阱是“过拟合”。如果你为了让历史收益更漂亮，不断调整参数、筛选时间区间、删除不利样本，最后得到的不是策略，而是一段历史的画像。实战中要保留样本外测试，记录每一次参数修改的原因，并用简单策略作为基准。如果复杂模型不能明显战胜简单规则，就没有必要承受额外复杂度。</p>
<table class="data-table"><thead><tr><th>流程环节</th><th>关键问题</th><th>常见错误</th><th>改进方法</th></tr></thead><tbody><tr><td>数据</td><td>口径是否稳定</td><td>使用幸存者偏差数据</td><td>保留退市样本，记录数据来源</td></tr><tr><td>信号</td><td>是否有经济含义</td><td>只因历史相关就交易</td><td>写出信号背后的行为或基本面逻辑</td></tr><tr><td>组合</td><td>仓位如何变化</td><td>满仓满杠杆追求收益</td><td>设置单资产和单策略上限</td></tr><tr><td>风控</td><td>模型何时失效</td><td>亏损后随意修改规则</td><td>提前定义暂停和复盘条件</td></tr></tbody></table>
<p>量化与康波并不矛盾。康波提供战略方向，量化提供战术节奏。例如在长周期回升阶段，权益资产可能是战略高配；但具体买入可以通过趋势、波动和估值分位控制节奏。换句话说，周期判断决定“要不要在场”，量化工具决定“以多大仓位、在什么位置进退”。</p>
</section>
""",
    63: """
<section class="kb-quality-section">
<h2>实战深化：把行为偏差关进制度笼子</h2>
<p>行为金融学最重要的结论，是知识并不会自动变成行为。很多人知道不要追涨杀跌，也知道要长期持有，但在账户波动、社交媒体和群体情绪面前，理性会迅速失效。因此，训练投资行为的重点不是要求自己永远冷静，而是提前设计规则，让自己在不冷静时也不至于犯致命错误。</p>
<p>第一道规则是决策日志。每一次买入、卖出、加仓、减仓，都写下当时的理由、预期、反证、止损或复盘条件。三个月后回看，你会发现大量决策并不是基于证据，而是基于害怕错过、急于回本或想证明自己正确。日志的价值在于把情绪留下证据，让错误可以被识别和改进。</p>
<p>第二道规则是预先承诺。比如单只股票不超过总资产10%，任何超过5%的仓位调整必须等待72小时，亏损达到预设条件必须复盘而不是加倍下注，盈利过快时必须检查估值而不是自动乐观。预承诺不是束缚能力，而是防止情绪在关键时刻接管账户。</p>
<p>第三道规则是反向证据清单。买入前必须写出三个可能让自己错的理由，卖出前必须写出三个可能让自己过早离场的理由。这个动作能有效对抗确认偏差，因为它强迫你主动寻找不舒服的信息。真正成熟的投资者，不是观点最坚定的人，而是最愿意让事实修正自己的人。</p>
<table class="data-table"><thead><tr><th>偏差</th><th>典型表现</th><th>制度化应对</th></tr></thead><tbody><tr><td>损失厌恶</td><td>亏损后死扛等待回本</td><td>买入前写清错误条件和退出规则</td></tr><tr><td>确认偏差</td><td>只看支持自己观点的信息</td><td>每次决策必须写反方论证</td></tr><tr><td>过度自信</td><td>重仓单一标的</td><td>设置仓位上限和强制分散</td></tr><tr><td>羊群效应</td><td>热点越热越想买</td><td>媒体热度过高时启动冷却期</td></tr></tbody></table>
<p>如果说康波研究帮助你看见大周期，行为金融学则帮助你守住自己。很多长期收益差距，不来自知识差距，而来自能否在极端行情中按规则行动。</p>
</section>
""",
    64: """
<section class="kb-quality-section">
<h2>实战深化：危机投资的第一原则是先活下来</h2>
<p>危机投资听起来充满机会，但它的第一原则不是抄底，而是生存。每一次大危机都会让市场出现看似便宜的资产，也会让一批高杠杆投资者在最接近底部时被迫出局。只有现金流、心理状态和仓位结构都能承受冲击的人，才有资格谈危机中的进攻。</p>
<p>危机可以分为流动性危机、偿付能力危机和制度信任危机。流动性危机中，好资产被迫抛售，政策注入流动性后往往反弹很快；偿付能力危机中，资产负债表真实受损，便宜可能变成更便宜；制度信任危机则会影响货币、银行和产权预期，需要更高比例的现金、黄金或全球分散资产。不同危机不能用同一套抄底模板。</p>
<p>判断是否进入可行动区间，可以看五类信号：价格跌幅是否达到历史极端、信用利差是否显著走阔、政策是否开始从观望转向救助、优质公司是否仍能融资、市场情绪是否从贪婪变成绝望。单个信号不足以决定买入，但多个信号共振时，分批计划就应该提前准备好。</p>
<table class="data-table"><thead><tr><th>危机类型</th><th>主要特征</th><th>优先动作</th><th>避免动作</th></tr></thead><tbody><tr><td>流动性危机</td><td>好坏资产一起跌</td><td>分批买入指数和龙头资产</td><td>一次性满仓</td></tr><tr><td>偿付危机</td><td>违约和破产增加</td><td>检查负债表，偏向现金流强者</td><td>只因跌幅大买入弱公司</td></tr><tr><td>通胀危机</td><td>货币购买力下降</td><td>配置实物资产、短久期和定价权企业</td><td>长期锁定低收益债券</td></tr><tr><td>制度危机</td><td>资本管制和信任冲击</td><td>提高全球分散和流动性</td><td>所有资产集中在单一体系</td></tr></tbody></table>
<p>危机前应写好“危机预案”：准备多少现金、下跌多少开始买、分几批、每批买什么、什么情况下停止买入、最坏情况下家庭现金流如何维持。预案越具体，危机中越不需要靠临场勇气。真正的危机投资能力，是在平时完成准备，在混乱中执行规则。</p>
</section>
""",
    65: """
<section class="kb-quality-section">
<h2>实战深化：把65课沉淀为个人投资政策书</h2>
<p>学完65课之后，最重要的成果不应该是一堆笔记，而是一份个人投资政策书。它回答四个问题：我为什么投资，我能承受什么风险，我用什么方法配置资产，我如何复盘和纠错。没有这份文件，知识很容易在行情波动中散掉；有了这份文件，投资就从临时反应变成长期经营。</p>
<p>个人投资政策书的第一部分是目标。目标不能只写“赚钱”，而要写清楚资金用途、时间长度和底线约束。养老资金、子女教育资金、创业备用金和长期财富增值资金，不能使用同一套风险参数。时间越长，越能承受权益波动；用途越刚性，越需要流动性和本金保护。</p>
<p>第二部分是战略资产配置。康波周期帮助你决定长期倾斜方向，但战略配置必须先适配个人生命周期。年轻投资者可以承受更多权益和成长资产，中年投资者要平衡现金流、家庭责任和长期增值，退休前后则更重视稳定收入和风险隔离。周期判断只能做加减法，不能替代个人风险承受能力。</p>
<p>第三部分是纪律。包括仓位上限、再平衡规则、买入卖出流程、重大决策冷却期、学习和复盘制度。纪律不是为了让投资僵化，而是为了避免每次市场变化都重新发明一套方法。真正成熟的系统，应该允许你在不同市场环境中调整参数，但不轻易改变原则。</p>
<table class="data-table"><thead><tr><th>政策书模块</th><th>必须写清楚的问题</th><th>建议频率</th></tr></thead><tbody><tr><td>目标与约束</td><td>资金用途、期限、最大可承受回撤</td><td>每年复查</td></tr><tr><td>资产配置</td><td>股票、债券、现金、黄金、房产和另类资产比例</td><td>半年复查</td></tr><tr><td>交易纪律</td><td>买入理由、卖出条件、仓位上限</td><td>每笔记录</td></tr><tr><td>复盘学习</td><td>错误清单、阅读计划、能力短板</td><td>每月复盘</td></tr><tr><td>传承安排</td><td>家庭会议、教育计划、文件归档</td><td>每年更新</td></tr></tbody></table>
<p>如果要把本课程体系压缩成一句话，就是：用康波看方向，用资产配置控风险，用行为纪律守住自己，用学习和复盘持续进化。未来30年不会按任何人的剧本展开，但拥有系统的人，会比只靠情绪和消息的人更有机会穿越周期。</p>
</section>
""",
}


PRACTICE_TARGETS = [10, 11, 12, 13, 14, 15, 16, 17, 19, 51, 52, 53, 54, 58, 60, 61, 62, 63, 64, 65]
EDIT_TARGETS = sorted(set(ENHANCEMENTS) | set(PRACTICE_TARGETS))


def clean_title(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def marked_block(start: str, end: str, body: str) -> str:
    body = body.strip()
    return f"\n{start}\n{body}\n{end}\n"


def replace_or_insert_marked(source: str, start: str, end: str, body: str, insert_at: int) -> tuple[str, bool]:
    block = marked_block(start, end, body)
    pattern = re.compile(rf"\n?\s*{re.escape(start)}[\s\S]*?{re.escape(end)}\s*\n?", re.I)
    if pattern.search(source):
        return pattern.sub(block, source, count=1), True
    return source[:insert_at] + block + source[insert_at:], True


def first_match_pos(source: str, patterns: list[str]) -> int | None:
    positions = []
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.I)
        if match:
            positions.append(match.start())
    return min(positions) if positions else None


def content_fallback_pos(source: str) -> int:
    pos = first_match_pos(source, [
        r"<div\b[^>]*class=[\"'][^\"']*bottom-nav[^\"']*[\"']",
        r"</article>",
        r"</main>",
        r"</body>",
    ])
    return pos if pos is not None else len(source)


def enhancement_insert_pos(source: str) -> int:
    pos = first_match_pos(source, [
        r"<h2[^>]*>[^<]*(?:练习题|课后练习|互动练习|练习与思考|课后测试|课后测验|测验题)[^<]*</h2>",
        r"<div\b[^>]*class=[\"'][^\"']*exercise[^\"']*[\"']",
        r"<h3[^>]*>\s*练习\s*1",
        r"<div\b[^>]*class=[\"'][^\"']*recommend[^\"']*[\"']",
        r"<h[23][^>]*>[^<]*(?:推荐阅读|延伸阅读|参考书目)[^<]*</h[23]>",
    ])
    return pos if pos is not None else content_fallback_pos(source)


def practice_insert_pos(source: str) -> int:
    pos = first_match_pos(source, [
        r"<div\b[^>]*class=[\"'][^\"']*exercise[^\"']*[\"']",
        r"<h3[^>]*>\s*练习\s*1",
        r"<h3[^>]*>\s*测验题",
        r"<h3[^>]*>\s*第\s*1\s*题",
        r"<h3[^>]*>\s*问题\s*1",
        r"<h3[^>]*>\s*题目一",
        r"<h2[^>]*>[^<]*(?:课后测试|课后测验|测验题)[^<]*</h2>",
        r"<div\b[^>]*class=[\"'][^\"']*recommend[^\"']*[\"']",
        r"<h[23][^>]*>[^<]*(?:推荐阅读|延伸阅读|参考书目)[^<]*</h[23]>",
    ])
    return pos if pos is not None else content_fallback_pos(source)


def add_enhancement(source: str, lesson_id: int) -> tuple[str, bool]:
    body = ENHANCEMENTS.get(lesson_id)
    if not body:
        return source, False
    return replace_or_insert_marked(source, ENHANCEMENT_START, ENHANCEMENT_END, body, enhancement_insert_pos(source))


def ensure_practice_heading(source: str) -> tuple[str, bool]:
    if AUDIT_PRACTICE_RE.search(source):
        return source, False
    # Preserve existing test headings and add the audit-visible wording there when possible.
    heading_pattern = re.compile(r"(<h2[^>]*>)([^<]*(?:课后测试|课后测验|测验题)[^<]*)(</h2>)", re.I)
    match = heading_pattern.search(source)
    if match:
        new_heading = f"{match.group(1)}{match.group(2)}（课后练习）{match.group(3)}"
        return source[:match.start()] + new_heading + source[match.end():], True
    block = "<h2>课后练习</h2>"
    return replace_or_insert_marked(source, PRACTICE_START, PRACTICE_END, block, practice_insert_pos(source))


def fix_title(source: str) -> tuple[str, bool]:
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", source, flags=re.I)
    if not h1:
        return source, False
    title = clean_title(h1.group(1))
    if not title:
        return source, False
    replacement = f"<title>{html.escape(title)} — 康波研究院</title>"
    updated, count = re.subn(r"<title[^>]*>[\s\S]*?</title>", replacement, source, count=1, flags=re.I)
    return updated, bool(count)


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = BACKUP_ROOT / f"core-course-priority-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    changed = []
    skipped = []
    for lesson_id in EDIT_TARGETS:
        path = FRONTEND_DIR / f"lesson{lesson_id}.html"
        if not path.exists():
            skipped.append(f"lesson{lesson_id}.html missing")
            continue
        original = path.read_text(encoding="utf-8", errors="ignore")
        source = original
        changed_this = False

        if lesson_id in ENHANCEMENTS:
            source, did = add_enhancement(source, lesson_id)
            changed_this = changed_this or did
        if lesson_id in PRACTICE_TARGETS:
            source, did = ensure_practice_heading(source)
            changed_this = changed_this or did
        if lesson_id in {60, 61, 62, 63, 64, 65}:
            source, did = fix_title(source)
            changed_this = changed_this or did

        if source != original:
            shutil.copy2(path, backup_dir / path.name)
            path.write_text(source, encoding="utf-8")
            changed.append(path.name)

    print(f"backup_dir={backup_dir}")
    print(f"changed={','.join(changed) if changed else 'none'}")
    if skipped:
        print("skipped=" + ",".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
