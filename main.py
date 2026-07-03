import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
from groq import Groq

# 1. Настройка БД
def init_db():
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio 
                 (ticker TEXT PRIMARY KEY, quantity REAL, buy_price REAL)''')
    conn.commit()
    conn.close()

init_db()

# 2. Инициализация API
import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

def get_ai_response(prompt):
    try:
        clean_text = prompt.encode("ascii", "ignore").decode("ascii")
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": clean_text}],
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

# 3. Интерфейс
st.set_page_config(page_title="Smart Investor Pro", layout="wide")
st.title("📈 Smart Investor Terminal")

tab1, tab2 = st.tabs(["📊 Terminal", "💼 My Portfolio"])

# --- Вкладка 1: Терминал ---
with tab1:
    st.sidebar.header("Navigation")
    market_indexes = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC"}
    top_10 = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AMD", "BRK.B"]
    
    mode = st.sidebar.radio("Select mode:", ["Custom Ticker", "Market Indexes", "Top 10 Stocks"])
    if mode == "Custom Ticker":
        ticker = st.sidebar.text_input("Enter Ticker:", value="AAPL").upper()
    elif mode == "Market Indexes":
        ticker = st.sidebar.selectbox("Select Index:", list(market_indexes.values()), format_func=lambda x: [k for k, v in market_indexes.items() if v == x][0])
    else:
        ticker = st.sidebar.selectbox("Select Top 10:", top_10)

    chart_type = st.sidebar.radio("Chart Type:", ["Line", "Candlestick", "Bar"])

    tick_obj = yf.Ticker(ticker)
    df = tick_obj.history(period="6mo")

    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"Charts for {ticker}")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_width=[0.2, 0.7])
            
            if chart_type == "Line":
                fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Price", line=dict(width=2)), row=1, col=1)
            elif chart_type == "Candlestick":
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
            else:
                fig.add_trace(go.Ohlc(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", mode='lines', line=dict(color='#FF5733', width=2.5)), row=2, col=1)
            fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📊 Key Metrics")
            st.metric("Price", f"{df['Close'].iloc[-1]:.2f}")
            info = tick_obj.info
            st.metric("P/E Ratio", f"{info.get('trailingPE', 0):.2f}")
            if st.button("🚀 AI Analysis"):
                st.info(get_ai_response(f"Analyze {ticker}. Price: {df['Close'].iloc[-1]:.2f}. Buy/Sell/Hold?"))

# --- Вкладка 2: Портфель (Исправленный блок) ---
with tab2:
    st.title("💼 Portfolio Performance")
    with st.expander("➕ Add/Update Asset"):
        with st.form("add_form"):
            new_t = st.text_input("Ticker").upper()
            qty = st.number_input("Quantity", min_value=0.0)
            prc = st.number_input("Buy Price (Avg)", min_value=0.0)
            if st.form_submit_button("Save"):
                if new_t:
                    conn = sqlite3.connect('portfolio.db')
                    c = conn.cursor()
                    c.execute('INSERT OR REPLACE INTO portfolio VALUES (?, ?, ?)', (new_t, qty, prc))
                    conn.commit()
                    conn.close()
                    st.rerun()

    conn = sqlite3.connect('portfolio.db')
    df_port = pd.read_sql_query("SELECT * FROM portfolio", conn)
    conn.close()

    if not df_port.empty:
        data = []
        for _, row in df_port.iterrows():
            ticker_name = str(row['ticker']).strip()
            if not ticker_name: continue
            
            try:
                hist = yf.Ticker(ticker_name).history(period="1d")
                if hist.empty: continue
                
                curr = hist['Close'].iloc[-1]
                val = curr * row['quantity']
                profit = val - (row['buy_price'] * row['quantity'])
                data.append({'Ticker': ticker_name, 'Value': val, 'Profit': profit})
            except Exception:
                continue
        
        # Теперь отрисовка ТОЛЬКО если есть данные после фильтрации
        if data:
            df_res = pd.DataFrame(data)
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.plotly_chart(go.Figure(data=[go.Pie(labels=df_res['Ticker'], values=df_res['Value'])]), use_container_width=True)
            with col_p2:
                st.metric("Total Profit", f"{df_res['Profit'].sum():.2f} USD")
                st.table(df_res)
        else:
            st.write("No valid stock data found in portfolio.")
    else:
        st.write("Portfolio is empty.")
