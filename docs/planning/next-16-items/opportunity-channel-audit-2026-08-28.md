# 招聘渠道逐条核验记录（2026-08-28）

## 范围与结论

输入文件为 `/home/Temp/增强企业渠道2026-08-28.csv`（SHA-256：`5e8f6febb52554ba00d326adc2021b395ce49a0e93fa3a3bc5fd0df8f8232a5e`）。文件共有 873 行、844 个唯一 URL、395 个企业名称；其中 41 行标记为“官方页面已确认”，832 行仍是“官方候选待打开”，覆盖 369 家企业和 803 个唯一候选 URL。“疑似职位列表”有 118 行，其余 755 行是入口/结构待确认。21 条可执行来源只是首批已完成结构化核验的子集，不代表候选文档的总量。

本轮采用保守准入：只有同时满足“官方域名或官方 ATS 租户、公开可访问、确实存在职位列表、能够读到结构化岗位字段、无需登录/凭据”才进入可执行来源清单。主页、宣传页、单个职位详情、PDF、第三方汇总页、登录页和无法稳定读回结构化列表的页面不注册为爬虫来源。

候选记录按官方主机的初步平台族分组如下；这只是批处理顺序，不代表尚未打开的链接已经被判定为非职位列表。

| 初步平台族 | 候选记录 | 企业数 | 唯一 URL |
| --- | ---: | ---: | ---: |
| 北森 `zhiye.com` | 115 | 64 | 113 |
| 飞书 `jobs.feishu.cn` | 38 | 25 | 38 |
| 大易 `hotjob.cn` | 35 | 23 | 34 |
| 平安招聘域 | 25 | 9 | 12 |
| 哈哈招聘 | 24 | 22 | 24 |
| 中公/地方招聘平台 | 9 | 9 | 9 |
| 厦门大学嘉庚/校园平台 | 7 | 7 | 7 |
| 其他企业自建站或平台 | 579 | 304 | 566 |

平台族统计来自 832 条候选记录的主机归一化；同一企业出现在多个平台时分别计入各组，不能把各组企业数相加作为总企业数。

可执行新增来源写入 [`config/opportunity_sources.additions-2026-08-28.v1.json`](../../../config/opportunity_sources.additions-2026-08-28.v1.json)，第二批写入 [`config/opportunity_sources.additions-2026-08-28.batch-02.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-02.json)，第三批写入 [`config/opportunity_sources.additions-2026-08-28.batch-03.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-03.json)，第四批写入 [`config/opportunity_sources.additions-2026-08-28.batch-04.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-04.json)，第五批写入 [`config/opportunity_sources.additions-2026-08-28.batch-05.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-05.json)，第六批写入 [`config/opportunity_sources.additions-2026-08-28.batch-06.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-06.json)，第七批写入 [`config/opportunity_sources.additions-2026-08-28.batch-07.json`](../../../config/opportunity_sources.additions-2026-08-28.batch-07.json)，第八批写入 [`config/opportunity_sources.additions-2026-08-29.batch-08.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-08.json)，第九批写入 [`config/opportunity_sources.additions-2026-08-29.batch-09.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-09.json)，第十批写入 [`config/opportunity_sources.additions-2026-08-29.batch-10.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-10.json)，第十一批写入 [`config/opportunity_sources.additions-2026-08-29.batch-11.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-11.json)，第十二批写入 [`config/opportunity_sources.additions-2026-08-29.batch-12.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-12.json)，第十三批写入 [`config/opportunity_sources.additions-2026-08-29.batch-13.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-13.json)，第十四批写入 [`config/opportunity_sources.additions-2026-08-29.batch-14.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-14.json)，第十五批写入 [`config/opportunity_sources.additions-2026-08-29.batch-15.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-15.json)，第十六批写入 [`config/opportunity_sources.additions-2026-08-29.batch-16.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-16.json)，第十七批写入 [`config/opportunity_sources.additions-2026-08-29.batch-17.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-17.json)，第十八批写入 [`config/opportunity_sources.additions-2026-08-29.batch-18.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-18.json)。当前已批准 68 个来源（首批 21 个、第二批北森 2 个、第三批北森 4 个、第四批北森 1 个、第五批北森 1 个、第六批北森 1 个、第七批北森 1 个、第八批北森 2 个、第九批北森 1 个、第十批北森 2 个、第十一批 5 个、第十二批 4 个、第十三批 4 个、第十四批 2 个、第十五批 2 个、第十六批 1 个、第十七批 1 个、第十八批北森 13 个）：5 个 Moka、14 个 Hotjob、2 个 Feishu、47 个 Beisen。十八个清单都是增量清单，不会重置已有来源状态；832 条候选记录仍以逐 URL 状态表为审计总范围，不能用已批准来源数直接相减推导剩余记录。需要管理员在 Labs 明确授权后执行导入命令。

统计修订（截至 2026-08-29 第四十二批）：在首批至第十八批历史段落之后又完成第二十至第四十二批，当前已批准 109 个来源（9 个 Moka、18 个 Hotjob、26 个 Feishu、56 个 Beisen），对应 42 个增量清单；“尚未导入 Labs”仅是本段形成时的历史状态，当前状态以文末“合并导入记录”为准。

## 本轮范围裁决（2026-08-29）

Labs 当前找工作模块读回为 41 条来源、31 家企业。为避免重复处理，以下已有企业不再进入本轮核验：DeepSeek、Rokid、e签宝、中控技术、京东、华为、吉利控股/极氪、大华股份、字节跳动、宇树科技、安恒信息、小米集团、强脑科技、恒生电子、新华三、有赞、杭州银行、每日互动、浙商银行、海康威视、涂鸦智能、网易、网易互娱、网易雷火、美团、腾讯、蚂蚁集团、连连数字、迪普科技、酷家乐和阿里巴巴集团。

