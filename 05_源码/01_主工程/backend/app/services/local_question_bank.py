"""无大模型时可用的本地阶段题库。

设计约束（为什么要有这个模块）：
- 练习诊断的题库原本只由 Orchestrator 调用大模型生成，环境没有配置 `LLM_API_KEY`
  时整条链路直接报错，界面只能显示一行红字。
- 评委/断网环境需要在没有任何外部 key 的情况下也能把「出题 → 作答 → 判分 →
  错题入库 → 掌握度」走通，因此这里用一份静态模板题库兜底。
- 兜底必须**自我声明**：资源 meta 里写 `local_template: True`，标题带
  「本地模板 · 未调用大模型」，页面据此显示徽标，不允许伪装成大模型生成。
- 数据格式必须和 `exercise_bank._load_generated_questions` 完全一致，否则兜底
  出来的题不会出现在练习会话里：type/title/content_uri/meta.requirement
  缺一不可，且 `meta.requirement.constraints.source` 必须是 `exercise_custom_bank`。
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.ids import new_id
from app.repo import insert_learning_event, insert_resource_item

LOCAL_BANK_AGENT = "local_question_bank"
LOCAL_BANK_TAG = "本地模板"

# 题型 -> 可用题目模板。选项顺序即作答顺序，answer 用选项字母表示。
TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "single_choice": [
        {
            "stem": "在用例图中，下列关于 include（包含）关系的描述正确的是（  ）。",
            "options": [
                "被包含用例必须执行，包含用例才可以执行",
                "包含用例一定会执行被包含用例，且被包含用例可被多个用例复用",
                "两个用例之间是可选关系，只是表达先后顺序",
                "包含关系只能出现在参与者（Actor）与用例之间",
            ],
            "answer": "B",
            "analysis": "include 表示当前用例**必须**执行被包含用例的公共行为，被包含用例可被多个用例复用；extend 才是可选的扩展点，所以 A、C 都不对，D 描述的是关联关系。",
            "knowledge_point": "用例关系 include",
        },
        {
            "stem": "用例图中 extend（扩展）关系成立的典型条件是（  ）。",
            "options": [
                "扩展用例无条件执行",
                "基础用例一定在某个扩展点触发扩展用例",
                "只有在特定条件下才执行扩展用例，且扩展用例不能独立承担主流程",
                "扩展用例必须比基础用例的编号更大",
            ],
            "answer": "C",
            "analysis": "extend 是**可选**的扩展：基础用例到达扩展点、且条件成立时才执行扩展用例；扩展用例本身不独立承担主流程。",
            "knowledge_point": "用例关系 extend",
        },
        {
            "stem": "下列哪一项最可能被识别为用例图中的参与者（Actor）？（  ）",
            "options": [
                "数据库表",
                "提交选课申请的学生",
                "用例之间的包含连线",
                "需求规格说明书的章节标题",
            ],
            "answer": "B",
            "analysis": "参与者是**与系统交互的外部角色**，人、外部系统、定时器都可以是参与者；数据库表与连线是系统内部结构，不是参与者。",
            "knowledge_point": "参与者识别",
        },
        {
            "stem": "非功能需求（如响应时间、并发量）在需求分析与建模阶段的正确处理方式是（  ）。",
            "options": [
                "归入实现细节，需求阶段不记录",
                "只写进项目计划，不进需求文档",
                "作为可度量的质量属性写入需求规格说明，并给出验收口径",
                "等系统上线后再根据实际表现补充",
            ],
            "answer": "C",
            "analysis": "非功能需求必须在需求阶段给出**可度量**的指标与验收口径，否则后期无法判定是否达标，也无法据此设计架构。",
            "knowledge_point": "非功能需求",
        },
        {
            "stem": "需求获取阶段同时使用访谈与原型法，主要目的是（  ）。",
            "options": [
                "用访谈替代文档评审",
                "弥补受访者表达能力的局限，用可看见的原型暴露隐藏需求",
                "减少参与者数量",
                "直接产出可上线的代码",
            ],
            "answer": "B",
            "analysis": "访谈适合澄清业务目标与术语，但用户常常说不清自己要什么；原型把抽象描述变成可看见的界面，能暴露遗漏与歧义。两者互补而非替代。",
            "knowledge_point": "需求获取方法",
        },
        {
            "stem": "在需求规格说明中，一条合格的用例描述一般不应缺少（  ）。",
            "options": [
                "用例编号、参与者、前置条件、主流程、备选流程、后置条件",
                "数据库表结构与索引设计",
                "服务器型号与部署拓扑",
                "项目预算与人员排期",
            ],
            "answer": "A",
            "analysis": "用例描述要能被验证与评审，必须包含编号、参与者、前后置条件、主流程与备选/异常流程；表结构、部署拓扑属于设计阶段。",
            "knowledge_point": "用例描述规范",
        },
    ],
    "multiple_choice": [
        {
            "stem": "下列哪些属于需求分析与建模阶段应产出的工件？（  ）",
            "options": [
                "用例图与用例描述",
                "需求规格说明书",
                "数据库物理索引脚本",
                "参与者与外部系统清单",
            ],
            "answer": "ABD",
            "analysis": "A、B、D 都是需求阶段工件；物理索引脚本属于数据库设计阶段产物。",
            "knowledge_point": "需求工件",
        },
        {
            "stem": "关于用例图与数据流图（DFD）的区别，下列说法正确的有（  ）。",
            "options": [
                "用例图面向外部角色描述系统能提供什么服务",
                "数据流图面向数据在系统内部的加工与流动",
                "用例图中不应出现数据库表",
                "两者可以互相完全替代",
            ],
            "answer": "ABC",
            "analysis": "用例图是**行为视角**、面向外部角色；DFD 是**数据视角**、面向内部加工。两者关注点不同，不能互相替代，所以 D 错。",
            "knowledge_point": "用例图与数据流图",
        },
        {
            "stem": "下列哪些现象说明需求获取可能不够充分？（  ）",
            "options": [
                "开发与用户对同一术语理解不一致",
                "用例遗漏了重要的异常分支",
                "需求文档没有任何非功能指标",
                "评审会上没有人提出异议",
            ],
            "answer": "ABC",
            "analysis": "术语歧义、异常分支缺失、非功能指标缺失都是需求不充分的典型信号；「没人提异议」不等于需求完整，反而可能是评审走过场。",
            "knowledge_point": "需求评审",
        },
    ],
    "true_false": [
        {
            "stem": "判断：用例图中的两个用例之间可以存在继承（泛化）关系。",
            "options": ["正确", "错误"],
            "answer": "正确",
            "analysis": "用例之间允许泛化：子用例继承父用例的行为并可扩展，这是 UML 用例图的合法关系之一。",
            "knowledge_point": "用例关系泛化",
        },
        {
            "stem": "判断：一个用例的执行结果应能被外部参与者观察到。",
            "options": ["正确", "错误"],
            "answer": "正确",
            "analysis": "用例是「系统为参与者提供的一个可观察的有价值结果」，因此必须有可观察的返回，否则更像内部函数。",
            "knowledge_point": "用例定义",
        },
        {
            "stem": "判断：需求规格说明一旦签字就不可再变更。",
            "options": ["正确", "错误"],
            "answer": "错误",
            "analysis": "需求会随业务变化而演化，正确做法是**受控变更**（变更评审 + 影响分析 + 版本留痕），而不是冻结不变。",
            "knowledge_point": "需求变更管理",
        },
    ],
    "short_answer": [
        {
            "stem": "简述用例图中 include 与 extend 的核心区别，并各举一个业务场景。",
            "options": [],
            "answer": "include：基础用例**必定**执行被包含用例，用于抽取公共步骤，如「下单」必含「校验库存」；extend：基础用例在**特定条件**下才执行扩展用例，如「支付」可扩展出「使用优惠券」。",
            "analysis": "判分看两点：是否说出「必选 vs 可选」，以及是否各给出一个场景。只说一句「一个是包含一个是扩展」不得分。",
            "knowledge_point": "用例关系对比",
        },
        {
            "stem": "为什么需求阶段就要为每个需求写入验收口径？请结合一个非功能需求说明。",
            "options": [],
            "answer": "验收口径把模糊描述变成可判定的条件，否则无法验证、也无法据此设计。例如「系统要快」应写成「列表页在 200 条数据内 P95 响应 ≤ 800ms」，这样开发有目标、测试有判据。",
            "analysis": "关键要点：可度量、可判定、能落到测试用例；缺任一点视为不合格答案。",
            "knowledge_point": "可验证需求",
        },
    ],
    "case_analysis": [
        {
            "stem": "某教务系统需求描述：「学生可以选课，课程容量未满时选课成功，容量已满时进入等待队列。」请指出应建模为哪些用例，并说明主流程与备选流程。",
            "options": [],
            "answer": "用例「选课」（参与者：学生）。主流程：学生提交选课请求 → 系统校验容量 → 容量未满则写入选课记录 → 返回成功。备选流程：容量已满 → 进入等待队列 → 返回「已排队」。",
            "analysis": "考察点：能否把一句话需求拆成用例 + 主流程 + 备选流程，且把「容量满」建模为备选分支而不是新用例。",
            "knowledge_point": "用例建模实操",
        },
        {
            "stem": "评审中发现开发把「查询成绩」画成了用例，但该操作没有任何参与者交互、也不改变系统状态。请判断这是否是合法用例，并说明理由。",
            "options": [],
            "answer": "不合法（或不必要）。用例必须是为参与者提供可观察价值的外部交互；纯内部数据加工既无参与者交互、也无状态变化，更适合放进数据流图/内部设计，而不是用例图。",
            "analysis": "考察点：用例的判定标准（外部可观察价值 + 参与者交互），能否区分用例图与内部处理建模。",
            "knowledge_point": "用例判定标准",
        },
    ],
}

TYPE_ORDER = ["single_choice", "multiple_choice", "true_false", "short_answer", "case_analysis"]


def llm_ready() -> bool:
    """是否配置了可用于出题的大模型（base_url + api_key 同时存在才算）。"""
    return bool(str(settings.llm_base_url or "").strip() and str(settings.llm_api_key or "").strip())


def _requested_counts(requirement: dict[str, Any]) -> tuple[dict[str, int], int]:
    config = requirement.get("question_config") if isinstance(requirement.get("question_config"), dict) else {}
    raw_counts = config.get("type_counts") if isinstance(config.get("type_counts"), dict) else {}
    counts: dict[str, int] = {}
    for key in TYPE_ORDER:
        value = raw_counts.get(key)
        try:
            counts[key] = max(0, int(value or 0))
        except (TypeError, ValueError):
            counts[key] = 0
    total = int(config.get("count") or sum(counts.values()) or 10)
    return counts, max(1, min(50, total))


def _select_questions(counts: dict[str, int], total: int) -> list[dict[str, Any]]:
    """按用户设定的题型数量选题；题型数量合计不足时用单选补齐到 total。"""
    picked: list[dict[str, Any]] = []
    for key in TYPE_ORDER:
        want = counts.get(key, 0)
        if want <= 0:
            continue
        pool = TEMPLATES.get(key, [])
        for idx in range(want):
            if not pool:
                break
            picked.append({**pool[idx % len(pool)], "type": key})

    if not picked:
        for idx in range(total):
            pool = TEMPLATES["single_choice"]
            picked.append({**pool[idx % len(pool)], "type": "single_choice"})

    if len(picked) < total:
        pool = TEMPLATES["single_choice"]
        idx = 0
        while len(picked) < total:
            picked.append({**pool[idx % len(pool)], "type": "single_choice"})
            idx += 1
    return picked[:total]


def build_local_question_bank(student_id: str, requirement: dict[str, Any]) -> dict[str, Any]:
    """生成一份本地模板题库资源，并写入用户资源清单。

    返回结构与 `insert_resource_item` 一致，可直接塞进 `resources` 列表。
    """
    requirement = dict(requirement or {})
    constraints = requirement.get("constraints") if isinstance(requirement.get("constraints"), dict) else {}
    # 保留调用方已经声明过的来源（练习诊断用 exercise_custom_bank，路径阶段用 path_stage_quiz），
    # 只补上缺失的字段：题库加载器只认这两个来源。
    source = str(constraints.get("source") or "").strip() or "exercise_custom_bank"
    requirement["constraints"] = {
        **constraints,
        "source": source,
        "skip_quality_check": True,
    }

    counts, total = _requested_counts(requirement)
    questions = _select_questions(counts, total)

    stage_title = str(constraints.get("path_stage_title") or "").strip()
    weak_points = [str(item).strip() for item in (requirement.get("weak_points") or []) if str(item).strip()]

    payload = {
        "meta": {
            "major": str(requirement.get("major") or "软件工程"),
            "course": str(requirement.get("course") or stage_title or "软件需求分析与建模"),
            "chapter": stage_title,
        },
        "questions": questions,
    }

    file_id = new_id()
    rel_path = f"files/{student_id}/{file_id}.json"
    abs_path = settings.data_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    title_prefix = stage_title or "阶段"
    item = insert_resource_item(
        student_id=student_id,
        type="question_bank",
        title=f"{title_prefix}题库（{LOCAL_BANK_TAG} · 未调用大模型）",
        tags=(weak_points or ["本地模板"])[:5],
        content_uri=rel_path,
        meta={
            "agent": LOCAL_BANK_AGENT,
            "requirement": requirement,
            "local_template": True,
            "question_count": len(questions),
        },
    )
    insert_learning_event(student_id, "generate", {"count": 1, "agent": LOCAL_BANK_AGENT, "local_template": True})
    return item
