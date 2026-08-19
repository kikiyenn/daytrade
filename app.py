import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import plotly.graph_objects as go
from fugle_marketdata import RestClient 
from streamlit_autorefresh import st_autorefresh 
import textwrap

# ==========================================
# 🔑 請貼上你的 Fugle API Key
FUGLE_API_KEY = "N2MxMDFmZjUtMzQ4My00Y2RhLTg4ZjgtYTUzNTkzOGVjZTBiIGQ5NzFmYjFlLWFlZjctNDBkNC1hYjAzLTUzNmIzNzljZWZmMg==" 
# ==========================================

st.set_page_config(page_title="專業當沖看盤系統", layout="wide")

hide_default_format = """
<style>
#MainMenu {visibility: hidden; }
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_default_format, unsafe_allow_html=True)

st.sidebar.title("⚙️ 交易設定")
stock_symbol = st.sidebar.text_input("輸入台股代號 (例如: 3037, 2330)", value="3037")

if FUGLE_API_KEY != "YOUR_FUGLE_API_KEY":
    use_realtime = True
    st_autorefresh(interval=3000, limit=None, key="realtime_refresh")
    st.sidebar.success("⚡ Fugle 零延遲報價 (每 3 秒自動更新)")
else:
    use_realtime = False
    st.sidebar.error("❌ 未設定 Fugle API Key，目前使用 Yahoo 延遲報價")

def calculate_td9(df):
    df['TD_Setup'] = 0
    td_count = 0
    for i in range(4, len(df)):
        current_close = df['Close'].iloc[i]
        compare_close = df['Close'].iloc[i-4]
        if current_close > compare_close:
            td_count = td_count + 1 if td_count > 0 else 1
        elif current_close < compare_close:
            td_count = td_count - 1 if td_count < 0 else -1
        else:
            td_count = 0
            
        df.iloc[i, df.columns.get_loc('TD_Setup')] = td_count
        if td_count == 9 or td_count == -9:
            td_count = 0 
    return df

def calculate_indicators(df):
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA13'] = df['Close'].rolling(window=13).mean()
    
    df['20MA'] = df['Close'].rolling(window=20).mean()
    df['STD'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['20MA'] + (2 * df['STD'])
    df['BB_Lower'] = df['20MA'] - (2 * df['STD'])
    
    df['Signal'] = 0
    df.loc[(df['MA5'] > df['MA13']) & (df['MA5'].shift(1) <= df['MA13'].shift(1)), 'Signal'] = 1  
    df.loc[(df['MA5'] < df['MA13']) & (df['MA5'].shift(1) >= df['MA13'].shift(1)), 'Signal'] = -1 
    
    df = calculate_td9(df)
    return df

@st.cache_data(ttl=600)
def get_historical_data(symbol):
    end_date = datetime.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=90) 
    ticker = f"{symbol}.TW"
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if df.empty:
        ticker = f"{symbol}.TWO"
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
        
    if not df.empty:
        df = calculate_indicators(df)
    return df

def get_realtime_price(symbol, use_rt):
    if use_rt:
        try:
            client = RestClient(api_key=FUGLE_API_KEY)
            stock = client.stock
            raw_quote = stock.intraday.quote(symbol=symbol)
            
            q = raw_quote
            if 'data' in q:
                q = q['data']
            if 'quote' in q:
                q = q['quote']
            
            # 🌟 新增：自動抓取股票中文名稱
            name = q.get('name', '')
            
            vol = q.get('total', {}).get('tradeVolume')
            if vol is None:
                vol = q.get('volume', q.get('tradeVolume'))
                
            close_price = q.get('closePrice', q.get('close', q.get('lastPrice')))
            high = q.get('highPrice', q.get('high'))
            low = q.get('lowPrice', q.get('low'))
            open_p = q.get('openPrice', q.get('open'))
            
            return close_price, high, low, open_p, vol, name
        except Exception as e:
            st.sidebar.error(f"⚠️ 富果連線異常: {e}")
            return None, None, None, None, None, ""
    return None, None, None, None, None, ""

def calculate_day_trade_score(price_change_pct, amplitude, volume_lots, current_price, ma5, cdp):
    score = 0
    if price_change_pct >= 7: score += 30
    elif price_change_pct >= 4: score += 20
    elif price_change_pct >= 1: score += 10
    elif price_change_pct > 0: score += 5
    
    if amplitude >= 8: score += 30
    elif amplitude >= 5: score += 20
    elif amplitude >= 3: score += 10
    
    if volume_lots >= 10000: score += 20
    elif volume_lots >= 5000: score += 15
    elif volume_lots >= 2000: score += 10
    elif volume_lots >= 500: score += 5
    
    if current_price > ma5: score += 10
    if current_price > cdp: score += 10
    return min(score, 100) 

try:
    df = get_historical_data(stock_symbol)
    
    if not df.empty and len(df) >= 5:
        yesterday_data = df.iloc[-2]
        today_data = df.iloc[-1]
        
        rt_close, rt_high, rt_low, rt_open, rt_vol, stock_name = get_realtime_price(stock_symbol, use_realtime)
        
        if rt_close is not None:
            data_source = "Fugle 即時"
            current_price = rt_close
            current_high = rt_high
            current_low = rt_low
            current_open = rt_open
            current_vol = rt_vol if rt_vol else 0
            display_name = stock_name if stock_name else ""
        else:
            data_source = "Yahoo 延遲"
            current_price = float(today_data['Close'])
            current_high = float(today_data['High'])
            current_low = float(today_data['Low'])
            current_open = float(today_data['Open'])
            current_vol = float(today_data['Volume']) if not pd.isna(today_data['Volume']) else 0
            display_name = ""

        # 🌟 終極修正：直接使用 API 給的數字，絕對不再擅自除以 1000
        volume_in_lots = int(current_vol)
        
        yesterday_close = float(yesterday_data['Close'])
        price_change = current_price - yesterday_close
        price_change_pct = (price_change / yesterday_close) * 100
        
        amplitude = ((current_high - current_low) / yesterday_close) * 100
        ma5_val = float(yesterday_data['MA5'])
        ma13_val = float(yesterday_data['MA13'])
        
        ma5_trend = "▲" if ma5_val > df.iloc[-3]['MA5'] else "▼"
        ma13_trend = "▲" if ma13_val > df.iloc[-3]['MA13'] else "▼"
        
        y_high, y_low, y_close = float(yesterday_data['High']), float(yesterday_data['Low']), yesterday_close
        cdp = (y_high + y_low + 2 * y_close) / 4
        ah = cdp + (y_high - y_low)   
        nh = 2 * cdp - y_low          
        nl = 2 * cdp - y_high         
        al = cdp - (y_high - y_low)   
        
        dt_score = calculate_day_trade_score(price_change_pct, amplitude, volume_in_lots, current_price, ma5_val, cdp)
        
        if dt_score >= 80: score_color, score_label = "#E8385A", "🔥 極強"
        elif dt_score >= 60: score_color, score_label = "#F5A623", "⭐ 強勢"
        elif dt_score >= 40: score_color, score_label = "#7B7B7B", "🟡 震盪"
        else: score_color, score_label = "#16A34A", "❄️ 偏弱"
        
        def calc_pct(level, curr): return f"{((level - curr) / curr * 100):+.2f}%"

        current_time_str = datetime.now().strftime("%H:%M:%S")
        
        # 🌟 新增：在標題加入股票中文名稱 {display_name}
        header_html = textwrap.dedent(f"""
        <div style='display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;'>
            <div><h2 style='margin:0;'>{stock_symbol} {display_name} 即時行情 <span style='font-size:14px; opacity:0.6; font-weight:normal;'>(來源: {data_source} | 更新: {current_time_str})</span></h2></div>
            <div style='background-color: {score_color}; color: white; padding: 12px 25px; border-radius: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); display: flex; flex-direction: column; justify-content: center;'>
                <div style='font-size: 32px; font-weight: 900; line-height: 1;'>{dt_score} <span style='font-size: 16px; font-weight: normal;'>分</span></div>
                <div style='font-size: 14px; margin-top: 5px; font-weight: bold;'>{score_label}</div>
            </div>
        </div>
        """)
        st.markdown(header_html, unsafe_allow_html=True)
        
        col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1, 1, 1, 1, 1])
        with col1:
            color = "#E8385A" if price_change > 0 else "#16A34A" if price_change < 0 else "gray"
            st.markdown(f"<h1 style='color:{color}; margin-bottom:0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:{color};'>{price_change:+.2f} ({price_change_pct:+.2f}%)</span>", unsafe_allow_html=True)
        with col2: st.metric("開盤", f"{current_open:.2f}")
        with col3: st.metric("最高", f"{current_high:.2f}")
        with col4: st.metric("最低", f"{current_low:.2f}")
        with col5: st.metric("昨收", f"{yesterday_close:.2f}")
        with col6: 
            st.metric("成交量", f"{volume_in_lots:,} 張")
            st.markdown(f"<div style='font-size:14px; opacity:0.6; margin-top:-10px;'>震幅 {amplitude:.2f}%</div>", unsafe_allow_html=True)
        
        st.divider()
        
        col_cdp, col_strategy = st.columns([1, 1.2])
        
        with col_cdp:
            st.markdown("#### 📊 支撐壓力價位")
            hi_status, hi_color = ("突破強壓", "#E8385A") if current_high >= ah else ("突破壓力", "#F5A623") if current_high >= nh else ("突破中關", "#7B7B7B") if current_high >= cdp else ("中關之下", "gray")
            lo_status, lo_color = ("跌破強撐", "#2563EB") if current_low <= al else ("觸及支撐", "#16A34A") if current_low <= nl else ("跌破中關", "#7B7B7B") if current_low <= cdp else ("中關之上", "gray")
            
            cdp_html = textwrap.dedent(f"""
            <div style="border:1px solid rgba(128,128,128,0.3); padding:15px; border-radius:10px; background: rgba(128,128,128,0.05);">
                <div style="display:flex; justify-content:space-between; color:#E8385A; font-size:16px;"><b>🔴 強壓</b> <span><b>{ah:.2f}</b> <br><small style="float:right;">{calc_pct(ah, current_price)}</small></span></div><hr style="margin:8px 0; border-top: 1px solid rgba(128,128,128,0.2);">
                <div style="display:flex; justify-content:space-between; color:#F5A623; font-size:16px;"><b>🟡 壓力</b> <span><b>{nh:.2f}</b> <br><small style="float:right;">{calc_pct(nh, current_price)}</small></span></div><hr style="margin:8px 0; border-top: 1px solid rgba(128,128,128,0.2);">
                <div style="display:flex; justify-content:space-between; font-size:18px;"><b>➖ 中關價</b> <span><b>{cdp:.2f}</b> <br><small style="float:right; opacity:0.6;">多空分界</small></span></div><hr style="margin:8px 0; border-top: 1px solid rgba(128,128,128,0.2);">
                <div style="display:flex; justify-content:space-between; color:#16A34A; font-size:16px;"><b>🟢 支撐</b> <span><b>{nl:.2f}</b> <br><small style="float:right;">{calc_pct(nl, current_price)}</small></span></div><hr style="margin:8px 0; border-top: 1px solid rgba(128,128,128,0.2);">
                <div style="display:flex; justify-content:space-between; color:#2563EB; font-size:16px;"><b>🔵 強撐</b> <span><b>{al:.2f}</b> <br><small style="float:right;">{calc_pct(al, current_price)}</small></span></div>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px dashed rgba(128,128,128,0.3);">
                    <div style="font-size: 14px; opacity:0.7; margin-bottom: 5px;">今日高低 vs CDP</div>
                    <div style="font-size: 15px;">
                        <span style="color:{hi_color};">高 {current_high:.1f} ({hi_status})</span>
                        <span style="opacity:0.4; margin: 0 8px;">|</span>
                        <span style="color:{lo_color};">低 {current_low:.1f} ({lo_status})</span>
                    </div>
                </div>
            </div>
            """)
            st.markdown(cdp_html, unsafe_allow_html=True)

        with col_strategy:
            st.markdown("#### 💡 操作建議")
            if current_price >= ah:
                zone_color, zone_title = "#E8385A", "S區：極強勢軋空"
                desc = "突破強壓，極強勢多頭格局。順勢操作，留意高檔爆量反轉。"
                up_hint, down_hint = f"上方無壓，沿均線續抱。", f"先看強壓 {ah:.1f} 能否轉為支撐。"
            elif current_price >= nh and current_price < ah:
                zone_color, zone_title = "#F5A623", "B區：壓力區間"
                desc = "位於壓力與強壓之間，多頭格局。適合小額試多，此區勝率較高。突破強壓可加碼。"
                up_hint, down_hint = f"先看強壓 {ah:.1f}，突破後看前高。", f"先看壓力 {nh:.1f} 能否守住。"
            elif current_price >= cdp and current_price < nh:
                zone_color, zone_title = "#F5A623", "偏多震盪區"
                desc = "位於中關與壓力之間。等待帶量突破壓力，可嘗試順勢偏多。"
                up_hint, down_hint = f"先看壓力 {nh:.1f}，站穩續攻。", f"先看中關 {cdp:.1f}，跌破轉弱。"
            elif current_price >= nl and current_price < cdp:
                zone_color, zone_title = "#16A34A", "C區：觀望區"
                desc = "低於中關價，空方略強。觀察是否守住支撐。不建議貿然進場，等待方向確認。"
                up_hint, down_hint = f"先看中關 {cdp:.1f}，站穩才有轉強機會。", f"先看支撐 {nl:.1f}，跌破下看強撐。"
            else:
                zone_color, zone_title = "#2563EB", "D區：弱勢探底區"
                desc = "跌破支撐，空方強勢控盤。切勿隨意摸底，做多者請嚴格停損。"
                up_hint, down_hint = f"反彈先看支撐 {nl:.1f} 能否站回。", f"下測強撐 {al:.1f}，跌破須嚴格停損出場。"
            
            strategy_html = textwrap.dedent(f"""
            <div style="background: rgba(128,128,128,0.05); padding:20px; border-radius:5px; border-left: 6px solid {zone_color}; border-right: 1px solid rgba(128,128,128,0.2); border-top: 1px solid rgba(128,128,128,0.2); border-bottom: 1px solid rgba(128,128,128,0.2); height: 100%;">
                <h3 style="margin-top:0; color:{zone_color};">{zone_title}</h3>
                <p style="font-size: 16px; opacity:0.9; line-height: 1.6;">{desc}</p>
                <div style="margin-top: 15px; font-size: 15px; line-height: 1.8;">
                    <span style="color:#E8385A;"><b>↑ 若上漲：</b></span> <span style="opacity:0.9;">{up_hint}</span><br>
                    <span style="color:#16A34A;"><b>↓ 若下跌：</b></span> <span style="opacity:0.9;">{down_hint}</span>
                </div>
            </div>
            """)
            st.markdown(strategy_html, unsafe_allow_html=True)

        st.divider()

        # ==========================================
        # 🔵 版面區塊 3: 底部 K 線圖
        # ==========================================
        st.markdown("#### 📈 技術線圖 (日K)")
        
        visible_df = df[-60:]
        date_labels = visible_df.index.strftime('%m/%d')
        
        buy_signals = visible_df[visible_df['Signal'] == 1]
        sell_signals = visible_df[visible_df['Signal'] == -1]
        buy_count, sell_count = len(buy_signals), len(sell_signals)
        total_signals = buy_count + sell_count
        
        td_val = today_data['TD_Setup']
        td_status = f"{int(td_val)}/9 多頭" if td_val > 0 else f"{abs(int(td_val))}/9 空頭" if td_val < 0 else "無"
        
        legend_html = textwrap.dedent(f"""
        <div style="background: rgba(128,128,128,0.05); padding: 12px 20px; border-radius: 8px; margin-bottom: -15px; font-size: 14px; border: 1px solid rgba(128,128,128,0.3);">
            <div style="margin-bottom: 8px;">
                <b style="font-size:16px;">{datetime.today().strftime('%m-%d')}</b> &nbsp; 
                <span style="color:#16A34A;">開 {current_open:.1f}</span> &nbsp; 
                <span style="color:#E8385A;">高 {current_high:.1f}</span> &nbsp; 
                <span style="color:#16A34A;">低 {current_low:.1f}</span> &nbsp; 
                <span>收 {current_price:.1f}</span> &nbsp; 
                <span style="opacity:0.7;">量 {volume_in_lots:,}</span>
            </div>
            <div style="display:flex; gap: 20px; align-items: center; margin-bottom: 8px;">
                <span style="color:#F5A623; font-weight:bold;">— MA5</span> <span>{ma5_val:.1f}</span> <span style="color:{'#E8385A' if ma5_trend=='▲' else '#16A34A'};">{ma5_trend}</span>
                <span style="color:#9B51E0; font-weight:bold;">— MA13</span> <span>{ma13_val:.1f}</span> <span style="color:{'#E8385A' if ma13_trend=='▲' else '#16A34A'};">{ma13_trend}</span>
            </div>
            <div style="display:flex; align-items: center; gap: 15px; flex-wrap: wrap;">
                <div><span style="color:#E8385A; font-size: 18px;">●</span> 轉多買進</div>
                <div><span style="color:#16A34A; font-size: 18px;">●</span> 轉空賣出</div>
                <div><span style="color:#E0B0FF; font-weight:bold;">—</span> BB</div>
                <div><span style="color:#48CFAF; font-size: 18px;">●</span> {td_status}</div>
                <div style="margin-left:auto; background: rgba(128,128,128,0.1); padding:4px 12px; border-radius:6px; font-size: 13px;">
                    日 K 訊號: <b>{total_signals}</b> &nbsp;|&nbsp; 多 <b style="color:#E8385A;">{buy_count}</b> &nbsp; 空 <b style="color:#16A34A;">{sell_count}</b>
                </div>
            </div>
        </div>
        """)
        st.markdown(legend_html, unsafe_allow_html=True)
        
        fig = go.Figure()
        
        fig.add_trace(go.Candlestick(x=date_labels, open=visible_df['Open'], high=visible_df['High'],
                                     low=visible_df['Low'], close=visible_df['Close'], name="K線",
                                     increasing_line_color='#E8385A', decreasing_line_color='#16A34A'))
        
        fig.add_trace(go.Scatter(x=date_labels, y=visible_df['MA5'], line=dict(color='#F5A623', width=1.5), name='MA5'))
        fig.add_trace(go.Scatter(x=date_labels, y=visible_df['MA13'], line=dict(color='#9B51E0', width=1.5), name='MA13'))
        fig.add_trace(go.Scatter(x=date_labels, y=visible_df['BB_Upper'], line=dict(color='rgba(155, 81, 224, 0.3)', dash='dot'), name='BB 上軌'))
        fig.add_trace(go.Scatter(x=date_labels, y=visible_df['BB_Lower'], line=dict(color='rgba(155, 81, 224, 0.3)', dash='dot'), name='BB 下軌'))
        
        levels = [(ah, "強壓", "#E8385A"), (nh, "壓力", "#F5A623"), 
                  (cdp, "中關", "#7B7B7B"), (nl, "支撐", "#16A34A"), (al, "強撐", "#2563EB")]
        for val, name, color in levels:
            fig.add_hline(y=val, line_dash="dot", line_color=color, annotation_text=f"{name} {val:.1f}", annotation_position="right")

        buy_x = buy_signals.index.strftime('%m/%d')
        sell_x = sell_signals.index.strftime('%m/%d')

        fig.add_trace(go.Scatter(
            x=buy_x, y=buy_signals['Low'] * 0.95, 
            mode='text', 
            text=['▲<br>多'] * len(buy_signals), 
            textposition='bottom center', 
            textfont=dict(color='#E8385A', size=13, weight='bold'), 
            name='買進'
        ))
        
        fig.add_trace(go.Scatter(
            x=sell_x, y=sell_signals['High'] * 1.05, 
            mode='text', 
            text=['空<br>▼'] * len(sell_signals), 
            textposition='top center', 
            textfont=dict(color='#16A34A', size=13, weight='bold'), 
            name='賣出'
        ))

        fig.update_layout(
            height=650, 
            margin=dict(l=0, r=120, t=30, b=10), 
            xaxis_rangeslider_visible=False, 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='gray'),
            showlegend=False,
            xaxis=dict(type='category', nticks=10, gridcolor='rgba(128,128,128,0.15)'),
            yaxis=dict(gridcolor='rgba(128,128,128,0.15)')
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("資料不足，無法計算當沖點位。")

except Exception as e:
    st.error(f"發生錯誤: {e}")