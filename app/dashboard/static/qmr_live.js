async function qmrLivePage(){
  const d=await api("/qmr/live-signals?limit=100");
  const rows=(d.items||[]).map(x=>`<tr><td>${fmt(x.signal_time)}</td><td><a href="/dashboard/qmr-live/${encodeURIComponent(x.signal_id)}"><b>${esc(x.symbol)}</b></a><div class="muted">${esc(x.signal_id)}</div></td><td>${x.signal_price}</td><td>${x.buy_score}</td><td>${x.latest_price??"—"}</td><td>${tag(x.signal_level)}</td><td>${tag(x.status)}</td><td>${tag(x.signal_mode)}</td></tr>`);
  content.innerHTML=`<section class="card"><h2>${locale==="zh-CN"?"QMR 实盘与研究信号":"QMR Live and Research Signals"}</h2><p class="muted">${locale==="zh-CN"?"正式与研究信号严格由最新回测策略状态决定。":"Live versus research mode is controlled by the latest backtest status."}</p>${table(locale==="zh-CN"?["时间","股票 / Signal ID","信号价","买入评分","当前","等级","状态","模式"]:["Time","Symbol / Signal ID","Signal Price","Buy Score","Latest","Level","Status","Mode"],rows,locale==="zh-CN"?"暂无 QMR 实盘信号":"No QMR live signals","")}</section>`;
}

async function qmrLiveDetail(){
  const id=decodeURIComponent(location.pathname.split("/").pop());
  const d=await api(`/qmr/live-signals/${encodeURIComponent(id)}`),x=d.signal;
  const rows=(d.performance||[]).map(p=>`<tr><td>${p.window_days}D</td><td>${p.completed?"✓":"—"}</td><td>${p.return_pct??"—"}</td><td>${p.mfe_pct??"—"}</td><td>${p.mae_pct??"—"}</td><td>${p.case_label??"—"}</td></tr>`);
  content.innerHTML=`<div class="grid metrics">${metric("Signal ID",x.signal_id)}${metric("Symbol",x.symbol)}${metric(locale==="zh-CN"?"等级":"Level",x.signal_level)}${metric(locale==="zh-CN"?"状态":"Status",x.status)}</div><div class="grid metrics">${metric("Quality",x.quality_score)}${metric("Mispricing",x.mispricing_score)}${metric("Recovery",x.recovery_score)}${metric("Buy Score",x.buy_score)}</div><section class="card"><h2>${locale==="zh-CN"?"表现跟踪":"Performance Tracking"}</h2>${table(["Window","Completed","Return %","MFE %","MAE %","Case"],rows,locale==="zh-CN"?"尚无已闭合日线可跟踪":"No closed daily bars to track","")}</section><section class="card"><h2>${locale==="zh-CN"?"历史相似样本与快照":"Historical Matches and Snapshot"}</h2><pre>${esc(JSON.stringify({similar:x.similar_statistics_json,snapshot:x.signal_snapshot_json,feedback:d.feedback},null,2))}</pre></section>`;
}
