# Feature Catalog

所有条目版本均为`1.0.0`，输出类型除`trend_alignment`为TEXT外均为DECIMAL；通用周期为`1m/5m/15m/30m/60m/1d`，VWAP仅分钟周期。预热期内值为空且状态为`WARMUP`；必要输入或参考数据缺失时为`MISSING`，不使用0或未来值填充。

## 收益

|英文名称|中文名称|公式/参数|范围|预热|
|---|---|---|---|---|
|return_1, return_5, return_10, return_20|1/5/10/20周期收益率|`close/close.shift(n)-1`|理论`>-1`，异常价格除外|2/6/11/21|
|log_return_1|单周期对数收益率|`ln(close/close.shift(1))`|实数|2|

## 趋势

|英文名称|中文名称|公式/参数|范围|预热|
|---|---|---|---|---|
|sma_5, sma_10, sma_20, sma_50, sma_200|简单移动均线|过去n根收盘均值|非负价格|5/10/20/50/200|
|ema_5, ema_10, ema_20, ema_50, ema_60, ema_200|指数移动均线|`ewm(span=n, adjust=False)`|非负价格|5/10/20/50/60/200|
|close_vs_ema20_pct, close_vs_ema60_pct|收盘价距离EMA|`(close/EMA-1)*100`|实数百分比|20/60|
|ema20_vs_ema60_pct|EMA20距离EMA60|`(EMA20/EMA60-1)*100`|实数百分比|60|
|close_vs_sma20_pct|收盘价距离SMA20|`(close/SMA20-1)*100`|实数百分比|20|
|ema20_slope_5, ema60_slope_5|EMA五周期斜率|`EMA/EMA.shift(5)-1`|实数|25/65|
|trend_alignment|趋势排列|比较close、EMA20、EMA60、EMA200|STRONG_BULL/BULL/MIXED/BEAR/STRONG_BEAR/UNKNOWN|200|

## 动量

|英文名称|中文名称|公式/参数|范围|预热|
|---|---|---|---|---|
|rsi_14|RSI14|Wilder增减幅平滑|0至100|15|
|macd_line_12_26|MACD线|EMA12-EMA26|实数|26|
|macd_signal_9|MACD信号线|MACD的EMA9|实数|34|
|macd_histogram|MACD柱|MACD线-信号线|实数|34|
|roc_10, roc_20|变化率|`(close/close.shift(n)-1)*100`|实数百分比|11/21|

## 波动率

|英文名称|中文名称|公式/参数|范围|预热|
|---|---|---|---|---|
|true_range|真实波幅|max(high-low, abs(high-prevClose), abs(low-prevClose))|非负|2|
|atr_14|ATR14|True Range的Wilder平滑|非负|15|
|atr_pct_14|ATR百分比|`ATR14/close*100`|通常非负|15|
|realized_volatility_20|20周期实现波动率|对数收益标准差乘周期年化因子|非负|21|
|bollinger_mid_20|布林中轨|SMA20|价格|20|
|bollinger_upper_20_2, bollinger_lower_20_2|布林上下轨|SMA20 ± 2倍总体标准差|价格|20|
|bollinger_width_pct|布林带宽|`(upper-lower)/mid*100`|通常非负|20|
|bollinger_position|布林位置|`(close-lower)/(upper-lower)`|实数；零宽度为MISSING|20|

实现波动率年化按每年252个交易日、正常盘分钟数390折算：1d=252、60m=1638、15m=6552、5m=19656、1m=98280。

## 成交量、成交额与VWAP