本轮优先完成且随后停止其余候选的企业批次为：哔哩哔哩、小红书、米哈游、安克创新、比亚迪、vivo、中芯国际、顺丰集团、NVIDIA、荣耀。每家企业先逐条核对候选 URL，合并 canonical/重复入口，仅将公开、无需登录、字段和分页闭合的官方职位列表登记为新增来源；详情页、登录页、宣传页和第三方页面只记录处置，不注册。禾赛、小鹏、思朗、原力灵机、森麒麟、去哪儿、锐石、马上消费、雷鸟、发那科、利欧等已完成的新增来源不重复验证，作为本轮已闭合结果保留。

最终导入找工作模块时，必须合并首批至当前所有已完成增量清单与本轮优先企业新清单，按规范化 canonical URL 和 UUID 去重；不得只导入最后一个批次，也不得覆盖或重置既有来源状态。

完成上述十家企业后，剩余候选企业停止主动扫描；未核验 URL 继续留在 CSV 审计范围，不伪造为 0 岗位，也不自动加入来源清单。

## 已准入来源

| 企业 | 来源类型 | 适配器 | 公开列表证据 |
| --- | --- | --- | --- |
| 德州仪器 | 校园招聘 | `moka-v1` | Moka API，68 条 |
| 微博 | 校园招聘 | `moka-v1` | Moka API，可分页 |
| 滴滴 | 校园招聘 | `moka-v1` | 短链解析到官方租户，Moka API，159 条 |
| 乐元素科技 | 校园招聘 | `moka-v1` | 申请入口解析为公开校园租户，Moka API，33 条 |
| 电科金仓 | 校园招聘 | `moka-v1` | 短链解析到官方租户，Moka API |
| 天翼云科技 | 校园招聘 | `hotjob-v1` | Hotjob `listPosition`，42 条 |
| 双环传动 | 社会招聘 | `hotjob-v1` | Hotjob `listPosition`，100 条 |
| 长光卫星 | 校园招聘 | `hotjob-v1` | Hotjob `listPosition`，15 条 |
| 三棵树 | 实习招聘 | `hotjob-v1` | Hotjob `listPosition`，42 条 |
| 宝时得科技 | 官方综合招聘 | `hotjob-v1` | 校招/社会接口均可读，39/108 条 |
| 安信证券 | 官方综合招聘 | `hotjob-v1` | 官方别名解析租户，校招/社会接口可读 |
| 大众汽车（中国）投资有限公司 | 官方综合招聘 | `hotjob-v1` | Hotjob 官方租户，19/171 条 |
| 格科 | 官方综合招聘 | `hotjob-v1` | Hotjob 官方租户，37/148 条 |
| 新城控股上海分公司 | 官方综合招聘 | `hotjob-v1` | Hotjob 官方租户，实习/社会接口可读 |
| 深圳创维-RGB | 校园招聘 | `hotjob-v1` | Hotjob `listPosition`，106 条 |
| 中国民航信息网络嘉兴分公司 | 官方综合招聘 | `hotjob-v1` | Hotjob 官方租户，92/81 条 |
| 地平线 | 官方综合招聘 | `hotjob-v1` | 官方校园域解析租户，90/271 条 |
| 天风证券 | 社会招聘 | `hotjob-v1` | Hotjob `listPosition`，13 条 |
| 华泰证券 | 官方综合招聘 | `hotjob-v1` | Hotjob 综合入口，社会接口可读 |
| Fastlane | 校园招聘 | `feishu-career-v1` | 受限 Chrome 沙箱读回 14 条 |
| 莉莉丝游戏 | 校园招聘 | `feishu-career-v1` | 受限 Chrome 沙箱读回岗位列表 |

第二至四批新增的北森来源：诺瓦星云实习（1 条/1 页）、诺瓦星云社会（96 条/20 页）、广东奥马冰箱（29 条/6 页）、华夏航空（5 条/1 页）、中茵微电子（13 条/3 页）、杰华特微电子（26 条/6 页）和三未信安（9 条/2 页）。它们均为公开列表的完整分页读回，绑定现有 `beisen-zhiye-v1`。 第八批核验批准亿道信息（3 页 15 条，含 2027 届）和方正微电子（7 页 32 条，届别为空）；春风动力、英维克在第一阶段仍未完成，杰克股份为旧版模板，暂留待补全。

第五批核验同时检查了 `sigmastar1.zhiye.com/campus/jobs`：其 31 个岗位 ID 与 canonical 租户 100% 重合，因此记录为重复镜像，不再创建第二个来源。

