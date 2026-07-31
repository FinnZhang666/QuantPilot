(function () {
  "use strict";

  const copy = {
    "zh-CN": {
      tagline: "陪你把每一笔交易做完",
      "nav.workspace": "工作台", "nav.home": "工作台", "nav.market": "市场洞察",
      "nav.snapshots": "市场快照", "nav.regime": "市场状态", "nav.candidates": "候选池",
      "nav.opportunities": "交易机会", "nav.planning": "交易计划", "nav.plans": "交易计划",
      "nav.positions": "我的持仓计划", "nav.investment": "投资组合", "nav.portfolios": "投资组合",
      "nav.research": "研究与复盘", "nav.tradeReviews": "交易复盘", "nav.opportunityReviews": "机会复盘",
      "nav.aiReviews": "AI 复盘分析", "nav.researchCenter": "研究中心", "nav.ai": "AI 助手",
      "nav.companion": "AI 交易助手", "nav.telegram": "Telegram 预览", "nav.operations": "运营工具",
      "nav.runtime": "运行状态", "nav.strategies": "策略观察", "nav.quality": "数据质量",
      "nav.reports": "历史报告", "nav.development": "开发看板", "nav.more": "更多",
      "nav.system": "版本中心", "action.logout": "退出登录", "workspace.eyebrow": "TRADE COMPANION 工作台",
      "state.loading": "正在读取本地数据…", "footer.boundary": "研究与交易生命周期工作台 · 不提供自动下单",
      "action.refresh": "刷新页面", "action.filter": "筛选", "action.search": "搜索",
      "state.empty": "当前没有可显示的数据。", "state.notAvailable": "暂不可用",
    },
    "en-US": {
      tagline: "Your AI Trade Companion",
      "nav.workspace": "Workspace", "nav.home": "Dashboard", "nav.market": "Market Intelligence",
      "nav.snapshots": "Market Snapshot", "nav.regime": "Market Regime", "nav.candidates": "Candidate Pool",
      "nav.opportunities": "Opportunities", "nav.planning": "Trade Planning", "nav.plans": "Trade Plans",
      "nav.positions": "My Position Plans", "nav.investment": "Portfolio", "nav.portfolios": "Portfolio Center",
      "nav.research": "Research & Review", "nav.tradeReviews": "Trade Reviews", "nav.opportunityReviews": "Opportunity Reviews",
      "nav.aiReviews": "AI Review Analysis", "nav.researchCenter": "Research Center", "nav.ai": "AI Companion",
      "nav.companion": "AI Trade Companion", "nav.telegram": "Telegram Preview", "nav.operations": "Operations",
      "nav.runtime": "Runtime", "nav.strategies": "Strategies", "nav.quality": "Data Quality",
      "nav.reports": "Reports", "nav.development": "Development", "nav.more": "More",
      "nav.system": "Version Center", "action.logout": "Sign out", "workspace.eyebrow": "TRADE COMPANION WORKSPACE",
      "state.loading": "Loading local data…", "footer.boundary": "Trade research lifecycle workspace · No automatic order submission",
      "action.refresh": "Refresh", "action.filter": "Filter", "action.search": "Search",
      "state.empty": "No data is currently available.", "state.notAvailable": "Not available",
    },
  };

  const pageTitles = {
    "zh-CN": {
      home: "工作台", opportunities: "交易机会", "opportunity-detail": "机会详情",
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
    },
    "en-US": {
      home: "Dashboard", opportunities: "Opportunities", "opportunity-detail": "Opportunity Details",
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
    },
  };

  const statusCopy = {
    "zh-CN": {CONNECTED:"已连接",RUNNING:"运行中",ACTIVE:"有效",NOTIFIED:"已通知",COMPLETED:"已完成",DEGRADED:"降级",DETECTED:"已发现",INBOX:"待处理",WAITING_APPROVAL:"等待批准",FAILED:"失败",INVALIDATED:"已失效",REJECTED:"已拒绝",EXPIRED:"已过期",STOPPED:"已停止",DISCONNECTED:"已断开",DISABLED:"未启用",VALID:"正常",WARMUP:"预热中",MISSING_FEATURE:"缺少特征",INSUFFICIENT_DATA:"数据不足",NO_SIGNAL:"暂无信号",LONG:"做多",SHORT:"做空",HIGH:"高",MEDIUM:"中",LOW:"低",CRITICAL:"紧急",UNKNOWN:"未知",NO_DATA:"无数据"},
    "en-US": {CONNECTED:"Connected",RUNNING:"Running",ACTIVE:"Active",NOTIFIED:"Notified",COMPLETED:"Completed",DEGRADED:"Degraded",DETECTED:"Detected",INBOX:"Inbox",WAITING_APPROVAL:"Waiting approval",FAILED:"Failed",INVALIDATED:"Invalidated",REJECTED:"Rejected",EXPIRED:"Expired",STOPPED:"Stopped",DISCONNECTED:"Disconnected",DISABLED:"Disabled",VALID:"Valid",WARMUP:"Warming up",MISSING_FEATURE:"Missing feature",INSUFFICIENT_DATA:"Insufficient data",NO_SIGNAL:"No signal",LONG:"Long",SHORT:"Short",HIGH:"High",MEDIUM:"Medium",LOW:"Low",CRITICAL:"Critical",UNKNOWN:"Unknown",NO_DATA:"No data"},
  };

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
