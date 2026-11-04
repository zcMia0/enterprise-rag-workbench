"""测评语料与 QA 集的**单一数据源**(Single Source of Truth)。

设计原则
--------
1. 语料只在这里定义一次, 由 ``gen_corpus.py`` 物化成 md / txt / docx / pdf / png 五种真实文件。
2. QA 集中的 ``key``(唯一关键串)必须真实出现在对应文档里, ``gen_corpus.py`` 会逐条断言,
   避免"问题与语料漂移"导致指标虚高。
3. 表格用 ``rows``(二维数组) 表达, md 渲染成管道表格、docx 渲染成 Word 表格、pdf 渲染成
   等宽文本行、png 渲染成"扫描件"位图 —— 同一份结构化数据覆盖四条解析链路。

复杂度标记
----------
``complex=True`` 表示该文档"格式复杂"(含表格 / 图片 / 混排), 是入库成功率指标的分母。
简单文档(纯文本)只作为对照, 不参与复杂文档成功率计算。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 语料定义
# ---------------------------------------------------------------------------
# 每个 doc:
#   filename  目标文件名(扩展名决定生成格式)
#   title     文档标题
#   complex   是否计入"复杂文档"(含表格/图片/混排)
#   sections  章节列表, 每项 {heading, paras, tables}
#       paras   [str, ...]                 普通段落
#       tables  [[[cell, ...], ...], ...]  表格列表(每张表是二维数组)
# ---------------------------------------------------------------------------

DOCS: list[dict] = [
    # ===================== Markdown + 表格 =====================
    {
        "filename": "handbook.md",
        "title": "员工手册",
        "complex": True,
        "sections": [
            {
                "heading": "第一章 入职流程",
                "paras": [
                    "新员工入职需完成四个步骤: 提交材料、签订协议、开通账号、参加培训。",
                    "入职培训包含公司文化、信息安全与合规三部分, 通常在一周内完成, 培训考核不合格者需补训一次。",
                ],
                "tables": [],
            },
            {
                "heading": "第二章 考勤与休假",
                "paras": [
                    "员工实行标准工时制, 每日工作八小时, 上班时间为上午九点至下午六点, 午休一小时。",
                    "年假按司龄递增: 满一年五天, 满三年十天, 满五年十五天, 年假需提前三个工作日申请。",
                    "病假需提供二级以上医疗机构证明, 事假应提前申请并由直属主管审批。",
                ],
                "tables": [],
            },
            {
                "heading": "第三章 员工档案字段说明",
                "paras": [
                    "下表为人力系统中员工档案的核心字段定义, 新增字段需走数据治理评审。",
                ],
                # 12 行宽表: 定长切分必然被截断
                "tables": [
                    [
                        ["字段名", "类型", "必填", "说明"],
                        ["emp_no", "varchar(16)", "是", "工号, 格式 EB-2024-0001"],
                        ["emp_name", "varchar(32)", "是", "员工姓名"],
                        ["dept_code", "varchar(8)", "是", "部门编码, 如 D-ENG-01"],
                        ["job_level", "varchar(4)", "是", "职级, P1 至 P9"],
                        ["hire_date", "date", "是", "入职日期"],
                        ["probation_end", "date", "否", "试用期结束日, 默认入职后 90 天"],
                        ["id_card", "varchar(18)", "是", "身份证号, 需加密存储"],
                        ["bank_acct", "varchar(32)", "是", "工资卡号, 需脱敏展示"],
                        ["cost_center", "varchar(12)", "否", "成本中心编码"],
                        ["manager_no", "varchar(16)", "否", "直属主管工号"],
                        ["status", "tinyint", "是", "状态: 1 在职 2 离职"],
                    ]
                ],
            },
        ],
    },
    {
        "filename": "pricing.md",
        "title": "产品定价与折扣政策",
        "complex": True,
        "sections": [
            {
                "heading": "一、标准版阶梯定价",
                "paras": [
                    "标准版按坐席数分档计价, 按年付费可享九折, 三年一次性付费可享七五折。",
                ],
                "tables": [
                    [
                        ["坐席区间", "单价(元/坐席/月)", "最小起订"],
                        ["1-50", "199", "10 坐席"],
                        ["51-200", "169", "51 坐席"],
                        ["201-500", "139", "201 坐席"],
                        ["500 以上", "119", "议价"],
                    ]
                ],
            },
            {
                "heading": "二、渠道折扣审批规则",
                "paras": [
                    "渠道折扣需按档位逐级审批, 任何低于底价的报价都必须由销售副总裁签批, 并在 CRM 中留痕。",
                ],
                # 较长的表: 易被切断
                "tables": [
                    [
                        ["折扣区间", "审批人", "所需材料", "备注"],
                        ["100%-91%", "销售经理", "报价单", "标准流程"],
                        ["90%-81%", "销售总监", "报价单+客户确认函", "需说明竞争情况"],
                        ["80%-71%", "销售副总裁", "折扣申请单+毛利测算", "毛利不得低于 45%"],
                        ["70% 及以下", "CEO", "折扣申请单+战略价值说明", "仅限战略客户"],
                    ]
                ],
            },
            {
                "heading": "三、续费与增购",
                "paras": [
                    "续费价格按上一年度合同金额的 95% 执行, 增购坐席按当前档位单价计算, 不重新分档。",
                ],
                "tables": [],
            },
        ],
    },
    {
        "filename": "onboarding.md",
        "title": "研发入职指引",
        "complex": True,
        "sections": [
            {
                "heading": "环境准备",
                "paras": [
                    "新同事请先领取笔记本并接入内网 VPN, VPN 客户端需从内网软件中心下载, 不要使用第三方渠道。",
                    "代码仓库统一使用 Git, 主干分支为 main, 合并前需通过 CI 与至少一位同事的 Code Review。",
                ],
                "tables": [],
            },
            {
                "heading": "常用系统账号申请",
                "paras": ["以下系统需在入职三个工作日内完成申请。"],
                # 中等表: 可能刚好存活
                "tables": [
                    [
                        ["系统", "申请入口", "审批人", "开通时限"],
                        ["代码仓库", "IT 服务台", "技术主管", "1 工作日"],
                        ["CI 流水线", "IT 服务台", "技术主管", "1 工作日"],
                        ["日志平台", "可观测平台自助申请", "自动审批", "即时"],
                        ["数据库只读", "DBA 工单", "DBA 负责人", "2 工作日"],
                        ["生产发布权限", "变更管理平台", "研发总监", "3 工作日"],
                    ]
                ],
            },
        ],
    },
    {
        "filename": "meeting_notes.md",
        "title": "季度技术评审会议纪要",
        "complex": True,
        "sections": [
            {
                "heading": "会议信息",
                "paras": [
                    "会议于十月第二周周三下午两点召开, 参会人包括架构组、平台组与业务线研发负责人。",
                    "本次评审聚焦检索性能与存储成本两条主线, 共形成三项决议。",
                ],
                "tables": [],
            },
            {
                "heading": "决议事项",
                "paras": ["以下决议自会议当日起生效, 责任人需在两日内给出排期。"],
                # 小表: 定长切分也能存活
                "tables": [
                    [
                        ["序号", "决议", "责任人", "截止日期"],
                        ["1", "向量库索引参数调优", "张工", "10-20"],
                        ["2", "冷数据归档策略落地", "李工", "10-31"],
                        ["3", "检索评测集扩充至 45 题", "王工", "11-15"],
                    ]
                ],
            },
        ],
    },
    # ===================== Word(docx) + 表格 =====================
    {
        "filename": "contract.docx",
        "title": "技术服务合同(节选)",
        "complex": True,
        "sections": [
            {
                "heading": "第二条 服务内容",
                "paras": [
                    "乙方为甲方提供企业知识库系统的部署、调优与运维支持服务, 服务期为合同生效之日起十二个月。",
                    "乙方应在每个自然季度结束后十个工作日内提交服务报告, 报告需包含故障统计、性能指标与优化建议。",
                ],
                "tables": [],
            },
            {
                "heading": "第三条 付款节点",
                "paras": ["合同总价分三期支付, 各期比例与触发条件如下。"],
                # 长表 ~600 字符: 定长切分会被截断
                "tables": [
                    [
                        ["期次", "比例", "金额(元)", "触发条件", "付款时限"],
                        ["首期", "30%", "180000", "合同签订并开具发票", "15 个工作日"],
                        ["二期", "40%", "240000", "完成生产环境部署并通过验收", "15 个工作日"],
                        ["三期", "30%", "180000", "服务期满且无重大故障", "30 个工作日"],
                    ]
                ],
            },
            {
                "heading": "第四条 违约责任",
                "paras": [
                    "任何一方违约, 应向守约方支付违约金, 违约金按未履行部分金额的每日千分之五计算。",
                    "因不可抗力导致的延迟, 双方互不承担违约责任, 但应在事件发生后五日内书面通知对方。",
                ],
                "tables": [
                    [
                        ["违约情形", "责任方", "处理方式"],
                        ["延期交付超过 15 日", "乙方", "按日计罚, 上限为合同总额 10%"],
                        ["逾期付款超过 30 日", "甲方", "乙方可暂停服务"],
                    ]
                ],
            },
        ],
    },
    {
        "filename": "tech_spec.docx",
        "title": "检索服务技术规范",
        "complex": True,
        "sections": [
            {
                "heading": "1. 范围",
                "paras": [
                    "本规范定义检索服务的功能边界、性能基线与配置项, 适用于生产与预发两套环境。",
                ],
                "tables": [],
            },
            {
                "heading": "2. 配置项清单",
                "paras": [
                    "下表列出的配置项均支持环境变量覆盖, 修改后需重启服务生效, 变更需登记变更单。",
                ],
                # 20 行超大表 ~1100 字符: 必然被切碎
                "tables": [
                    [
                        ["配置项", "默认值", "取值范围", "说明"],
                        ["chunk_size", "600", "200-2000", "切分块大小(字符)"],
                        ["chunk_overlap", "80", "0-500", "切分重叠字符数"],
                        ["vector_top_k", "10", "1-100", "向量召回条数"],
                        ["bm25_top_k", "20", "1-200", "BM25 召回条数"],
                        ["rrf_k", "60", "1-100", "RRF 平滑常数"],
                        ["hybrid_fetch_k", "30", "1-200", "融合前单路召回上限"],
                        ["embedding_dim", "1024", "256-1536", "向量维度, 需与模型一致"],
                        ["embedding_model", "text-embedding-v3", "-", "嵌入模型名称"],
                        ["request_timeout_ms", "3500", "500-30000", "上游请求超时"],
                        ["max_upload_mb", "50", "1-200", "单文件上传上限"],
                        ["ocr_engine", "rapid", "rapid/paddle/mock", "OCR 引擎"],
                        ["text_density_threshold", "0.35", "0.05-0.95", "路由到 OCR 的密度阈值"],
                        ["index_rebuild_batch", "256", "32-1024", "索引重建批大小"],
                        ["cache_ttl_sec", "300", "0-3600", "检索结果缓存时长"],
                        ["log_level", "INFO", "DEBUG/INFO/WARN", "日志级别"],
                        ["enable_prefetch", "true", "true/false", "是否启用预检索"],
                        ["evidence_min_score", "0.02", "0-1", "证据采纳最低融合分"],
                        ["qa_log_retention_days", "90", "7-365", "问答日志保留天数"],
                        ["thread_max_turns", "20", "1-100", "单会话最大轮次"],
                    ]
                ],
            },
        ],
    },
    # ===================== PDF =====================
    {
        "filename": "q_report.pdf",
        "title": "第三季度经营分析报告",
        "complex": True,
        "sections": [
            {
                "heading": "一、整体经营情况",
                "paras": [
                    "第三季度公司实现营业收入一亿两千万元, 同比增长百分之十八, 环比增长百分之六。",
                    "毛利率为百分之六十二, 较上季度提升两个百分点, 主要得益于云资源成本优化与交付自动化。",
                    "研发投入占营业收入比例为百分之二十四, 同比提升三个百分点, 人员结构进一步向平台与算法倾斜。",
                ],
                "tables": [],
            },
            {
                "heading": "二、分业务线收入",
                "paras": [
                    "下表为三条业务线的收入与毛利情况, 数据口径与财务系统一致。",
                ],
                # PDF 中表格会被拍平成文本行, 结构化信息依赖阅读顺序
                "tables": [
                    [
                        ["业务线", "收入(万元)", "同比", "毛利率"],
                        ["企业软件", "6800", "+22%", "65%"],
                        ["行业解决方案", "3900", "+11%", "58%"],
                        ["运维托管", "1300", "+9%", "61%"],
                    ]
                ],
            },
            {
                "heading": "三、下季度重点",
                "paras": [
                    "下季度将重点推进知识库产品的行业化封装, 计划完成三个行业模板与两套交付工具链。",
                    "同时启动海外节点的灰度, 目标是在年底前完成新加坡区域的可用性验证。",
                ],
                "tables": [],
            },
        ],
    },
    {
        "filename": "policy.pdf",
        "title": "信息安全管理制度",
        "complex": False,
        "sections": [
            {
                "heading": "第一条 目的",
                "paras": [
                    "为规范公司信息资产的访问、使用与传输, 防范数据泄露风险, 特制定本制度。",
                    "本制度适用于全体员工、外包人员及第三方合作方。",
                ],
                "tables": [],
            },
            {
                "heading": "第二条 数据分级",
                "paras": [
                    "公司数据分为公开、内部、机密、绝密四级, 机密及以上数据禁止存储在个人设备与公共网盘。",
                    "绝密数据的访问需双人授权, 且所有操作必须留痕, 日志保留不少于一百八十天。",
                ],
                "tables": [],
            },
            {
                "heading": "第三条 账号与权限",
                "paras": [
                    "账号实行实名制, 禁止共享账号, 密码长度不少于十二位并每九十天更换一次。",
                    "离职人员账号应在离职当日禁用, 并在三个工作日内完成权限回收。",
                ],
                "tables": [],
            },
        ],
    },
    # ===================== 纯文本(对照组) =====================
    {
        "filename": "api_spec.txt",
        "title": "知识库检索 API 说明",
        "complex": False,
        "sections": [
            {
                "heading": "接口概览",
                "paras": [
                    "检索服务对外提供两个接口: 混合检索接口与流式问答接口。",
                    "混合检索接口为 POST /api/retrieval/debug, 请求体包含 query 与 top_k 两个字段, 返回按融合分降序排列的证据片段。",
                    "流式问答接口为 POST /api/agent/chat, 使用 SSE 协议逐 token 返回, 事件类型包括 meta、token、sources 与 done。",
                ],
                "tables": [],
            },
            {
                "heading": "鉴权与限流",
                "paras": [
                    "所有接口需要携带 Bearer Token, Token 由网关统一签发, 有效期两小时。",
                    "单租户默认限流为每分钟六百次请求, 超出后返回 429 状态码并在响应头中给出重试等待秒数。",
                    "批量导入接口单独限流, 阈值为每分钟二十次, 避免影响在线检索的稳定性。",
                ],
                "tables": [],
            },
        ],
    },
    {
        "filename": "faq.txt",
        "title": "知识库产品常见问题",
        "complex": False,
        "sections": [
            {
                "heading": "使用相关",
                "paras": [
                    "问: 支持哪些文档格式? 答: 支持 PDF、Word、Markdown 与纯文本, 扫描件与图片型 PDF 会走 OCR 链路。",
                    "问: 单个文件最大多大? 答: 默认五十兆, 可通过 max_upload_mb 配置项调整, 上限两百兆。",
                    "问: 上传后多久可以检索? 答: 文档入库是同步完成的, 通常十秒内即可检索到, 超大文档会稍慢。",
                ],
                "tables": [],
            },
            {
                "heading": "效果相关",
                "paras": [
                    "问: 为什么表格内容检索不到? 答: 请确认表格已被识别为受保护块, 若为扫描件请检查 OCR 是否启用。",
                    "问: 回答没有引用来源怎么办? 答: 检查证据裁判阈值 evidence_min_score, 阈值过高会导致证据被过滤。",
                ],
                "tables": [],
            },
        ],
    },
    # ===================== 扫描件(图片 -> OCR 链路) =====================
    {
        "filename": "scan_form.png",
        "title": "纸质登记表扫描件",
        "complex": True,
        "sections": [
            {
                "heading": "扫描件说明",
                "paras": [
                    "本文件为纸质表单的扫描件, 无文本层, 必须走 OCR 链路才能提取内容。",
                ],
                "tables": [],
            },
        ],
    },
    {
        "filename": "scan_invoice.png",
        "title": "发票扫描件",
        "complex": True,
        "sections": [
            {
                "heading": "扫描件说明",
                "paras": [
                    "本文件为发票扫描件, 图像型, 需 OCR 识别票面字段。",
                ],
                "tables": [],
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# QA 测评集
# ---------------------------------------------------------------------------
# type  = keyword  : 精确词面问题(字段名 / 编号 / 配置项 / 阈值), 考察 BM25 补足能力
#         semantic : 自然语言改写问题(不出现原文精确词), 考察向量语义召回能力
# key   = 唯一关键串, 命中该 chunk 即判为召回正确(单一正解, 故 Hit@k 等价 Recall@k)
# ---------------------------------------------------------------------------

QA: list[dict] = [
    # ---------- keyword: 字段名 / 编号 / 配置项 ----------
    {"q": "员工档案里工号的格式要求是什么", "key": "EB-2024-0001", "type": "keyword", "doc": "handbook.md"},
    {"q": "身份证号字段应该怎么存储", "key": "需加密存储", "type": "keyword", "doc": "handbook.md"},
    {"q": "工资卡号字段的展示要求", "key": "需脱敏展示", "type": "keyword", "doc": "handbook.md"},
    {"q": "职级字段的取值有哪些", "key": "P1 至 P9", "type": "keyword", "doc": "handbook.md"},
    {"q": "部门编码的示例是什么", "key": "D-ENG-01", "type": "keyword", "doc": "handbook.md"},
    {"q": "试用期结束日默认多少天", "key": "入职后 90 天", "type": "keyword", "doc": "handbook.md"},
    {"q": "成本中心字段的类型和长度", "key": "cost_center", "type": "keyword", "doc": "handbook.md"},
    {"q": "status 字段 1 和 2 分别代表什么", "key": "1 在职 2 离职", "type": "keyword", "doc": "handbook.md"},
    {"q": "渠道折扣打到 75% 需要谁审批", "key": "销售副总裁", "type": "keyword", "doc": "pricing.md"},
    {"q": "70% 及以下的折扣审批要求", "key": "战略价值说明", "type": "keyword", "doc": "pricing.md"},
    {"q": "标准版 51 到 200 坐席的单价", "key": "169", "type": "keyword", "doc": "pricing.md"},
    {"q": "三年一次性付费的折扣", "key": "七五折", "type": "keyword", "doc": "pricing.md"},
    {"q": "request_timeout_ms 的默认值和范围", "key": "3500", "type": "keyword", "doc": "tech_spec.docx"},
    {"q": "rrf_k 配置项是什么含义", "key": "RRF 平滑常数", "type": "keyword", "doc": "tech_spec.docx"},
    {"q": "evidence_min_score 默认值", "key": "0.02", "type": "keyword", "doc": "tech_spec.docx"},
    {"q": "text_density_threshold 的作用", "key": "路由到 OCR 的密度阈值", "type": "keyword", "doc": "tech_spec.docx"},
    {"q": "max_upload_mb 上限可以设到多少", "key": "上限两百兆", "type": "keyword", "doc": "faq.txt"},
    {"q": "qa_log_retention_days 的取值范围", "key": "7-365", "type": "keyword", "doc": "tech_spec.docx"},
    {"q": "混合检索接口的路径和请求字段", "key": "/api/retrieval/debug", "type": "keyword", "doc": "api_spec.txt"},
    {"q": "流式问答接口的事件类型有哪些", "key": "meta、token、sources", "type": "keyword", "doc": "api_spec.txt"},
    {"q": "逾期付款超过 30 日会怎样", "key": "乙方可暂停服务", "type": "keyword", "doc": "contract.docx"},
    {"q": "违约金按什么比例计算", "key": "每日千分之五", "type": "keyword", "doc": "contract.docx"},
    {"q": "首期付款比例和金额", "key": "30%", "type": "keyword", "doc": "contract.docx"},
    {"q": "三期付款的触发条件", "key": "服务期满且无重大故障", "type": "keyword", "doc": "contract.docx"},
    {"q": "生产发布权限由谁审批", "key": "研发总监", "type": "keyword", "doc": "onboarding.md"},
    {"q": "数据库只读权限的开通时限", "key": "2 工作日", "type": "keyword", "doc": "onboarding.md"},
    {"q": "账号密码多久更换一次", "key": "每九十天", "type": "keyword", "doc": "policy.pdf"},
    {"q": "绝密数据日志保留多少天", "key": "一百八十天", "type": "keyword", "doc": "policy.pdf"},
    {"q": "离职人员账号什么时候禁用", "key": "离职当日", "type": "keyword", "doc": "policy.pdf"},
    {"q": "单租户默认限流每分钟多少次", "key": "六百次", "type": "keyword", "doc": "api_spec.txt"},
    # ---------- semantic: 自然语言改写, 不出现原文精确词 ----------
    {"q": "新同事来报到以后要办哪些手续", "key": "提交材料、签订协议、开通账号、参加培训", "type": "semantic", "doc": "handbook.md"},
    {"q": "请假的年假天数跟工作年限怎么挂钩", "key": "满五年十五天", "type": "semantic", "doc": "handbook.md"},
    {"q": "生病请假需要准备什么证明材料", "key": "二级以上医疗机构证明", "type": "semantic", "doc": "handbook.md"},
    {"q": "如果培训考试没过怎么办", "key": "补训一次", "type": "semantic", "doc": "handbook.md"},
    {"q": "买的人多单价会更便宜吗", "key": "119", "type": "semantic", "doc": "pricing.md"},
    {"q": "老客户第二年续约能便宜多少", "key": "95%", "type": "semantic", "doc": "pricing.md"},
    {"q": "给客户打折太多会不会影响利润考核", "key": "毛利不得低于 45%", "type": "semantic", "doc": "pricing.md"},
    {"q": "远程办公怎么连公司内网", "key": "内网 VPN", "type": "semantic", "doc": "onboarding.md"},
    {"q": "代码合并到主干前要走什么流程", "key": "Code Review", "type": "semantic", "doc": "onboarding.md"},
    {"q": "开会定下来的检索调优谁来负责", "key": "张工", "type": "semantic", "doc": "meeting_notes.md"},
    {"q": "评测集要扩到多少题", "key": "45 题", "type": "semantic", "doc": "meeting_notes.md"},
    {"q": "这个季度收入同比涨了多少", "key": "百分之十八", "type": "semantic", "doc": "q_report.pdf"},
    {"q": "毛利提升主要靠什么", "key": "云资源成本优化", "type": "semantic", "doc": "q_report.pdf"},
    {"q": "哪块业务毛利最高", "key": "企业软件", "type": "semantic", "doc": "q_report.pdf"},
    {"q": "公司打算往海外发展吗", "key": "新加坡", "type": "semantic", "doc": "q_report.pdf"},
    {"q": "研发花了多少钱占比多少", "key": "百分之二十四", "type": "semantic", "doc": "q_report.pdf"},
    {"q": "服务期满没有大故障那笔钱怎么付", "key": "180000", "type": "semantic", "doc": "contract.docx"},
    {"q": "碰到天灾导致延期要不要赔钱", "key": "不可抗力", "type": "semantic", "doc": "contract.docx"},
    {"q": "传上去的文件多久能被搜到", "key": "十秒内", "type": "semantic", "doc": "faq.txt"},
    {"q": "回答没有给出引用该怎么排查", "key": "evidence_min_score", "type": "semantic", "doc": "faq.txt"},
    {"q": "上传的文件大小有什么限制", "key": "默认五十兆", "type": "semantic", "doc": "faq.txt"},
]


def complex_docs() -> list[dict]:
    """返回复杂文档(计入入库成功率分母)。"""
    return [d for d in DOCS if d.get("complex")]


def all_table_specs(doc: dict) -> list[list[list[str]]]:
    """抽取某文档的全部表格(二维数组列表)。"""
    out: list[list[list[str]]] = []
    for sec in doc["sections"]:
        out.extend(sec.get("tables") or [])
    return out


def doc_plain_text(doc: dict) -> str:
    """把文档所有文字(含表格单元格)拍平为一个字符串, 供 QA key 断言使用。"""
    parts: list[str] = [doc.get("title", "")]
    for sec in doc["sections"]:
        parts.append(sec.get("heading", ""))
        parts.extend(sec.get("paras") or [])
        for tbl in sec.get("tables") or []:
            for row in tbl:
                parts.extend(row)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 规模化干扰语料 (deterministic, 固定生成, 保证可复现)
# ---------------------------------------------------------------------------
# 仅有 12 篇文档时, 索引只有二十来个 chunk, Hit@5 会饱和(几乎谁都能全中), 测评失去区分度。
# 真实企业知识库里往往是"几十篇结构几乎一样的制度文件", 差别只在部门/年度/金额上 ——
# 这才是"标题词、字段名命中不稳"的真实场景。因此这里按固定规则生成干扰语料:
#   · 差旅政策: 10 个部门 × 3 个年度 = 30 篇, 版式完全相同, 只有部门/年度/金额不同
#   · 技术服务合同: 20 个客户 = 20 篇, 只有客户名/合同编号不同
# 所有关键值(文号 / 金额)按公式构造为全局唯一, 避免"关键串撞车"造成假命中。

_DEPTS = ["研发", "市场", "销售", "财务", "人力", "法务", "运营", "客服", "供应链", "设计"]
_YEARS = ["2022", "2023", "2024"]
_CLIENTS = ["恒远科技", "锐达数据", "云启智能", "博晟软件", "天工机械", "联信网络", "华洋物流",
            "中科微电", "远东能源", "盛元传媒", "凯盛医疗", "朗新环保", "金鼎建材", "海川航运",
            "同辉电子", "长兴材料", "万通地产", "瑞丰农业", "新元教育", "合力装备"]


def _travel_doc(di: int, dept: str, yi: int, year: str) -> dict:
    k = di * 3 + yi
    code = f"TRV-{year}-D{di + 1:02d}"
    t1 = 520 + k * 100          # 一线
    t2 = t1 - 60                # 二线
    t3 = t1 - 120               # 三线
    meal = 80 + k * 5
    return {
        "filename": f"travel_{year}_d{di + 1:02d}.md",
        "title": f"{dept}部差旅报销标准({year} 年度)",
        "complex": True,
        "generated": True,
        "sections": [
            {
                "heading": "一、总则",
                "paras": [
                    f"为规范{dept}部员工因公出差的开支管理, 依据公司差旅管理制度制定本标准。",
                    f"本标准文号为 {code}, 自 {year} 年 1 月 1 日起执行, 适用于{dept}部全体在职员工及实习生。",
                    "出差前须在协同系统提交申请, 经直属主管审批后生效; 未审批产生的费用不予报销。",
                ],
                "tables": [],
            },
            {
                "heading": "二、报销标准",
                "paras": [
                    "住宿费按出差城市的等级分档限额, 超出限额部分由个人承担; 餐补按自然日计算, 无需提供票据。",
                ],
                "tables": [
                    [
                        ["城市等级", "住宿上限", "餐补标准", "市内交通"],
                        ["一线城市", f"{t1} 元/晚", f"{meal} 元/天", "实报实销"],
                        ["二线城市", f"{t2} 元/晚", f"{meal - 20} 元/天", "实报实销"],
                        ["三线城市", f"{t3} 元/晚", f"{meal - 40} 元/天", "实报实销"],
                    ]
                ],
            },
            {
                "heading": "三、报销流程",
                "paras": [
                    "出差结束后十个工作日内提交报销单, 需附发票原件、行程单与审批记录, 缺件将退回补正。",
                    "财务部在收到完整材料后五个工作日内完成审核, 审核通过的费用随当月工资一并发放。",
                    "对审核结果有异议的, 可在结果通知后三个工作日内向财务部发起复核申请。",
                ],
                "tables": [],
            },
        ],
    }


def _contract_doc(ci: int, client: str) -> dict:
    code = f"CT-2024-C{ci + 1:02d}"
    total = 300000 + ci * 25000
    first = total * 3 // 10
    return {
        "filename": f"contract_c{ci + 1:02d}.md",
        "title": f"技术服务合同({client})",
        "complex": True,
        "generated": True,
        "sections": [
            {
                "heading": "第一条 服务内容",
                "paras": [
                    f"甲方 {client} 委托乙方提供企业知识库系统的部署、调优与运维支持服务。",
                    f"本合同编号 {code}, 服务期为合同生效之日起十二个月, 服务范围以附件一的服务清单为准。",
                    "乙方应在每季度结束后十个工作日内提交服务报告, 报告需包含故障统计与性能指标。",
                ],
                "tables": [],
            },
            {
                "heading": "第二条 付款条款",
                "paras": [
                    "合同总价分三期支付, 各期比例与触发条件如下表; 所有款项均以人民币结算并开具增值税专用发票。",
                ],
                "tables": [
                    [
                        ["期次", "比例", "金额(元)", "触发条件"],
                        ["首期", "30%", f"{first}", "合同签订并开具发票"],
                        ["二期", "40%", f"{total * 4 // 10}", "部署完成并通过验收"],
                        ["三期", "30%", f"{total * 3 // 10}", "服务期满且无重大故障"],
                    ]
                ],
            },
            {
                "heading": "第三条 其他约定",
                "paras": [
                    "任何一方违约, 应向守约方支付违约金, 违约金按未履行部分金额的每日千分之五计算。",
                    "因不可抗力导致的延迟, 双方互不承担违约责任, 但应在事件发生后五日内书面通知对方。",
                    "合同履行中发生争议的, 双方应先行协商; 协商不成的, 提交合同签订地人民法院管辖。",
                ],
                "tables": [],
            },
        ],
    }


def _build_scaled() -> tuple[list[dict], list[dict]]:
    docs: list[dict] = []
    for di, dept in enumerate(_DEPTS):
        for yi, year in enumerate(_YEARS):
            docs.append(_travel_doc(di, dept, yi, year))
    for ci, client in enumerate(_CLIENTS):
        docs.append(_contract_doc(ci, client))

    qa: list[dict] = []
    # 每个部门取 2024 年度的政策: 关键词型(金额/文号) + 语义型(换一种说法问)
    for di, dept in enumerate(_DEPTS):
        k = di * 3 + 2
        t1 = 520 + k * 100
        meal = 80 + k * 5
        qa.append({
            "q": f"{dept}部 2024 年一线城市出差住宿上限是多少",
            "key": f"{t1} 元/晚", "type": "keyword",
            "doc": f"travel_2024_d{di + 1:02d}.md",
        })
        qa.append({
            "q": f"{dept}部 2024 年度差旅政策文号",
            "key": f"TRV-2024-D{di + 1:02d}", "type": "keyword",
            "doc": f"travel_2024_d{di + 1:02d}.md",
        })
    for di, dept in enumerate(_DEPTS[:5]):
        k = di * 3 + 2
        meal = 80 + k * 5
        qa.append({
            "q": f"{dept}的同事 2024 年去二线城市出差, 每天吃饭补贴能报多少",
            "key": f"{meal - 20} 元/天", "type": "semantic",
            "doc": f"travel_2024_d{di + 1:02d}.md",
        })
    # 合同: 前 10 家问编号(关键词型), 后 5 家换口语问法(语义型)
    for ci, client in enumerate(_CLIENTS[:10]):
        qa.append({
            "q": f"和{client}签的技术服务合同编号是多少",
            "key": f"CT-2024-C{ci + 1:02d}", "type": "keyword",
            "doc": f"contract_c{ci + 1:02d}.md",
        })
    for ci in range(10, 15):
        client = _CLIENTS[ci]
        qa.append({
            "q": f"帮我找一下{client}那份技术服务合同的文号",
            "key": f"CT-2024-C{ci + 1:02d}", "type": "semantic",
            "doc": f"contract_c{ci + 1:02d}.md",
        })
    return docs, qa


_SCALED_DOCS, _SCALED_QA = _build_scaled()
DOCS.extend(_SCALED_DOCS)
QA.extend(_SCALED_QA)

# curated=True 表示"手工编写、格式多样"的测评基准文档(前 12 篇)。
# 入库质量只在这批文档上统计 —— 50 篇模板化近重复文档的成败高度一致,
# 把它们计入分母等于把同一条结论重复 50 次, 反而稀释信号。
for _d in DOCS:
    _d.setdefault("curated", not _d.get("generated", False))