第六批核验批准新芯（10 页 50 条，含 2027 届）；苏纳光电在当时的页数窗口内仍未完成，后续第十八批已用 `page_size=100` 完整读回。 第七批核验批准鸣石私募（1 页 5 条，含 2027 届）；新华三在当时的页数窗口内仍未完成，后续第十八批已完整读回。 第九批核验批准杰克股份旧版列表（3 页 35 条）；中国电信云计算和恒生电子旧镜像分别因当前 0 条/2023 旧岗位且已有对应来源，记录为重复或过期镜像，不入库。 第十批核验批准海栎创科技（1 页 5 条）和浩鲸科技（8 页 38 条）；科大讯飞后续第十七批已完整读回。 第十一批核验批准金山云（1 页 1 条，2027 届）、慧策（14 页 70 条，旧届别）、货拉拉（1 页 0 条）、龙旗科技（1 页 0 条）和锦浪科技（5 页 25 条，2027 届）。 第十二批核验批准基恩士（1 页 1 条）、星纵物联（3 页 15 条，2027 届）、迈瑞医疗校园（2 页 10 条）和新能德（9 页 43 条）；昆仑芯仍为非标准模板，暂留待适配。 第十三批核验批准豪威集团（16 页 78 条，2027 届）、上海精测（5 页 25 条，2027 届）、前海开源（4 页 16 条，旧届别）和四方继保（10 页 48 条，2026 届）；睿创微纳后续第十八批已完整读回。 第十四批核验批准欣旺达实习（1 页 1 条）和洲明科技校园（6 页 29 条，2027 届）；传音控股、天职国际、万兴科技后续第十八批已完整读回。 第十五批核验批准康尼机电（5 页 21 条，2027 届）和芯动科技（4 页 20 条，2027 届）。 第十六批核验批准春风动力（41 页 205 条，2027 届）。 第十七批核验批准科大讯飞综合列表（18 页 895 条，page_size=50；2027/2028 届字段，无法判定的岗位类型保留 OTHER）。第十八批核验批准苏纳光电（校园 41 条/1 页、综合 165 条/2 页）、新华三（综合 371 条/4 页、社会 295 条/3 页）、睿创微纳（校园 63 条/1 页、综合 270 条/3 页）、传音控股（校园 178 条/2 页、综合 969 条/10 页）、天职国际（综合 467 条/5 页、校园 110 条/2 页）和万兴科技（社会 39 条/1 页、校园综合 141 条/2 页、实习 110 条/2 页）。所有页面使用 `page_size=100` 完整闭合，综合页可能与其专属招聘页有岗位重叠，保留为不同官方入口并由来源字段区分。

第十九批核验批准欣旺达（综合 502 条/6 页、校园综合 1,253 条/13 页、实习列表明确 0 条/1 页）、恒玄科技（综合 85 条/1 页）和一鸣食品（综合 169 条/2 页）。所有页面使用 `page_size=100` 完整闭合；明确为空的实习列表仍保留为可监测来源，不伪造岗位。

第二十批核验批准思摩尔国际（Moka 校园 12 条/1 页）、巨一（Hotjob 校园 1 条/1 页、综合 10 条/2 页）、宇通集团（Hotjob 综合 79 条/7 页）和浙江长龙航空（Hotjob 综合 87 条/7 页）。长龙首次接口返回的第一页分页元数据与后页不一致，适配器诚实拒绝；只有后续完整重试的每页总数和总页数一致后才批准。

第二十一批核验批准海信集团（北森校园 475 条/5 页、综合 1,204 条/13 页）和华勤技术（官网链接指向的 Moka 校园 52 条/2 页、社会 48 条/2 页、实习 69 条/3 页）。华勤实习列表中 68 条为实习、1 条为校园大使，按公开接口字段保留混合招聘类型。

所有准入适配器都保留来源发布时间（Moka/Hotjob/Feishu/Beisen 对应公开字段，缺失时保持为空），并使用现有来源 allowlist、robots、速率、页数、岗位数和 600 秒上限。没有使用管理员 CSS/XPath/脚本配置，也没有访问投递接口。

## 适配器变更

- `hotjob-v1`：新增大易公开租户列表适配器。只接受有限的 Hotjob 租户路径，按 `recruitType` 分页读取，解析岗位 ID、名称、计划、地点、类别、届别和 `publishDate`；综合入口去重同一岗位，不把空结果伪装成异常。
- `beisen-zhiye-v1`：在原有 BSGlobal API 分支外增加旧版 `jobsTable/listtable` 服务端列表解析，跟随同域分页链接并校验总数；没有明确职位表或分页证据时仍拒绝。
- `feishu-career-v1`：新增受限 Feishu 招聘浏览器适配器。来源 host 为固定白名单，页面通过公开 `search/job/posts` 请求取得岗位；浏览器运行时只允许当前租户与已知静态资源域名，禁止任意管理员 host。
- 共享浏览器协议：允许一个固定适配器对应多个已审核租户 host，并保持每次请求的来源 host 与 `allowed_hosts` 一致；既有 Alibaba、字节、小米、海康适配器契约不变。
- Moka 大响应：公开职位加密响应使用既有 `MAX_ADAPTER_RESPONSE_BYTES`，避免 30 条岗位正文在默认 64 KiB 限制下被截断。

## 其余 URL 的逐条处置规则

CSV 中每个唯一 URL 均按下列互斥结果之一记录；原始行中的企业、URL、页面核验状态和证据仍是审计输入，不在系统中复制响应正文。

| 处置 | 数量（唯一 URL） | 说明 |
| --- | ---: | --- |
| 已准入并写入增量清单 | 109 | 截至第四十二批，已完成结构化接口/沙箱读回；早期 55 为历史快照 |
| 平台候选，待补充官方列表证据 | 约 170 | 主要是 `*.zhiye.com`、其他 Feishu/Hotjob/Moka 租户；入口存在不等于列表可采集 |
| 普通官网或静态招聘页 | 约 216 | 需要每个站点独立字段契约，不能使用通用 HTML fallback |
| 入口/主页/宣传页 | 约 152 | 无稳定职位列表或仅提供导航 |
| 职位详情、公告、新闻、企业介绍 | 约 120 | 不是来源列表；详情只能作为岗位链接，不作为采集入口 |
| 登录、个人中心或要求会话 | 10 | 按项目裁决标记暂不支持，不保存 Cookie/storage state |
| 非 HTTPS | 58 | 来源模型拒绝；必须由官方站点提供 HTTPS 后重新核验 |
| PDF/图片等文件 | 2 | 不是结构化岗位列表，保留为人工参考 |
| 无法确定页面类型 | 约 95 | 需要企业方或管理员提供明确官方列表页后再核验 |

