# 合作商商品离线导入

本工具仅生成待人工审核的候选映射，不部署、不调用微信、不更新生产文件。离线校验通过不证明商家真实、授权有效、商品在售或小程序已上线。仅允许修改及导入获得真实商家资料支持的记录；禁止拿京东搜索入口充当真实商品。

2026-09-27 用户确认：目前没有合作商授权或商品 ID，线上 500 条均为 `jd_search`，commission 为 0。此项为用户提供的状态，不是本工具实时线上核验结果。当前商品资料交付仅为表头空模板，不生成真实或 demo 商品候选映射；佣金为 0 不等于有授权或可购买。

## 使用

在项目根目录运行（Python 3.10+，仅标准库，无网络请求）：

```sh
python3 tools/import_partner_products.py /absolute/path/partner.csv
python3 tools/import_partner_products.py /absolute/path/partner.json --dry-run
python3 tools/import_partner_products.py /absolute/path/partner.csv --allow-partial
python3 tools/import_partner_products.py /absolute/path/partner.csv --output /absolute/path/partner-20260927.candidate.json
python3 tools/import_partner_products.py --generate-matching-csv /absolute/path/partner-matching-500.csv
python3 -B -m unittest discover -s tools -p 'test_partner_products.py' -v
```

默认要求 1..500 每个书 ID 恰好一条；`--allow-partial` 才允许不足 500 条，仍报告覆盖率和缺失 ID。空批次、重复 ID、未知 ID、任一不合格记录均导致整批拒绝，返回码 2，绝不静默过滤后写出。返回码 0 仅代表离线校验成功。默认 dry-run 不写文件。`--output` 才创建新文件，必须以 `.candidate.json` 结尾，父目录必须已存在，禁止覆盖已有文件及 `/var/www`、`/etc` 下的路径；不能与 `--dry-run` 同用。

默认候选 `authorizationStatus` 为 `unverified`，即使其他格式正确也不能获得后端购买就绪状态。人工必须先逐条核验真实授权主体、范围、有效期、对应商品目标及公开售后渠道；完成后才可从原始 CSV/JSON 输入重新生成新的已审核候选：

```sh
python3 tools/import_partner_products.py /absolute/path/partner.csv --authorization-reviewed --output /absolute/path/partner-reviewed.candidate.json
```

`--authorization-reviewed` 是操作者对整批真实授权已经人工核验的显式声明，才输出 `authorizationStatus=confirmed`；它不是自动核验，也不会绕过任何必填或商品目标校验。禁止为了通过测试或启用购买而伪造授权、引用、售后渠道或使用该标记。当前用户没有合作商授权和商品 ID，因此真实数据不得使用此标记。参数可结合默认 dry-run 预检；只有 `--output` 才写文件。不能与 `--generate-matching-csv` 一起使用。

`--generate-matching-csv NEW.csv` 是独立的显式写文件操作：从 canonical 书目生成 500 行待商家填写的 UTF-8 BOM CSV，只填 `bookId`、`title`、`author`，其他列全部空白，不含 readiness 字段或 demo 商品。状态为 `UNFILLED_MATCHING_WORKSHEET_NOT_PRODUCTS`，不代表商品校验通过。禁止与输入文件、`--output`、`--dry-run`、`--allow-partial` 混用；允许 `--catalog` 指定同结构契约。只创建新 CSV，禁止覆盖任何已有文件及生产目录，不覆盖 `data/partner-products.template.csv` 表头空模板。待填写 CSV 缺少授权和商品目标，直接导入会被整批拒绝。

## 输入契约

模板只有表头，没有伪造商品行。支持 UTF-8 / UTF-8 BOM CSV、JSON 对象数组、`{"书ID": {输入字段}}` 映射。映射键自动成为 `bookId`，已有 `bookId` 必须一致。输入 JSON 所有字段值必须为字符串，包括 ID、价格和佣金；拒绝重复 JSON 键、CSV 重复列、错列、未知字段和控制字符。不接受销量、微信联系人、`authorizationStatus` 或任意 readiness 标记，避免这些未经核实的声明进入候选数据。候选输出是后端格式，不是原始输入格式：含嵌套售后对象、授权状态和带 `%` 的佣金比例，不接受直接再次导入候选来继承审核状态；重新审核必须使用原始输入和显式 CLI 标记。

必填字段：

| 字段 | 要求 |
| --- | --- |
| `bookId`, `title`, `author` | ID 为 1..500，书名作者须与书目逐字匹配 |
| `channel`, `channelName`, `settlementMode` | 渠道限 `wechat_shop`、`jd_union`、`custom`；结算限 `agreement`、`direct`、`wechat_shop`、`cps`、`commission`、`affiliate` |
| `productId` | 商家提供的实际商品 ID，字母数字下划线或连字符，最长 128 字符 |
| `merchantName`, `merchantId` | 实际商家主体及可核对的店铺或主体标识 |
| `authorizationBasis`, `authorizationReference` | 合作/分销/销售授权依据及可追溯的协议、授权文档编号或资料位置；不得填口头猜测或伪造凭证 |
| `afterSales` | 商家提供的可公开售后政策描述字符串，最长 500 字符 |
| `afterSalesContact` | 必填、可公开的实际售后服务渠道字符串，最长 200 字符；由商家提供，不生成个人微信联系人，不得填内部文件路径或授权文档引用 |
| `targetEvidence` | 可追溯证据，供人工核验具体商品、版本、书目、商家及跳转目标的一致性 |

可选字段为模板中其余列。填报说明：