|英文名称|中文名称|公式/参数|范围|预热|周期/缺失行为|
|---|---|---|---|---|---|
|volume_sma_5, volume_sma_20, volume_sma_50|成交量均值|过去n根volume均值|非负|5/20/50|通用；volume缺失为MISSING|
|volume_ratio_20|成交量比率|当前volume/前20根volume均值|非负|21|基准排除当前K线|
|turnover_sma_20|成交额均值|过去20根turnover均值|非负|20|turnover缺失为MISSING|
|session_vwap_regular|正常盘日内VWAP|日内累计typical price×volume/累计volume|价格|1|仅分钟、REGULAR，按交易日重置；零量为MISSING|
|close_vs_vwap_pct|收盘价距离VWAP|`(close/VWAP-1)*100`|实数百分比|1|仅分钟，VWAP缺失则MISSING|

## 跳空与价格行为

|英文名称|中文名称|公式|范围|预热|
|---|---|---|---|---|
|gap_open_pct|开盘跳空|日线`open/前收-1`；分钟继承当日正常盘开盘相对前日正常盘收盘|实数|2|
|body_range_ratio|实体比例|`abs(close-open)/(high-low)`|0至1；零振幅MISSING|1|
|upper_wick_ratio|上影比例|`(high-max(open,close))/(high-low)`|0至1；零振幅MISSING|1|
|lower_wick_ratio|下影比例|`(min(open,close)-low)/(high-low)`|0至1；零振幅MISSING|1|
|close_location_value|收盘位置|`(close-low)/(high-low)`|0至1；零振幅MISSING|1|

## 高低点、突破与回撤

|英文名称|中文名称|公式|预热|
|---|---|---|---|
|distance_from_high_20_pct, distance_from_high_60_pct, distance_from_high_252_pct|距离滚动高点|`(close/过去n根含当前最高价-1)*100`|20/60/252|
|distance_from_low_20_pct, distance_from_low_60_pct|距离滚动低点|`(close/过去n根含当前最低价-1)*100`|20/60|
|breakout_high_20_pct, breakout_high_60_pct|突破前期高点距离|`(close/前n根最高价-1)*100`，阈值排除当前K线|21/61|
|drawdown_from_20_high_pct, drawdown_from_60_high_pct, drawdown_from_252_high_pct|高点回撤|`(close/过去n根含当前最高价-1)*100`|20/60/252|

全部输出为实数百分比。窗口输入不足为WARMUP。

## 相对强弱

|英文名称|中文名称|公式/参数|预热|参考|
|---|---|---|---|---|
|relative_return_qqq_5, relative_return_qqq_20, relative_return_qqq_60|相对QQQ收益|本标的n期收益-QQQ同时间戳n期收益|6/21/61|US.QQQ|
|relative_ratio_qqq|相对QQQ价格比率|本标的close/QQQ close|1|US.QQQ|
|relative_ratio_qqq_ema20|相对比率EMA20|相对比率的EMA20，adjust=False|20|US.QQQ|
|relative_ratio_vs_ema20_pct|相对比率距离EMA20|`(ratio/ratioEMA20-1)*100`|20|US.QQQ|
|relative_return_soxx_20|相对SOXX收益20|本标的20期收益-SOXX同时间戳20期收益|21|US.SOXX，可选|

参考标的必须周期、UTC时间戳和数据源语义一致，只做精确对齐；参考缺失即MISSING。

## 市场环境

|英文名称|中文名称|公式/参数|预热|参考|
|---|---|---|---|---|
|market_qqq_return_1, market_qqq_return_5|QQQ市场收益|QQQ同时间戳1/5期收益|2/6|US.QQQ|
|market_qqq_close_vs_ema20_pct|QQQ距离EMA20|QQQ `(close/EMA20-1)*100`|20|US.QQQ|
|market_qqq_atr_pct_14|QQQ ATR百分比|QQQ Wilder ATR14/close×100|15|US.QQQ|
|market_soxx_return_5|SOXX市场收益5|SOXX同时间戳5期收益|6|US.SOXX|
|market_soxx_close_vs_ema20_pct|SOXX距离EMA20|SOXX `(close/EMA20-1)*100`|20|US.SOXX|

市场环境条目只输出环境数值，不定义牛熊状态或交易决策。