数量为按 URL 去重后的审计分组摘要（平台候选与普通官网等分组存在少量路径规则边界，故以“约”表示）；精确逐行证据以输入 CSV 的 873 行和上方 hash 为准，重复 URL 不会重复注册。

## 明确暂不适配的代表性来源

- 小红书、华宝新能、诺瓦星云、三星等页面在本机只读探针返回 403/安全拦截；没有把 403 当成“0 岗位”。
- 江瀚新材等页面把岗位放在图片或公告中，需要 OCR/人工确认，当前不满足结构化采集契约。
- `*.jobs.feishu.cn` 的大量行是单个职位详情、登录页或租户首页；只有已列入批次清单且完成受限浏览器读回的租户才批准，其余仍保持待核验。
- `*.zhiye.com` 的大量行虽然形状像 `/campus/jobs`，但本轮公开 HTTP 读回被 BeiSen 防护拦截；在没有受控浏览器证据前不批量启用。
- Oracle/SAP、企业自建站及招聘聚合平台没有统一公开协议；不得用通用 Playwright 或猜测 API 作为 fallback。

## 验证记录

- Hotjob：使用受限 `curl`/公开 `listPosition` GET，只读首层分页和字段摘要；未提交简历、未登录。
- Feishu：使用 `/usr/local/bin/blog-playwright-cli` 与独立 `blog-browser` 沙箱核验 Fastlane；浏览器 collector 实际返回 `complete=true`、`pages_read=2`、14 个岗位。莉莉丝公开校园列表也返回结构化岗位。
- 代码聚焦回归：Hotjob/Feishu Python 测试 `11 passed`；Node 浏览器契约 `5 passed`；Python 编译、Ruff/format 目标文件、Django `check`、`node --check` 和 `git diff --check` 均退出 0。来源清单管理命令 dry-run 返回 `sources=21`，解析读回为 21 个唯一 URL，三个适配器均已注册且官方 URL 主机均在 allowlist 内。
- 来源清单测试中 4 个需要 Django 测试数据库的用例在默认 SQLite 初始化阶段被项目既有 PostgreSQL 专用迁移（`ALTER TABLE ... ADD CONSTRAINT`）阻断；同一批次其余 27 个适配器/浏览器/服务用例通过。该环境问题未被归因于本轮适配器，也未通过切换共享数据库绕过。
- 清单中的 Moka 入口已去除不参与采集的 `sourceToken` 追踪参数；当前 shell 未加载 Labs 数据库环境，来源 UUID/URL 冲突读回落到空 SQLite 并因缺少 `opportunity_source` 表失败，未因此执行迁移或写库。
- 受限环境中部分后续浏览器探针因低内存/上游等待被停止；这些来源没有被标记为成功，也没有写入数据库。
- 北森候选的第一阶段页面可达性探测覆盖 113 个唯一 URL，全部返回 HTTP 200：99 个新版 `BSGlobal` 模板、11 个旧版服务器渲染模板、3 个其他模板。该结果只证明页面可达和模板分布，不代表 113 个链接都已完成岗位接口分页或数量校验。

## 下一步

统计修订（2026-08-29，第十九批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-19.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-19.json) 的 5 个北森来源后，累计已批准 73 个来源（5 个 Moka、14 个 Hotjob、2 个 Feishu、52 个 Beisen），共十九个增量清单。前文的 68 个来源是第十八批结束时的历史快照；本批次的详细分页证据见上方第十九批记录。

统计修订（2026-08-29，第二十批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-20.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-20.json) 的 5 个来源后，累计已批准 78 个来源（6 个 Moka、18 个 Hotjob、2 个 Feishu、52 个 Beisen），共二十个增量清单。前一段的 73 个来源是第十九批结束时的历史快照。

统计修订（2026-08-29，第二十一批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-21.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-21.json) 的 5 个来源后，累计已批准 83 个来源（9 个 Moka、18 个 Hotjob、2 个 Feishu、54 个 Beisen），共二十一个增量清单。前一段的 78 个来源是第二十批结束时的历史快照。

第二十二批核验批准英科医疗科技股份有限公司的 Feishu 校招列表（3 页 158 条）。受限浏览器 collector 真实运行约 144 秒后完整结束，岗位详情、招聘项目、城市、职能、届别和发布时间均可读回；该租户已加入固定白名单，未开放通用 Feishu 域名。

统计修订（2026-08-29，第二十二批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-22.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-22.json) 的 1 个 Feishu 来源后，累计已批准 84 个来源（9 个 Moka、18 个 Hotjob、3 个 Feishu、54 个 Beisen），共二十二个增量清单。前一段的 83 个来源是第二十一批结束时的历史快照。

第二十三批核验批准元气森林 Feishu 社会招聘列表（5 个分页批次、312 条）。修正招聘类型映射后，真实 collector 读回 17 条实习、295 条社会招聘，计划字段分别为“实习招聘”和“社会招聘”；详情链接、城市、职能和发布时间均可读回。

统计修订（2026-08-29，第二十三批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-23.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-23.json) 的 1 个 Feishu 来源后，累计已批准 85 个来源（9 个 Moka、18 个 Hotjob、4 个 Feishu、54 个 Beisen），共二十三个增量清单。前一段的 84 个来源是第二十二批结束时的历史快照。

第二十四批核验批准 Momenta Feishu 实习列表（2 个分页批次、96 条）。真实 collector 读回 93 条实习和 3 条校园项目，包含城市、职能、项目、2027 届和发布时间；详情链接均为同租户路径。

