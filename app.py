import os
import yfinance as yf
import pandas as pd
import talib
import matplotlib.pyplot as plt
import streamlit as st
from datetime import date


## Function to check if the provided username/email and password are valid
def is_valid_credentials(username_or_email, password):
    data = pd.read_excel("data.xlsx")
    user_match = data[(data["Username"] == username_or_email) | (data["Email"] == username_or_email)]
    if not user_match.empty:
        return password == user_match["Password"].iloc[0]
    return False

def backtest_trading_strategy(symbol, start_date, end_date, daily_timeframe, weekly_timeframe, initial_capital, rsi_value, sma_period):
    daily_data = yf.download(symbol, start=start_date, end=end_date, interval=daily_timeframe)
    weekly_data = yf.download(symbol, start=start_date, end=end_date, interval=weekly_timeframe)

    weekly_data["SMA"] = talib.SMA(weekly_data["Close"], timeperiod=sma_period)
    weekly_data["RSI"] = talib.RSI(weekly_data["Close"], timeperiod=14)

    data = pd.merge(daily_data[["Close"]], weekly_data[["SMA", "RSI"]], how="left", left_index=True, right_index=True)

    data["Buy"] = (data["Close"] > data["SMA"]) & (data["RSI"] > rsi_value)
    data["Sell"] = data["Close"] < data["SMA"]

    position = 0
    stop_loss = 0.02
    stop_loss_price = 0
    max_holding_period = pd.DateOffset(weeks=4)
    entries = []
    exits = []
    target_price = 0  # Initialize target_price

    returns = []  # List to store individual trade returns
    capital = [initial_capital]  # List to store capital after each trade
    trade_dates = []  # List to store trade dates
    quantities = []  # List to store quantities bought
    investments = []  # List to store total amount invested in each trade

    for i in range(len(data)):
        if data["Buy"][i] and position == 0:
            position = 1
            entry_price = data["Close"][i]
            stop_loss_price = entry_price * (1 - 0.02)
            target_price = entry_price * 1.05
            entries.append((daily_data.index[i], entry_price))
            quantity = capital[-1] // entry_price  # Calculate whole number quantity bought based on current capital
            quantities.append(quantity)
            investments.append(quantity * entry_price)  # Record total amount invested

        elif (data["Sell"][i] or data["Close"][i] <= stop_loss_price or data["Close"][i] >= target_price) and position == 1:
            position = 0
            exit_price = data["Close"][i]
            pnl = (exit_price - entry_price) / entry_price
            capital[-1] += capital[-1] * pnl  # Adjust capital based on trade return
            exits.append((daily_data.index[i], exit_price, pnl))
            returns.append(pnl)  # Add trade return to returns list
            capital.append(capital[-1])  # Append current capital to list
            trade_dates.append(daily_data.index[i].date())  # Add trade date to trade dates list

        if position == 1 and data["Close"][i] < stop_loss_price:
            stop_loss_price = data["Close"][i] * (1 - 0.02)

        if position == 1 and daily_data.index[i] >= entries[-1][0] + max_holding_period:
            position = 0
            exit_price = data["Close"][i]
            pnl = (exit_price - entry_price) / entry_price
            capital[-1] += capital[-1] * pnl  # Adjust capital based on trade return
            exits.append((daily_data.index[i], exit_price, pnl))
            returns.append(pnl)  # Add trade return to returns list
            capital.append(capital[-1])  # Append current capital to list
            trade_dates.append(daily_data.index[i].date())  # Add trade date to trade dates list


    # Check if the last trade is still open
    if position == 1:
        exit_price = data["Close"][-1]
        pnl = (exit_price - entry_price) / entry_price
        capital[-1] += capital[-1] * pnl  # Adjust capital based on trade return
        exits.append((date.today(), exit_price, pnl))
        returns.append(pnl)  # Add trade return to returns list
        trade_dates.append(date.today())  # Add today's date as trade date
        capital.append(capital[-1])  # Append current capital to list

    trade_data = pd.DataFrame(entries, columns=["Entry Date", "Entry Price"])
    trade_data["Exit Date"] = [x[0] for x in exits]
    trade_data["Exit Price"] = [x[1] for x in exits]
    trade_data["P&L"] = [x[2] for x in exits]

    # Calculate P&L in percentage and store it in the DataFrame
    for exit_info in exits:
        entry_date, entry_price = next((e for e in entries[::-1] if e[0] <= exit_info[0]), (None, None))
        if entry_date is not None and entry_price is not None:
            exit_date, exit_price, _ = exit_info
            pnl = (exit_price - entry_price) / entry_price
            trade_data.loc[trade_data["Exit Date"] == exit_date, "P&L"] = pnl

    trade_data["P&L in %"] = trade_data["P&L"] * 100

    trade_data["Entry Date"] = pd.to_datetime(trade_data["Entry Date"])
    trade_data["Exit Date"] = pd.to_datetime(trade_data["Exit Date"])
    trade_data["Holding Period"] = (trade_data["Exit Date"] - trade_data["Entry Date"]).dt.days
    trade_data["Capital Used"] = investments
    trade_data["No of Quantities"] = quantities
    trade_data["Profit/Loss Amount"] = trade_data["No of Quantities"] * (trade_data["Exit Price"] - trade_data["Entry Price"])
    trade_data["No of Quantities"] = trade_data["No of Quantities"].astype(int)

    total_trades = len(trade_data)
    success_trades = len(trade_data[trade_data["P&L"] > 0])
    success_ratio = success_trades / total_trades if total_trades > 0 else 0
    percentage_return = ((capital[-1] - initial_capital) / initial_capital) * 100

    strategy_profit = (capital[-1] - initial_capital) / initial_capital * 100
    annualized_return = ((1 + percentage_return / 100) ** (365 / len(data))) - 1
    total_signals = total_trades
    profit_factor = trade_data[trade_data["P&L"] > 0]["P&L"].sum() / abs(trade_data[trade_data["P&L"] < 0]["P&L"].sum())

    return (total_trades, success_ratio, capital[-1], strategy_profit, annualized_return, total_signals, profit_factor, trade_data, capital)

