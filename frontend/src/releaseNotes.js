export const releasePageCopy = {
  en: {
    label: "Release notes",
    title: "What changed, exactly.",
    intro: "Each note separates the visible outcome from the mechanism, names what stayed unchanged, and records how the work was validated."
  },
  zh: {
    label: "更新日志",
    title: "到底改了什么。",
    intro: "每份更新都会把用户看得见的结果、背后的机制、没有改变的部分和实际验证分开说清楚。"
  }
}

export const releaseNotes = [
  {
    id: "2026-07-18-big-books",
    date: "2026-07-18",
    en: {
      pageLabel: "Release notes",
      badge: "Reader update",
      dateLabel: "July 18, 2026",
      title: "Academic pages stay intact. Large graphs stay readable.",
      intro: "This release adds an Academic reading mode for papers and textbooks, makes document structure detection more reliable, and keeps the complete graph usable as books grow. It changes PDF reading, extraction recovery, and graph rendering; it does not remove any nodes or relationships from All Chapters.",
      comparisonLead: "Think of it as two reading paths:",
      comparisonHeaders: ["", "Novel / continuous prose", "Academic document"],
      comparisonRows: [
        ["Best for", "Novels and narrative books", "Papers, textbooks, and research reports"],
        ["Default PDF mode", "Detected chapters", "Physical pages"],
        ["Reader presentation", "Reflowed text", "Original PDF pages"],
        ["What stays intact", "Chapter order and readable paragraphs", "Formulas, figures, tables, captions, columns, images, and typography"],
        ["Search and graph jumps", "Exact extracted passage", "Highlights and source links over the original page"]
      ],
      walkthroughHeading: "For this release, we:",
      walkthrough: [
        "Classify a PDF from a bounded early text sample, then default novels to chapter mode and papers or textbooks to physical-page mode. Uncertain documents ask the reader to choose.",
        "Render physical pages through PDF.js instead of flattening an academic document into reflowed body text, while retaining search highlights and graph source jumps.",
        "Prefer EPUB navigation and PDF outline or page-layout evidence before fallback segmentation, reducing false chapters from contents pages, citations, page numbers, and referenced books.",
        "Open the reader before the complete graph is ready, load the current episode and initial graph in parallel, search on the server, and transfer later graph changes as episode deltas.",
        "Move dense graphs to WebGL. Standard graphs receive a bounded layout window before freezing; massive graphs use a static profile that keeps every node and edge without continuous layout work.",
        "Draw a bounded, collision-aware set of labels. Important entities are considered first, zoom reveals more local names, and searched or selected entities remain eligible.",
        "Present relationship details as source entity → relationship → target entity, merge entity types case-insensitively, and let a failed chapter retry without rebuilding the whole book."
      ],
      conclusionsHeading: "So:",
      conclusions: [
        "Academic PDFs keep the page structure that carries meaning instead of becoming a wall of extracted text.",
        "Page mode still supports search, reading progress, graph extraction, and jumps back to the source.",
        "All Chapters still contains every extracted node and relationship; the renderer only limits which labels are painted at the current zoom.",
        "The primary extraction provider remains the first attempt. OpenRouter is an optional fallback after a primary failure.",
        "The reader remains usable while extraction and graph delivery continue in the background."
      ],
      importantLabel: "One important detail:",
      importantDetail: "A cleaner graph overview does not mean graph data was discarded. Label selection controls only which names are drawn at the current camera position. Search targets and selected entities stay visible, zoom reveals more names, and the complete node-and-edge topology remains available.",
      validationHeading: "Validation",
      validation: [
        "All 59 frontend unit tests passed, the production build completed, and the entry bundle measured 223,992 bytes against a 307,200-byte limit.",
        "The massive-graph browser fixture carries exactly 5,000 nodes and 20,000 relationships and exercises scope switching, search, maximize and restore, drag, and a 12-event wheel burst.",
        "The standard WebGL fixture carries 600 nodes and 1,200 relationships and checks visible links during layout, frozen final coordinates, collision-free labels, hub emphasis, and semantic zoom.",
        "The landing route keeps reader, PDF.js, WebGL, and release-detail views in lazy route chunks; the entry bundle retains its 300 KiB raw-size budget."
      ],
      backHome: "Back to PageAndNode",
      timelineLabel: "Release timeline"
    },
    zh: {
      pageLabel: "更新日志",
      badge: "阅读器更新",
      dateLabel: "2026 年 7 月 18 日",
      title: "学术页面保留原貌，大图也终于看得清。",
      intro: "这次更新加入了面向论文与教材的学术阅读模式，让文档结构识别更可靠，也让整本书的完整图谱在规模变大后仍然可用。它改变了 PDF 阅读、抽取恢复和图谱渲染；All Chapters 里的节点和关系一条都没有删。",
      comparisonLead: "可以把它理解成两条阅读路径：",
      comparisonHeaders: ["", "小说 / 连续正文", "学术文档"],
      comparisonRows: [
        ["适合内容", "小说与叙事类书籍", "论文、教材与研究报告"],
        ["PDF 默认模式", "识别出的章节", "物理页面"],
        ["阅读器呈现", "重排后的正文", "原始 PDF 页面"],
        ["保留内容", "章节顺序与可读段落", "公式、图表、表格、题注、分栏、图片与字体"],
        ["搜索与图谱溯源", "定位到抽取出的原文段落", "在原始页面上高亮并跳回出处"]
      ],
      walkthroughHeading: "这次更新具体做了这些事：",
      walkthrough: [
        "用长度受限的开头文本判断 PDF 类型：小说默认按章节，论文和教材默认按物理页；无法确定时交给读者选择。",
        "物理页模式通过 PDF.js 直接渲染页面，不再把学术文档压成重排正文；搜索高亮和图谱溯源仍然保留。",
        "章节识别优先使用 EPUB 导航、PDF 大纲和页面布局证据，再进入兜底切分，减少把目录页、引用、页码和被引用书目误认成章节。",
        "阅读器不等完整图谱：当前正文和首份图谱并行加载，全文搜索在服务端完成，后续图谱只传新增章节的差量。",
        "密集图谱切到 WebGL。普通大图只在限定时间内布局后冻结；超大图使用静态配置，保留全部节点与连线，同时停止持续重排。",
        "标签采用有上限的碰撞避让：重要实体优先，放大后补回更多局部名称，搜索到和选中的实体始终保留显示资格。",
        "关系详情按“来源实体 → 关系 → 目标实体”呈现，实体类型不区分大小写；单章抽取失败后可以直接重试，不用重建整本书。"
      ],
      conclusionsHeading: "因此：",
      conclusions: [
        "学术 PDF 不会再失去承载含义的页面结构，也不会只剩一墙抽取文字。",
        "按页阅读仍然支持搜索、阅读进度、图谱抽取和跳回原文。",
        "All Chapters 仍保留每个已抽取节点和每条关系；渲染器只控制当前缩放级别画出哪些名字。",
        "主抽取服务始终先尝试；OpenRouter 只是在主服务失败后的可选后备。",
        "抽取和图谱传输在后台继续时，阅读器仍然可以使用。"
      ],
      importantLabel: "一个重要细节：",
      importantDetail: "图谱概览变干净，不代表数据被删了。标签选择只决定当前镜头下画出哪些名字；搜索目标和选中实体仍然可见，放大后会出现更多名称，完整的节点与连线拓扑始终保留。",
      validationHeading: "验证",
      validation: [
        "前端 59 项单元测试全部通过，生产构建完成；入口包实测 223,992 字节，低于 307,200 字节上限。",
        "超大图浏览器场景固定包含 5,000 个节点和 20,000 条关系，并检查范围切换、搜索、最大化与恢复、拖拽和连续 12 次滚轮输入。",
        "标准 WebGL 场景包含 600 个节点和 1,200 条关系，并检查布局期间连线可见、最终坐标冻结、标签不碰撞、枢纽强调与语义缩放。",
        "首页把阅读器、PDF.js、WebGL 和更新详情保留在懒加载路由中，入口包继续遵守 300 KiB 的原始体积预算。"
      ],
      backHome: "返回 PageAndNode",
      timelineLabel: "更新记录"
    }
  }
]