统计修订（2026-08-29，第二十四批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-24.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-24.json) 的 1 个 Feishu 来源后，累计已批准 86 个来源（9 个 Moka、18 个 Hotjob、5 个 Feishu、54 个 Beisen），共二十四个增量清单。前一段的 85 个来源是第二十三批结束时的历史快照。

第二十五批核验批准乐信圣文 Feishu 综合列表（2 个分页批次、42 条）。真实 collector 读回 33 条社会、8 条实习和 1 条校园岗位，均有同域详情、城市、职能、招聘计划和发布时间。

统计修订（2026-08-29，第二十五批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-25.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-25.json) 的 1 个 Feishu 来源后，累计已批准 87 个来源（9 个 Moka、18 个 Hotjob、6 个 Feishu、54 个 Beisen），共二十五个增量清单。前一段的 86 个来源是第二十四批结束时的历史快照。

第二十六批核验批准轻舟智航 Feishu 社会列表（2 个分页批次、57 条）。真实 collector 读回 54 条社会和 3 条实习岗位，均含城市、职能、详情链接和发布时间。

统计修订（2026-08-29，第二十六批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-26.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-26.json) 的 1 个 Feishu 来源后，累计已批准 88 个来源（9 个 Moka、18 个 Hotjob、7 个 Feishu、54 个 Beisen），共二十六个增量清单。前一段的 87 个来源是第二十五批结束时的历史快照。

第二十七批核验批准英科再生 Feishu 校园列表（2 个分页批次、53 条）。真实 collector 读回 49 条校园和 4 条实习岗位，数量与首页项目摘要一致，并包含 2027 届、城市、职能和发布时间。

统计修订（2026-08-29，第二十七批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-27.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-27.json) 的 1 个 Feishu 来源后，累计已批准 89 个来源（9 个 Moka、18 个 Hotjob、8 个 Feishu、54 个 Beisen），共二十七个增量清单。前一段的 88 个来源是第二十六批结束时的历史快照。

第二十八批核验批准波克 Feishu 校园列表（2 个分页批次、105 条）。真实 collector 读回 97 条校园和 8 条实习岗位，均含上海地点、职能、2027 届和发布时间。

统计修订（2026-08-29，第二十八批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-28.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-28.json) 的 1 个 Feishu 来源后，累计已批准 90 个来源（9 个 Moka、18 个 Hotjob、9 个 Feishu、54 个 Beisen），共二十八个增量清单。前一段的 89 个来源是第二十七批结束时的历史快照。

第二十九批核验批准上海它石智航技术有限公司 Feishu 社会招聘列表（3 个分页批次、116 条）。受限 `blog-browser` collector 完整读回 `count=116`，每条均有同域详情链接、上海地点和 `publish_time`，招聘类型为社会招聘；页面自身的 `count` 请求 405 不影响实际 `job/posts` 成功响应。

统计修订（2026-08-29，第二十九批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-29.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-29.json) 的 1 个 Feishu 来源后，累计已批准 91 个来源（9 个 Moka、18 个 Hotjob、10 个 Feishu、54 个 Beisen），共二十九个增量清单。前一段的 90 个来源是第二十八批结束时的历史快照。

第三十批核验批准思朗科技 Feishu 校园招聘列表（2 个分页批次、41 条）。受限 `blog-browser` collector 完整读回 `count=41`，岗位标题含 2027 校招信息，详情链接均为同域，城市与 `publish_time` 均可读回。

统计修订（2026-08-29，第三十批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-30.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-30.json) 的 1 个 Feishu 来源后，累计已批准 92 个来源（9 个 Moka、18 个 Hotjob、11 个 Feishu、54 个 Beisen），共三十个增量清单。前一段的 91 个来源是第二十九批结束时的历史快照。

第三十一批核验批准原力灵机 Feishu 社会招聘列表（2 个分页批次、52 条）。受限 `blog-browser` collector 完整读回 `count=52`，岗位均有北京或无锡地点、同域详情链接和 `publish_time`，招聘类型均为社会招聘。

统计修订（2026-08-29，第三十一批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-31.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-31.json) 的 1 个 Feishu 来源后，累计已批准 93 个来源（9 个 Moka、18 个 Hotjob、12 个 Feishu、54 个 Beisen），共三十一个增量清单。前一段的 92 个来源是第三十批结束时的历史快照。

第三十二批核验批准森麒麟 Feishu 校园招聘列表（2 个分页批次、11 条）。受限 `blog-browser` collector 完整读回 `count=11`，全部为 2027 校招，含青岛地点、岗位类别、同域详情链接和 `publish_time`。

统计修订（2026-08-29，第三十二批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-32.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-32.json) 的 1 个 Feishu 来源后，累计已批准 94 个来源（9 个 Moka、18 个 Hotjob、13 个 Feishu、54 个 Beisen），共三十二个增量清单。前一段的 93 个来源是第三十一批结束时的历史快照。

第三十三批核验批准小鹏 Feishu 校园招聘列表（6 个分页批次、507 条）。受限 `blog-browser` collector 完整读回 `count=507`，岗位含 2027 校招和实习混合类型，均有城市、类别、同域详情链接和 `publish_time`；未按来源名称覆盖公开行类型。

统计修订（2026-08-29，第三十三批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-33.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-33.json) 的 1 个 Feishu 来源后，累计已批准 95 个来源（9 个 Moka、18 个 Hotjob、14 个 Feishu、54 个 Beisen），共三十三个增量清单。前一段的 94 个来源是第三十二批结束时的历史快照。