def main():
    # Check if the user is logged in
    if "username" not in st.session_state:
        st.title("Login")
        username_or_email_input = st.text_input("Username or Email:")
        password_input = st.text_input("Password:", type="password")

        if st.button("Login"):
            if is_valid_credentials(username_or_email_input, password_input):
                st.session_state.username = username_or_email_input
                data = pd.read_excel("data.xlsx")
                user_name = data[(data["Username"] == username_or_email_input) | (data["Email"] == username_or_email_input)]["Name"].iloc[0]
            else:
                st.error("Invalid username/email or password. Please try again.")
        return

    # Define the position variable to keep track of the current open position
    position = 0

    # Get the directory path of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Join the script directory with the file name to get the full file path
    file_path = os.path.join(script_dir, "nse.xlsx")

    # Read the nse.xlsx file (change to .csv if it's actually in CSV format)
    nse_data = pd.read_excel(file_path)
    ticker_list = nse_data["Ticker"].tolist()
    company_list = nse_data["Company Name"].tolist()

    # Sidebar content
    st.sidebar.title("Parameters")
    selected_company = st.sidebar.selectbox("Select the company:", company_list)

    # Find the corresponding ticker for the selected company
    selected_ticker = nse_data[nse_data["Company Name"] == selected_company]["Ticker"].values[0]

    # Date input
    start_date = st.sidebar.date_input("Start Date", date(2021, 1, 1))
    end_date = st.sidebar.date_input("End Date", date.today())

    rsi_value = st.sidebar.slider("Weekly RSI crossed up", min_value=0, max_value=100, value=60)
    sma_period = st.sidebar.slider("Weekly SMA Period", min_value=1, max_value=200, value=21)

    # Main content
    st.title("Momentum Trading Strategy Backtest")

    daily_timeframe = "1d"
    weekly_timeframe = "1wk"
    initial_capital = 100000  # Initial investment amount (1 lakh)

    total_trades, success_ratio, final_capital, strategy_profit, annualized_return, total_signals, profit_factor, trade_data, capital = backtest_trading_strategy(
        selected_ticker, start_date, end_date, daily_timeframe, weekly_timeframe, initial_capital, rsi_value, sma_period
    )

    # Box containers for key performance metrics
    st.subheader("Key Performance Metrics")

    # Define custom CSS styling for the boxes
    box_style = """
        background-color: #2f4f4f;
        color: white;
        text-align: center;
        font-size: 18px;
        padding: 20px;
        margin: 10px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
    """

    # Use HTML to apply the custom styling to the boxes
    st.write(
        '<div style="display: flex; flex-wrap: wrap;">'
        f'<div style="{box_style}; flex: 33.33%;">Total Number of Signals:<br><b>{total_signals}</b></div>'
        f'<div style="{box_style}; flex: 33.33%;">Success/Failure Trades Ratio:<br><b>{success_ratio:.2f}</b></div>'
        f'<div style="{box_style}; flex: 33.33%;">Strategy Profit:<br><b>{strategy_profit:.2f}%</b></div>'
        f'<div style="{box_style}; flex: 33.33%;">Final Capital:<br><b>{final_capital:.2f}</b></div>'
        f'<div style="{box_style}; flex: 33.33%;">Annualized Return:<br><b>{annualized_return:.2f}%</b></div>'
        f'<div style="{box_style}; flex: 33.33%;">Profit Factor:<br><b>{profit_factor:.2f}</b></div>'        
        '</div>',
        unsafe_allow_html=True
    )

    
    # Modify DataFrame to remove time from "Entry Date" and "Exit Date" columns
    trade_data["Entry Date"] = trade_data["Entry Date"].dt.date
    trade_data["Exit Date"] = trade_data["Exit Date"].dt.date

    # Remove the "P&L" column after "Exit Price" column
    trade_data = trade_data[["Entry Date", "Entry Price", "Exit Date", "Exit Price", "P&L in %", "Holding Period", "Capital Used", "No of Quantities", "Profit/Loss Amount"]]

    # Display trade details with an expander
    with st.expander("Trade Details"):
        st.dataframe(trade_data)

    # Plot cumulative capital curve
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(trade_data["Entry Date"], capital[:-1], color='yellow', label="Cumulative Capital", linewidth=2)
    ax.scatter(trade_data["Entry Date"], capital[:-1], color='red', label="Data Points", zorder=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Capital (%)")
    ax.set_title("Cumulative Capital Curve")
    ax.legend()
    ax.grid(True, linestyle='dotted', alpha=0.5)
    ax.margins(0.02)

    st.pyplot(fig)

if __name__ == "__main__":
    main()
