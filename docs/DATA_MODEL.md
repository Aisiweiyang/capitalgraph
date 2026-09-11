# CapitalGraph CN 数据模型

版本：0.1 ｜ 2026-09-07 ｜ 与 `packages/domain` 实现保持同步

## 实体与标识

| 表 | 说明 | 关键列 |
| --- | --- | --- |
| entities | 企业/自然人/基金/合伙/机构/政府或国资机构/证券/分支机构 | id, kind, primary_name_id, created_at, merged_into_id(疑似重复/合并) |
| entity_identifiers | 外部 ID，一律带命名空间 | entity_id, namespace(uscc/lei/ticker/src:<connector>), value, valid_from/to |
| name_aliases | 名称与曾用名 | entity_id, name, norm_name, alias_type(official/former/abbreviation/translation), lang, valid_from/to |
| securities | 证券与主体关联 | entity_id, code, exchange, security_type |

约束：禁止名称作主键；`(namespace, value)` 唯一（活跃期间）；USCC 过 GB 32100 校验位。

## 声明层（时态、证据优先）

| 表 | 说明 |
| --- | --- |
| relationship_statements | subject/predicate/object 三元声明：predicate ∈ holds_shares/controls/beneficial_owner_candidate/invests_in/appointed_at/legal_rep/provides_guarantee/pledges_shares/related_transaction/same_control；含 share_ratio、voting_ratio、control_type、currency、amount、valid_from/valid_to、recorded_at、status、claim_basis、confidence |
| ownership_statements | 持股特化视图（独立表，不与控制混同）：share_ratio、share_class、via_security |
| control_statements | 控制特化：control_type(voting_rights/board/contract/de_facto/government)，表决权路径说明 |

硬约束：**持股不自动等于控制**。ownership 与 control 必须分别成声明；控制可引用持股证据但不隐式生成。

## 证据层（append-only）

| 表 | 说明 |
| --- | --- |
| source_documents | 来源登记：connector_id、原始 URL、访问时间、条款/许可证说明、内容哈希 |
| source_snapshots | 抓取快照：document_id、存储键(对象存储 sha256)、http_status、fetched_at；原文可关闭则只存哈希 |
| evidence_fragments | 证据片段：snapshot_id、json_path/xpath、字段、原始值、标准化值、页面行号 |
| dataset_licenses | 数据集许可证与允许用途 |
| ingestion_runs | 采集运行：connector、参数哈希、started/finished、status、counts、error 摘要 |

每个声明通过 `statement_evidence`(statement_id, evidence_fragment_id, actor, note) 关联 ≥1 证据片段；
无证据声明只能在 status=disputed/pending_review 下存在。

## 实体解析

| 表 | 说明 |
| --- | --- |
| resolution_candidates | 特征(JSON)、分数、阈值、匹配方法版本、输入哈希 |
| resolution_decisions | candidate → decision(merge/reject/pending)、decided_by(rule/model/human)、版本、理由 |

## 派生层（可重算）

| 表 | 说明 |
| --- | --- |
| derived_paths | 每条路径：root→…→leaf、边声明 id 列表、直接比例、路径乘积、环路标记 |
| ownership_calculations | 一次计算：root、at、config(深度/阈值)、config_hash、algorithm_version、输入声明集合哈希、聚合有效权益、方法说明、unknown 字段显式置空 |
| risk_flags | flag_type(cycle/cross_holding/missing_ratio/ratio_anomaly/low_confidence/duplicate_candidate/stale_source)、subject、payload、状态 |

## 数据质量与复核

| 表 | 说明 |
| --- | --- |
| quality_issues | 规则名、严重度、目标实体/声明、检测运行、状态(open/confirmed/dismissed) |
| review_queue | 待人工复核：类型(冲突/疑似重复/低置信/来源失效)、payload、assignee、结果 |

## 运营与安全

| 表 | 说明 |
| --- | --- |
| users | 用户名、口令哈希(argon2id)、角色、is_active |
| audit_log | 追加式：actor、action、target、request_id、result、at、detail(JSON，脱敏) |
| tasks | worker 任务：kind、幂等键(唯一)、payload、status、attempts、next_retry_at、last_error |

## 时态规则

- 有效性区间左闭右开：`valid_from <= at < valid_to`；`valid_to` 为空表示至今。
- 修正不覆盖：旧声明 `status→superseded` 并新开一条，`superseded_by_id` 指向新声明。
- `recorded_at` 永远不改写历史答案。