第三十四批核验批准去哪儿旅行 Feishu 综合职位列表（2 个分页批次、57 条）。受限 `blog-browser` collector 完整读回 `count=57`，包含社会招聘和实习混合行，均有城市、同域详情链接和 `publish_time`；类型按公开行字段保留。

统计修订（2026-08-29，第三十四批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-34.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-34.json) 的 1 个 Feishu 来源后，累计已批准 96 个来源（9 个 Moka、18 个 Hotjob、15 个 Feishu、54 个 Beisen），共三十四个增量清单。前一段的 95 个来源是第三十三批结束时的历史快照。

第三十五批核验批准锐石创芯 Feishu 社会招聘列表（2 个分页批次、8 条）。受限 `blog-browser` collector 完整读回 `count=8`，公开招聘类型均为社招，含深圳/上海/成都地点、岗位类别、同域详情链接和 `publish_time`。

统计修订（2026-08-29，第三十五批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-35.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-35.json) 的 1 个 Feishu 来源后，累计已批准 97 个来源（9 个 Moka、18 个 Hotjob、16 个 Feishu、54 个 Beisen），共三十五个增量清单。前一段的 96 个来源是第三十四批结束时的历史快照。

第三十六批核验批准马上消费两个官方 Feishu 列表：社会招聘列表 1 个分页批次、3 条岗位（北京/重庆/成都/杭州等地点、类别、详情链接和发布时间）；校招列表 1 个分页批次、0 条岗位，collector 返回 `complete=true` 的合法空集合。

统计修订（2026-08-29，第三十六批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-36.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-36.json) 的 2 个 Feishu 来源后，累计已批准 99 个来源（9 个 Moka、18 个 Hotjob、18 个 Feishu、54 个 Beisen），共三十六个增量清单。前一段的 97 个来源是第三十五批结束时的历史快照。

第三十七批核验批准北京发那科两个官方 Feishu 列表：社会招聘 1 个分页批次、9 条岗位；校园招聘 2 个分页批次、24 条岗位。两条列表均含北京/上海/深圳地点、类别、同域详情链接和 `publish_time`，校园行全部按公开字段识别为校园招聘。

统计修订（2026-08-29，第三十七批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-37.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-37.json) 的 2 个 Feishu 来源后，累计已批准 101 个来源（9 个 Moka、18 个 Hotjob、20 个 Feishu、54 个 Beisen），共三十七个增量清单。前一段的 99 个来源是第三十六批结束时的历史快照。

第三十八批核验批准利欧集团两个 canonical Feishu 列表：社会招聘 2 个分页批次、47 条岗位（44 条社会、3 条实习），校园招聘 2 个分页批次、31 条岗位（均为 2027 届）。两个入口均含城市、类别、同域详情链接和 `publish_time`；旧候选租户已 canonical 重定向，未重复登记。

统计修订（2026-08-29，第三十八批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-38.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-38.json) 的 2 个 Feishu 来源后，累计已批准 103 个来源（9 个 Moka、18 个 Hotjob、22 个 Feishu、54 个 Beisen），共三十八个增量清单。前一段的 101 个来源是第三十七批结束时的历史快照。

第三十九批核验批准雷鸟创新 Feishu 综合职位列表（3 个分页批次、123 条）。受限 `blog-browser` collector 完整读回 `count=123`，其中 109 条社会招聘、14 条实习，均含深圳/宁波/成都/无锡/北京地点、类别、同域详情链接和 `publish_time`；类型按公开行字段保留。

统计修订（2026-08-29，第三十九批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-39.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-39.json) 的 1 个 Feishu 来源后，累计已批准 104 个来源（9 个 Moka、18 个 Hotjob、23 个 Feishu、54 个 Beisen），共三十九个增量清单。前一段的 103 个来源是第三十八批结束时的历史快照。

第四十批核验批准禾赛科技两个官方 Feishu 列表：校园招聘 3 个分页批次、149 条岗位（144 条校园、5 条实习）；社会招聘 3 个分页批次、156 条岗位。两入口均含城市、类别、同域详情链接和 `publish_time`，类型按公开行字段保留；社会列表首次运行无进展，稳定重试后完整闭合。

统计修订（2026-08-29，第四十批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-40.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-40.json) 的 2 个 Feishu 来源后，累计已批准 106 个来源（9 个 Moka、18 个 Hotjob、25 个 Feishu、54 个 Beisen），共四十个增量清单。前一段的 104 个来源是第三十九批结束时的历史快照。

第四十一批核验批准中芯国际官网指向的两个北森列表：校园招聘 25 页、248 条岗位（含 2026/2027 届）；社会招聘 30 页、293 条岗位。两入口均为旧版 `zwm` 服务端列表，适配器新增受限解析和 256 KiB 页面上限后完整闭合，详情链接、城市和类别可读。

统计修订（2026-08-29，第四十一批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-41.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-41.json) 的 2 个 Beisen 来源后，累计已批准 108 个来源（9 个 Moka、18 个 Hotjob、25 个 Feishu、56 个 Beisen），共四十一个增量清单。前一段的 106 个来源是第四十批结束时的历史快照。

第四十二批核验批准安克创新官方 Feishu 校园/实习综合列表（6 个分页批次、493 条）。受限 collector 完整读回 239 条校园和 254 条实习岗位，均有城市、类别、同域详情链接和 `publish_time`；同一列表只登记一个综合来源。

统计修订（2026-08-29，第四十二批）：新增 [`config/opportunity_sources.additions-2026-08-29.batch-42.json`](../../../config/opportunity_sources.additions-2026-08-29.batch-42.json) 的 1 个 Feishu 来源后，累计已批准 109 个来源（9 个 Moka、18 个 Hotjob、26 个 Feishu、56 个 Beisen），共四十二个增量清单。前一段的 108 个来源是第四十一批结束时的历史快照。

