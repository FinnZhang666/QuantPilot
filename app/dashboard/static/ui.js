(function () {
  "use strict";

  const copy = {
    "zh-CN": {
      tagline: "陪你把每一笔交易做完",
      "nav.workspace": "🏠 工作台", "nav.home": "工作台", "nav.market": "📈 市场",
      "nav.regime": "市场状态", "nav.marketMonitor": "市场监控", "nav.universe": "股票池", "nav.qmr": "优质错杀", "nav.candidates": "候选池",
      "nav.strategy": "📊 策略", "nav.plans": "交易计划", "nav.paperPositions": "我的持仓",
      "nav.tradeReviews": "交易复盘", "nav.scoreboard": "策略成绩榜", "nav.ai": "🤖 AI",
      "nav.companion": "AI 交易解读", "nav.aiReviews": "AI 策略复盘", "nav.telegram": "Telegram 预览",
      "nav.product": "📱 产品运营", "nav.feedback": "用户反馈", "nav.behavior": "用户行为",
      "nav.botStats": "Bot 统计", "nav.userIntelligence": "用户洞察", "nav.lab": "🧪 Strategy Lab",
      "nav.experiments": "策略实验", "nav.parameters": "参数比较", "nav.researchCenter": "研究中心",
      "nav.more": "⚙ 更多", "nav.system": "版本中心", "nav.systemMonitor": "系统监控", "nav.logs": "运行日志",
      "action.logout": "退出登录", "workspace.eyebrow": "TRADE COMPANION 工作台",
      "workspace.admin": "管理员",
      "state.loading": "正在读取本地数据…", "footer.boundary": "研究与交易生命周期工作台 · 不提供自动下单",
      "action.refresh": "刷新页面", "action.filter": "筛选", "action.search": "搜索",
      "state.empty": "当前没有可显示的数据。", "state.notAvailable": "暂不可用",
    },
    "en-US": {
      tagline: "Your AI Trade Companion",
      "nav.workspace": "🏠 Workspace", "nav.home": "Dashboard", "nav.market": "📈 Market",
      "nav.regime": "Market Regime", "nav.marketMonitor": "Market Monitor", "nav.universe": "Universe", "nav.qmr": "Quality Mispricing", "nav.candidates": "Candidate Pool",
      "nav.strategy": "📊 Strategy", "nav.plans": "Trade Plans", "nav.paperPositions": "My Positions",
      "nav.tradeReviews": "Trade Reviews", "nav.scoreboard": "Strategy Scoreboard", "nav.ai": "🤖 AI",
      "nav.companion": "AI Trade Interpretation", "nav.aiReviews": "AI Strategy Review", "nav.telegram": "Telegram Preview",
      "nav.product": "📱 Product Operations", "nav.feedback": "User Feedback", "nav.behavior": "User Behavior",
      "nav.botStats": "Bot Statistics", "nav.userIntelligence": "User Intelligence", "nav.lab": "🧪 Strategy Lab",
      "nav.experiments": "Strategy Experiments", "nav.parameters": "Parameter Comparison", "nav.researchCenter": "Research Center",
      "nav.more": "⚙ More", "nav.system": "Version Center", "nav.systemMonitor": "System Monitor", "nav.logs": "Runtime Logs",
      "action.logout": "Sign out", "workspace.eyebrow": "TRADE COMPANION WORKSPACE",
      "workspace.admin": "Administrator",
      "state.loading": "Loading local data…", "footer.boundary": "Trade research lifecycle workspace · No automatic order submission",
      "action.refresh": "Refresh", "action.filter": "Filter", "action.search": "Search",
      "state.empty": "No data is currently available.", "state.notAvailable": "Not available",
    },
  };

  const pageTitles = {
    "zh-CN": {
      home: "工作台", universe: "股票池", qmr: "优质错杀", "qmr-detail": "评分拆解", opportunities: "交易机会", "opportunity-detail": "机会详情",
      "trade-plans": "交易计划", "trade-plan-detail": "交易计划详情", positions: "我的持仓计划",
      "position-detail": "持仓计划详情", portfolios: "投资组合", "portfolio-detail": "投资组合详情",
      "holding-detail": "持仓详情", "market-snapshots": "市场快照", "market-snapshot-detail": "快照详情",
      "symbol-overview": "股票概览", "telegram-preview": "Telegram 预览", "watchlist-snapshot": "关注列表快照",
      "trade-reviews": "交易复盘", "trade-review-detail": "交易复盘详情", companion: "AI 交易助手",
      "companion-detail": "AI 分析详情", "market-regime": "市场状态", candidates: "候选池",
      "candidate-detail": "候选详情", reviews: "机会复盘", "review-detail": "机会复盘详情",
      "ai-reviews": "AI 复盘分析", "ai-review-detail": "AI 复盘详情", research: "研究中心",
      "research-detail": "研究工作区", runtime: "运行状态", strategies: "策略观察",
      "strategy-detail": "策略详情", "data-quality": "数据质量", reports: "历史报告",
      development: "开发看板", "development-detail": "Issue 详情", system: "版本中心",
      "market-monitor": "市场监控", "paper-positions": "我的持仓", "strategy-scoreboard": "策略成绩榜",
      "product-feedback": "用户反馈", "product-behavior": "用户行为", "bot-statistics": "Bot 统计",
      "user-intelligence": "用户洞察", "strategy-parameters": "参数比较", "system-monitor": "系统监控",
      "runtime-logs": "运行日志",
    },
    "en-US": {
      home: "Dashboard", universe: "Universe", qmr: "Quality & Mispricing", "qmr-detail": "Score Breakdown", opportunities: "Opportunities", "opportunity-detail": "Opportunity Details",
      "trade-plans": "Trade Plans", "trade-plan-detail": "Trade Plan Details", positions: "My Position Plans",
      "position-detail": "Position Plan Details", portfolios: "Portfolio Center", "portfolio-detail": "Portfolio Details",
      "holding-detail": "Holding Details", "market-snapshots": "Market Snapshot", "market-snapshot-detail": "Snapshot Details",
      "symbol-overview": "Symbol Overview", "telegram-preview": "Telegram Preview", "watchlist-snapshot": "Watchlist Snapshot",
      "trade-reviews": "Trade Reviews", "trade-review-detail": "Trade Review Details", companion: "AI Companion",
      "companion-detail": "AI Analysis Details", "market-regime": "Market Regime", candidates: "Candidate Pool",
      "candidate-detail": "Candidate Details", reviews: "Opportunity Reviews", "review-detail": "Opportunity Review Details",
      "ai-reviews": "AI Review Analysis", "ai-review-detail": "AI Review Details", research: "Research Center",
      "research-detail": "Research Workspace", runtime: "Runtime", strategies: "Strategy Monitor",
      "strategy-detail": "Strategy Details", "data-quality": "Data Quality", reports: "Reports",
      development: "Development Board", "development-detail": "Issue Details", system: "Version Center",
      "market-monitor": "Market Monitor", "paper-positions": "My Positions", "strategy-scoreboard": "Strategy Scoreboard",
      "product-feedback": "User Feedback", "product-behavior": "User Behavior", "bot-statistics": "Bot Statistics",
      "user-intelligence": "User Intelligence", "strategy-parameters": "Parameter Comparison", "system-monitor": "System Monitor",
      "runtime-logs": "Runtime Logs",
    },
  };

  const statusCopy = {
    "zh-CN": {CONNECTED:"已连接",RUNNING:"运行中",ACTIVE:"有效",NOTIFIED:"已通知",COMPLETED:"已完成",DEGRADED:"降级",DETECTED:"已发现",INBOX:"待处理",OPEN:"开放",INVESTIGATING:"处理中",IN_PROGRESS:"处理中",PLANNED:"已规划",RELEASED:"已发布",WAITING_APPROVAL:"等待批准",FAILED:"失败",ERROR:"错误",WARNING:"警告",INVALID:"无效",INVALIDATED:"已失效",REJECTED:"已拒绝",CANCELLED:"已取消",EXPIRED:"已过期",STOPPED:"已停止",STALE:"状态过期",DISCONNECTED:"已断开",DISABLED:"未启用",VALID:"正常",WARMUP:"预热中",MISSING_FEATURE:"缺少特征",INSUFFICIENT_DATA:"数据不足",NO_SIGNAL:"暂无信号",LONG:"做多",SHORT:"做空",HIGH:"高",MEDIUM:"中",LOW:"低",CRITICAL:"紧急",UNKNOWN:"未知",NO_DATA:"无数据",PLAN:"计划中",COMPANION:"陪伴中",REVIEW:"复盘中",READY:"已就绪",CLOSED:"已关闭",WATCH:"观察中",PENDING:"待处理",NONE:"无",HOLDING:"持有中",NOT_HOLDING:"未持有",WATCHING:"关注中",NOT_WATCHING:"未关注",NEUTRAL:"中性",BULLISH:"偏多",BEARISH:"偏空"},
    "en-US": {CONNECTED:"Connected",RUNNING:"Running",ACTIVE:"Active",NOTIFIED:"Notified",COMPLETED:"Completed",DEGRADED:"Degraded",DETECTED:"Detected",INBOX:"Inbox",OPEN:"Open",INVESTIGATING:"In progress",IN_PROGRESS:"In progress",PLANNED:"Planned",RELEASED:"Released",WAITING_APPROVAL:"Waiting approval",FAILED:"Failed",ERROR:"Error",WARNING:"Warning",INVALID:"Invalid",INVALIDATED:"Invalidated",REJECTED:"Rejected",CANCELLED:"Cancelled",EXPIRED:"Expired",STOPPED:"Stopped",STALE:"Stale",DISCONNECTED:"Disconnected",DISABLED:"Disabled",VALID:"Valid",WARMUP:"Warming up",MISSING_FEATURE:"Missing feature",INSUFFICIENT_DATA:"Insufficient data",NO_SIGNAL:"No signal",LONG:"Long",SHORT:"Short",HIGH:"High",MEDIUM:"Medium",LOW:"Low",CRITICAL:"Critical",UNKNOWN:"Unknown",NO_DATA:"No data",PLAN:"Plan",COMPANION:"Companion",REVIEW:"Review",READY:"Ready",CLOSED:"Closed",WATCH:"Watch",PENDING:"Pending",NONE:"None",HOLDING:"Holding",NOT_HOLDING:"Not holding",WATCHING:"Watching",NOT_WATCHING:"Not watching",NEUTRAL:"Neutral",BULLISH:"Bullish",BEARISH:"Bearish"},
  };

  Object.assign(statusCopy["zh-CN"], {WAIT_FOR_CONFIRMATION:"等待确认",SMALL_PROBE:"小仓试探",SMALL_POSITION:"小仓介入",CONSIDER_ENTRY:"考虑介入",PROTECT_PROFIT:"保护利润",REDUCE_POSITION:"考虑减仓",EXIT_POSITION:"考虑退出",DATA_INSUFFICIENT:"数据不足",QUALITY_MISPRICING_CANDIDATE:"优质错杀候选",EARLY_ENTRY:"早期介入",CONFIRMED_ENTRY:"确认介入",STRONG_ENTRY:"强确认",PROTECT:"保护利润",REDUCE:"减仓",EXIT:"退出"});
  Object.assign(statusCopy["en-US"], {WAIT_FOR_CONFIRMATION:"Wait for confirmation",SMALL_PROBE:"Small probe",SMALL_POSITION:"Small position",CONSIDER_ENTRY:"Consider entry",PROTECT_PROFIT:"Protect profits",REDUCE_POSITION:"Consider reducing",EXIT_POSITION:"Consider exit",DATA_INSUFFICIENT:"Insufficient data",QUALITY_MISPRICING_CANDIDATE:"Quality mispricing candidate",EARLY_ENTRY:"Early entry",CONFIRMED_ENTRY:"Confirmed entry",STRONG_ENTRY:"Strong entry",PROTECT:"Protect",REDUCE:"Reduce",EXIT:"Exit"});
  const supported = new Set(["zh-CN", "en-US"]);
  let locale = localStorage.getItem("tc-dashboard-language") || "zh-CN";
  if (!supported.has(locale)) locale = "zh-CN";
  const t = (key) => (copy[locale] && copy[locale][key]) || key;

  function applyLanguage() {
    document.documentElement.lang = locale;
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-label-key]").forEach((node) => {
      const label = t(node.dataset.labelKey);
      const target = node.querySelector("b");
      if (target) target.textContent = label;
      node.title = label;
    });
    const page = document.body.dataset.page;
    const title = pageTitles[locale][page] || (locale === "zh-CN" ? "工作台" : "Dashboard");
    const heading = document.querySelector("#page-title");
    if (heading) heading.textContent = title;
    document.title = `Trade Companion · ${title}`;
    const select = document.querySelector("#language-select");
    if (select) select.value = locale;
  }

  function setLocale(value) {
    if (!supported.has(value)) return;
    localStorage.setItem("tc-dashboard-language", value);
    location.reload();
  }

  function configureShell() {
    applyLanguage();
    document.querySelector("#language-select")?.addEventListener("change", (event) => setLocale(event.target.value));
    document.querySelector("#refresh-page")?.addEventListener("click", () => location.reload());
    const sidebar = document.querySelector("#sidebar");
    const backdrop = document.querySelector("#sidebar-backdrop");
    const collapsed = localStorage.getItem("tc-sidebar-collapsed") === "true";
    if (collapsed) document.body.classList.add("sidebar-collapsed");
    document.querySelector("#sidebar-toggle")?.addEventListener("click", () => {
      document.body.classList.toggle("sidebar-collapsed");
      localStorage.setItem("tc-sidebar-collapsed", String(document.body.classList.contains("sidebar-collapsed")));
    });
    document.querySelector("#mobile-menu")?.addEventListener("click", () => document.body.classList.add("sidebar-open"));
    document.querySelectorAll(".nav-group-toggle").forEach((button) => {
      const group = button.closest(".nav-group");
      const key = `tc-nav-group-${button.dataset.group}`;
      const isClosed = localStorage.getItem(key) === "closed";
      group.classList.toggle("collapsed", isClosed);
      button.setAttribute("aria-expanded", String(!isClosed));
      button.addEventListener("click", () => {
        const closed = group.classList.toggle("collapsed");
        button.setAttribute("aria-expanded", String(!closed));
        localStorage.setItem(key, closed ? "closed" : "open");
      });
    });
    backdrop?.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
    sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => document.body.classList.remove("sidebar-open")));
    window.setInterval(() => {
      const value = new Intl.DateTimeFormat(locale, {timeZone:"America/New_York",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}).format(new Date());
      const clock = document.querySelector("#market-clock"); if (clock) clock.textContent = `ET ${value}`;
    }, 1000);
  }

  window.TCUI = { copy, pageTitles, statusCopy, get locale(){ return locale; }, t, setLocale, applyLanguage, configureShell };
  if (document.querySelector("#sidebar")) configureShell();
}());