- 微信商品仅使用 `miniProgramAppId` + `path`。AppID 格式为 `wx` 加 16 位小写十六进制字符，页面路径须从 `pages/` 或 `/pages/` 开始并包含完整商品 ID token。不能用店铺首页或只有 ID 没有可执行目标的记录。mini 当前仅支持核验过的 `mini_program` 和 HTTPS `clipboard`；本轮无条件拒绝 `business_view`。为保持空模板不变，保留 `businessType`、`queryString` 表头，但必须留空，填入即拒绝。目标仍须经过授权资料和真机核验，格式通过不等于核验完成。
- 外部渠道要求 `externalUrl` 或 `affiliateUrl` 为 HTTPS 具体商品地址，URL 路径/参数包含完整商品 ID；两者同时提供时必须相同。京东仅接受 `https://item.jd.com/商品ID.html`，不接收搜索、短链、重定向或未解析推广链接。其他商家的链接同样拒绝明显搜索/重定向目标；不符合保守规则的合法链接进入人工处理，不放宽为任意 URL。
- `price` 可留空，禁止自行填价格。提供时必须是非负十进制金额（最多两位小数），同时提供 `priceEvidence`。`commissionRate` 输入使用 0..100 百分数（不带 `%`），提供时要求 `commissionEvidence`；佣金类结算必须提供二者。候选输出统一追加 `%`（如输入 `2.50` 输出 `2.50%`），与后端佣金格式一致；未提供则不补值。工具不会补造价格、销量或佣金，也不会抓取网络价格。
- `source` 若提供必须等于 `channel`；`openType` 若提供必须为目标对应的 `mini_program` 或 `clipboard`。工具只推导这两个路由字段，不推导真实商业事实。

默认书目来自 `shared/content-contract.json` 的 `courses` 数组，**仅选择 `kind=book` 的 500 条，使用 `number` 作为书 ID、canonical `title` 和 `author`**，不使用 `displayTitle`、核心课程或旧 data 搜索快照。要求 number 为 1..500 的唯一整数，key 与 `book:number` 一致，作者和书名非空；不完整或冲突即拒绝。`--catalog` 仅接受同结构内容契约，不再接受旧商品映射充当书目，不应为迁就错误商品而修改契约。内容相同的课程条目仍按各自书 ID 独立审核，不推测版本或 ISBN。

## 审核与生产边界

后端契约为 `authorizationReference`、`merchantName`、`afterSales`、`authorizationStatus`。输入 `afterSales` 为描述字符串，另必填 `afterSalesContact`；候选输出转换为 `afterSales: {description: 输入afterSales, contact: 输入afterSalesContact}`，不额外输出顶层 `afterSalesContact`。`merchantName` 最长 200 字符且必须可公开；公开字段及商品目标不得包含私密授权引用。`authorizationStatus` 只由 CLI 人工审核标记决定，不能在输入里设置。旧 `afterSalesPolicy` 不接受。`merchantId`、`authorizationBasis`、`targetEvidence` 为额外内部审核资料。

导入工具不接受或生成 `purchaseEntryReady`、`canBuy`、`commissionReady`。这些不是商家可自行声明的输入；后端必须结合审核资料和具体目标计算运行状态。mini 前端的接入契约是后端 `purchaseEntryReady === true`，同时入口非 search 且具有具体商品目标；不得独自相信 `canBuy`，搜索入口和缺少授权的记录不能据此变成可购买商品。本子任务不修改或声称已验证前后端的运行实现。

候选 JSON 顶层仍是书 ID 映射，购书字段与 `tools/configure_wechat_commerce.py`、`backend_remote/main.py` 和 `server_patch/backend/main.py` 兼容，另保留商家、授权、售后和证据字段用于审核。不会自动调用配置脚本；该脚本可写生产，不能把运行它当作本工具的下一步自动操作。候选内的审核资料应按内部资料保管，不应包含密钥、身份证号或未获准公开的个人信息。

商品 URL、授权文档及证据引用仅供内部核验，不应公开到网页、静态下载目录或公共 API；候选文件不属于公开交付包。后端负责隔离内部审核信息与客户端运行所需字段，本工具不发布这些文件，也不声称已验证后端信息隔离。

人工需逐条确认商家身份与授权范围、版本匹配、商品实际可售、售价/佣金证据时效、售后责任，并在真实小程序配置下核验跳转。现有后端会合并默认搜索链接并优先使用全局 AppID/业务视图配置，空字段也可能被忽略，因此候选文件本身不能证明线上最终跳转正确，必须检查最终 API 返回及真机打开结果。后端对商品 ID 的存在可能推断佣金就绪，该推断也不等于已获得分佣资格。

不足 500 条的候选不能直接替换完整生产映射。审核后应另行形成可审阅的合并结果，经过用户对生产更新最后一步的授权再部署。当前工具不执行合并、支付、联系商家、提交审核或发布。

测试中全部商家、授权、价格及目标资料都是显式虚构 fixture，只存在于测试临时目录，不可作为生产资料。模板不携带任何测试数据。

集成测试直接从当前 `server_patch/backend/main.py` AST 提取真实授权、公开信息、商品合并、佣金和 `book_open_action` 函数，执行 CLI 写出临时候选并交给这些后端函数验证，不复制或模拟后端判断。覆盖默认未审核不能购买、显式已审核 mini_program/HTTPS clipboard 可配置购买、搜索默认值被替换、缺授权/售后仍拒绝、百分比格式及内部引用不出现在公开商家信息。AST 提取不运行服务启动代码，不连接数据库或网络；通过只证明当前本地契约一致，不代表真实授权、线上状态、支付或微信真机跳转已核验。