1. 管理员先分别对二十九个增量清单执行 dry-run，确认首批 21 条、第二批 2 条、第三批 4 条和第四批 1 条和第五批 1 条和第六批 1 条和第七批 1 条和第八批 2 条和第九批 1 条和第十批 2 条和第十一批 5 条和第十二批 4 条和第十三批 4 条和第十四批 2 条和第十五批 2 条和第十六批 1 条和第十七批 1 条和第十八批 13 条和第十九批 5 条、第二十批 5 条、第二十一批 5 条、第二十二至第二十九批各 1 条、唯一 URL、适配器均已注册。
2. 继续按候选平台批次核验 832 条候选记录，使用规范化 URL 与 CSV 行号维护逐条状态；每批单独记录企业、URL、列表证据、岗位总数和适配器结论。
3. 已获授权并在 Labs 以合并清单导入已通过核验的全部批次；新增来源置为 `NEVER`/未公开，不改动现有来源、岗位和任务历史。后续只需按来源执行首次检查与审核。
4. 在 Labs 串行执行首次来源检查，逐来源核对岗位数、发布时间、届别窗口和失败原因；只有完整分页和去重读回通过后才进入公开审核。
5. 不将任何未核验候选或首批清单直接视为生产发布；生产迁移、来源导入和全量爬取仍需单独授权与备份门禁。
6. 第十九批 manifest 已通过 dry-run；继续核验时从剩余候选 URL 逐批推进，不能把入口页、详情页、重复镜像或未闭合分页加入来源。
7. 第二十批 manifest 同样仅做 dry-run；长龙的分页元数据曾发生一次瞬时不一致，首次 Labs 采集时需核对任务是否稳定进入成功终态。
8. 第二十一批 manifest 已通过 dry-run；华勤的三个 Moka 租户由官网公开链接确认，首次采集时需保留其混合招聘类型，不按来源名称强行覆盖。
9. 第二十二批 manifest 已通过 dry-run；Feishu 浏览器采集耗时较长，首次 Labs 检查应保持单来源串行并观察任务租约，不要并发启动多个浏览器采集。
10. 第二十三批 manifest 已通过 dry-run；元气森林的类型映射回归已加入，后续同类 Feishu 租户需同时核对具体 `recruit_type` 与父级字段。
11. 第二十四批 manifest 已通过 dry-run；Momenta 页面同样有少量校园项目行，首次采集需保留具体类型和项目字段。
12. 第二十五批 manifest 已通过 dry-run；乐信圣文综合页的混合招聘类型需沿用具体行字段，不按来源类型覆盖。
13. 第二十六批 manifest 已通过 dry-run；轻舟智航页面虽以社会入口为主，仍需保留具体实习行的类型。
14. 第二十七批 manifest 已通过 dry-run；英科再生列表加载较慢但 collector 完整闭合，首次 Labs 采集仍需观察租约和超时。
15. 第二十八批 manifest 已通过 dry-run；波克校园列表含实习行，首次采集继续按行保留类型。
16. 第二十九批 manifest 已通过 dry-run；Tars 社招列表的 405 计数请求不能作为失败依据，首次 Labs 采集需继续核对 `job/posts` 的完整终态。
17. 第三十批 manifest 已通过 dry-run；思朗校招列表使用单段业务前缀 `/xiaozhao/position/list`，首次 Labs 采集需继续核对 41 条岗位和类型字段。
18. 第三十一批 manifest 已通过 dry-run；原力灵机社会列表需在首次 Labs 采集时继续核对 52 条岗位和北京/无锡地点。
19. 第三十二批 manifest 已通过 dry-run；森麒麟校园列表需在首次 Labs 采集时继续核对 11 条 2027 届岗位和青岛地点。
20. 第三十三批 manifest 已通过 dry-run；小鹏列表含历史实习行，首次 Labs 采集需核对类型保留和 507 条分页闭合，不按来源类型强制归类。
21. 第三十四批 manifest 已通过 dry-run；去哪儿综合列表含社会与实习混合行，首次 Labs 采集需核对 57 条分页闭合和类型保留。
22. 第三十五批 manifest 已通过 dry-run；锐石创芯社会列表需在首次 Labs 采集时继续核对 8 条岗位和城市/类别字段。
23. 第三十六批 manifest 已通过 dry-run；马上消费校招空列表需保持可监测，不得当作采集失败或伪造岗位。
24. 第三十七批 manifest 已通过 dry-run；北京发那科社会/校园列表需在首次 Labs 采集时分别核对 9/24 条岗位和类型字段。
25. 第三十八批 manifest 已通过 dry-run；利欧旧租户应继续使用 canonical `leoglobal.jobs.feishu.cn`，首次 Labs 采集需核对社会/校园两列表的类型和数量。
26. 第三十九批 manifest 已通过 dry-run；雷鸟综合列表含社会与实习混合行，首次 Labs 采集需核对 123 条分页闭合和类型保留。
27. 第四十批 manifest 已通过 dry-run；禾赛社会列表曾出现无进展，首次 Labs 采集需关注租约/超时并核对 156 条，校园列表核对 149 条。
28. 第四十一批 manifest 已通过 dry-run；中芯国际旧版 `zwm` 页面需在首次 Labs 采集时核对 25/30 页、248/293 条和届别窗口。
29. 第四十二批 manifest 已通过 dry-run；安克综合列表含校园/实习混合行，首次 Labs 采集需核对 493 条和类型保留。

## 合并导入记录（2026-08-29）

为避免只导入最后一批，本次使用 [`config/opportunity_sources.additions-2026-08-29.all.json`](../../../config/opportunity_sources.additions-2026-08-29.all.json) 将首批清单与 batch-02 至 batch-42 逐一合并后一次性导入 Labs。合并清单共 42 份、109 条来源；按规范化 UUID 和 canonical URL 校验后均唯一，且与原有 41 条来源没有冲突。

Labs 导入结果：`created=109`、`updated=0`。数据库读回为 150 条来源、158 条来源域名记录；新增 109 条全部为启用、未公开、`NEVER`/零失败/`row_version=1`，适配器分布为 Moka 9、Hotjob 18、Feishu 26、Beisen 56。42 份原始批次逐批读回均为预期数量，现有岗位数据（10,705 条）未被来源导入改动。

本次只登记来源配置，没有自动启动 109 个首次爬取任务；后续应在 Labs 按来源串行检查分页、发布时间、届别窗口和失败原因，通过审核后再公开。

## 新增来源审核结果（2026-08-30）

本次审核范围严格限定为 `config/opportunity_sources.additions-2026-08-29.all.json` 中的 109 条新增来源。旧的 `config/opportunity_sources.v1.json` 41 条来源不纳入本轮 IT 审核，也没有被停用、重新检查或改写；Labs 数据库读回为 41 条全部 `enabled=true`、`publicly_visible=true`。

### 结果汇总

| 项目 | 数量 | 结论 |
| --- | ---: | --- |
| 新增来源总数 | 109 | 全部能在 Labs 以 UUID 和 canonical URL 唯一读回 |
| 保留并启用 | 88 | 通过官方列表、分页完整和 IT/技术岗位门槛 |
| 下架 | 21 | 无可验证 IT 岗位、仅非 IT 岗位，或列表证据不足；保留历史数据和审计记录 |
| 保留来源的完整快照 | 88/88 | 最新检查均为 `SUCCEEDED`，`complete=true`、`truncated=false` |
| 保留来源的非空列表 | 85 | 共读回 13,057 条岗位；每条来源至少有一个明确技术岗位标题或技术类别 |
| 合法空列表监测来源 | 3 | 巨一校园、欣旺达实习、马上消费校招；页面完整返回 0 条，不伪造岗位 |

保留来源的适配器分布为 Beisen 46、Feishu 21、Hotjob 13、Moka 8；来源类型为校园 49、综合 23、社会 12、实习 4。所有保留来源仍按来源自动公开规则运行，当前 `publicly_visible=true`，没有把旧来源混入本轮裁决。

### IT 相关性门槛

判定使用实际采集到的岗位标题、招聘计划和分类，不按公司名称臆测。明确技术信号包括软件/开发、算法/人工智能、数据/计算机/IT、云/网络/安全、前后端/客户端、嵌入式/硬件/芯片、测试、数字化、智能制造、FPGA、编译器、系统和技术研发等。85 条非空保留来源均至少命中一个信号；例如滴滴、科大讯飞、地平线、安克创新、新华三、中芯国际、传音控股、禾赛科技和华勤技术均有成批软件、算法、AI、数据或硬件岗位。对制造、半导体、汽车和金融企业，仅保留实际存在技术研发、软件、算法、信息系统或硬件岗位的来源，不因企业属于某行业就自动通过。

本轮下架的 21 条新增来源为：双环传动、三棵树、宝时得科技、新城控股集团股份有限公司上海分公司、天风证券、诺瓦星云实习、华夏航空、杰克股份、金山云、货拉拉、龙旗科技、基恩士、前海开源、欣旺达实习、一鸣食品、思摩尔国际（SMOORE）、英科医疗科技股份有限公司、元气森林、英科再生、青岛森麒麟轮胎股份有限公司、利欧集团社会招聘。下架只影响这些新增来源；同名企业的其他新增来源若有明确 IT 岗位仍独立保留，例如利欧集团校园来源、欣旺达综合来源和诺瓦星云社会来源。

### 失败来源修复与复核

浙江长龙航空综合入口最初因 Hotjob 首页返回 `pageSize=10,totalPage=9`，后续页返回 `pageSize=15,totalPage=6` 而触发 `opportunities.adapter_response_invalid.v1`。适配器现在在首响应报告不同页大小时只重启一次分页，并继续用提供方实际页大小校验总数，避免漏读或把可恢复的元数据漂移当作成功。聚焦回归为 `7 passed`；Labs 真实安全 HTTP 客户端读回综合入口 `complete=True`、`truncated=False`、88 条岗位。随后在 Labs 以当前代码执行单来源任务 `01M178WAC4V89J1Y4AEYC8DT1P`，数据库读回 `run/item=SUCCEEDED`、快照 88 条、7 个逻辑分页、0 错误、88 条在架岗位。

### 审核边界与后续

本次审核没有删除岗位、清空历史、迁移数据库、发布生产或执行 Git 操作。21 条下架来源的岗位历史仍保留，但不会进入公开来源列表；3 条合法空列表继续监测，下一次有岗位时再按同一 IT 门槛复核。后续 Celery worker 若要在常驻进程中使用 Hotjob 页大小修复，需要在获得服务重启授权后执行一次受控 worker 重载；本次已用同步任务完成 Labs 数据读回验证，未擅自重启服务。

字段完整性补充：本轮保留来源的 13,057 条岗位中，Feishu 2,106、Hotjob 1,549、Moka 456 条带有可解析的发布时间；Beisen 8,946 条当前均未读到可解析发布时间。该字段缺失没有被误判为来源无效，也没有改变本轮 IT 裁决；如要求所有岗位必须显示发布时间，应另行补充 Beisen 字段适配。
