import os
import time
import pyarrow
import warnings
import operator
import socket
from datetime import datetime, timedelta
import pandas as pd
import pandas_ta as ta
import optuna
from moexalgo import Ticker
from datetime import datetime
from functools import reduce
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings('ignore')

# --- 1. СИСТЕМНЫЕ ФУНКЦИИ ---
def get_cache_path(ticker, start, end):
    cache_dir = os.path.join(os.getcwd(), 'cache')
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    # Приводим к формату ГГГГ-ММ-ДД для имени файла
    s = datetime.strptime(start, '%d.%m.%Y').strftime('%Y-%m-%d')
    e = datetime.strptime(end, '%d.%m.%Y').strftime('%Y-%m-%d')
    return os.path.join(cache_dir, f"{ticker}_{s}_{e}.parquet")

def get_moex_data(ticker_symbol, start_date, end_date):
    final_path = get_cache_path(ticker_symbol, start_date, end_date)
    temp_path = final_path.replace(".parquet", "_TEMP.parquet")
    
    if os.path.exists(final_path):
        return pd.read_parquet(final_path)

    s_dt = datetime.strptime(start_date, '%d.%m.%Y')
    e_dt = datetime.strptime(end_date, '%d.%m.%Y')
    
    # ПРЕДОХРАНИТЕЛЬ 1: Только дата (гггг-мм-дд) без времени для API
    iso_end = e_dt.strftime('%Y-%m-%d')
    
    all_dfs = []
    current_dt = s_dt

    if os.path.exists(temp_path):
        try:
            temp_df = pd.read_parquet(temp_path)
            if not temp_df.empty:
                last_ts = temp_df.index.max()
                if last_ts >= e_dt:
                    temp_df.to_parquet(final_path)
                    os.remove(temp_path)
                    return temp_df
                current_dt = last_ts + timedelta(minutes=1)
                all_dfs.append(temp_df)
        except: pass

    try:
        t = Ticker(ticker_symbol)
        with tqdm(total=(e_dt-s_dt).days, desc=f" Загрузка {ticker_symbol}", unit="дн", 
                  initial=(current_dt-s_dt).days) as pbar:
            
            while current_dt.date() < e_dt.date():
                # ПРЕДОХРАНИТЕЛЬ 2: Только дата для старта
                curr_iso_start = current_dt.strftime('%Y-%m-%d')
                
                df_chunk = pd.DataFrame()
                try:
                    # Запрос только по датам YYYY-MM-DD
                    raw_data = t.candles(start=curr_iso_start, end=iso_end, period=1)
                    if raw_data is not None:
                        df_chunk = pd.DataFrame(raw_data)
                except Exception as e:
                    # Если API ругается на формат, выводим что именно ему не нравится
                    tqdm.write(f" [!] Ошибка API на {curr_iso_start}: {e}")
                    time.sleep(5)
                    # Если это 1 января и API падает, пробуем просто перешагнуть день
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=0, minute=0)
                    continue

                if df_chunk.empty:
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=0, minute=0)
                    pbar.update(1)
                    continue

                # Обработка
                df_chunk = df_chunk.rename(columns={'begin': 'ts', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                df_chunk['ts'] = pd.to_datetime(df_chunk['ts'])
                df_chunk.set_index('ts', inplace=True)
                
                # ПРЕДОХРАНИТЕЛЬ 3: Фильтруем то, что уже скачали ранее (внутри того же дня)
                df_chunk = df_chunk.loc[df_chunk.index >= current_dt]
                
                if df_chunk.empty:
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=0, minute=0)
                    pbar.update(1)
                    continue

                all_dfs.append(df_chunk)
                last_ts = df_chunk.index.max()
                
                pbar.update(max(0, (last_ts.date() - current_dt.date()).days))
                current_dt = last_ts + timedelta(minutes=1)
                
                pd.concat(all_dfs).to_parquet(temp_path)
                time.sleep(0.2)

    except Exception as e:
        tqdm.write(f" [!] Ошибка: {e}")

    # 3. Финализация
    if all_dfs:
        final_df = pd.concat(all_dfs).sort_index()
        # Убираем возможные дубликаты на стыках чанков
        final_df = final_df[~final_df.index.duplicated(keep='last')]
        final_df.to_parquet(final_path)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return final_df
    
    return pd.DataFrame()

# --- 2. ЯДРО БЭКТЕСТА ---
def run_full_backtest(df_raw, params, commission=0.00035):
    # Запас баров для индикаторов (EMA 200 требует истории)
    if df_raw is None or len(df_raw) < 250: 
        return None
        
    df = df_raw.copy()
    buy_conds = []
    sell_conds = []
    readable_parts = []

    # --- 1. РАСЧЕТ ИНДИКАТОРОВ И СБОР УСЛОВИЙ ---

    # ADX (Фильтр силы тренда)
    adx_filter = pd.Series(True, index=df.index)
    if params.get('use_adx'):
        adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=params.get('adx_len', 14))
        if adx_df is not None and not adx_df.empty:
            df['adx'] = adx_df.iloc[:, 0]
            adx_filter = (df['adx'].notnull()) & (df['adx'] > params.get('adx_min', 25))
            readable_parts.append(f"ADX({params['adx_len']},>{params['adx_min']})")

    # RSI (Осциллятор перепроданности)
    if params.get('use_rsi'):
        rsi_s = ta.rsi(df['Close'], length=params.get('rsi_len', 14))
        if rsi_s is not None:
            df['rsi'] = rsi_s
            buy_conds.append(df['rsi'] < params['rsi_buy_lvl'])
            sell_conds.append(df['rsi'] > 70)
            readable_parts.append(f"RSI({params['rsi_len']},<{params['rsi_buy_lvl']})")

    # Bollinger Bands (Волатильность)
    if params.get('use_bb'):
        bb = ta.bbands(df['Close'], length=params['bb_len'], std=params['bb_std'])
        if bb is not None and not bb.empty:
            df['bbl'], df['bbu'] = bb.iloc[:, 0], bb.iloc[:, 2]
            buy_conds.append(df['Close'] < df['bbl'])
            sell_conds.append(df['Close'] > df['bbu'])
            readable_parts.append(f"BB({params['bb_len']},{round(params['bb_std'],1)})")

    # MACD (Импульс)
    if params.get('use_macd'):
        macd = ta.macd(df['Close'], fast=12, slow=26)
        if macd is not None and not macd.empty:
            df['macd_h'] = macd.iloc[:, 1]
            buy_conds.append(df['macd_h'] > 0)
            sell_conds.append(df['macd_h'] < 0)
            readable_parts.append("MACD(12,26)")

    # Stochastic (Быстрый осциллятор)
    if params.get('use_stoch'):
        stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3)
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch.iloc[:, 0]
            buy_conds.append(df['stoch_k'] < 20)
            sell_conds.append(df['stoch_k'] > 80)
            readable_parts.append("STOCH(14,3)")

    # EMA (Фильтр долгосрочного тренда)
    if params.get('use_ema'):
        ema_s = ta.ema(df['Close'], length=params['ema_len'])
        if ema_s is not None:
            df['ema'] = ema_s
            buy_conds.append((df['ema'].notnull()) & (df['Close'] > df['ema']))
            sell_conds.append((df['ema'].notnull()) & (df['Close'] < df['ema']))
            readable_parts.append(f"EMA({params['ema_len']})")

    # Если Optuna выключила все индикаторы - выходим
    if not buy_conds: 
        return None
    
    df.dropna(inplace=True)
    if df.empty: 
        return None

    # --- 2. ГЕНЕРАЦИЯ СИГНАЛОВ ---
    df['signal'] = 0
    # Вход: (Любой из индикаторов ИЛИ) ПРИ УСЛОВИИ (Фильтра ADX)
    df.loc[reduce(operator.or_, buy_conds) & adx_filter, 'signal'] = 1
    # Выход: Любой из индикаторов на выход
    df.loc[reduce(operator.or_, sell_conds), 'signal'] = 0
    
    df['pos'] = df['signal'].shift(1).fillna(0)
    
    # --- 3. СИМУЛЯЦИЯ СДЕЛКОК ---
    trades, in_pos, entry_p = [], False, 0
    close_vals, pos_vals = df['Close'].values, df['pos'].values

    for i in range(len(df)):
        if pos_vals[i] == 1 and not in_pos:
            entry_p, in_pos = close_vals[i], True
        elif pos_vals[i] == 0 and in_pos:
            trades.append((close_vals[i] / entry_p) - 1 - (2 * commission))
            in_pos = False

    if not trades: return None

    # --- 4. РАСЧЕТ ИТОГОВ ---
    sum_profit = sum(trades)
    plus_trades = [t for t in trades if t > 0]
    equity = pd.Series(trades).add(1).cumprod()
    max_dd = (equity.cummax() - equity).max() if not equity.empty else 0

    return {
        "Параметры": " + ".join(readable_parts),
        "Сделок": len(trades),
        "Плюсовых": len(plus_trades),
        "Эффективность (%)": round((len(plus_trades)/len(trades))*100, 2),
        "Ср.прибыль (%)": round((sum_profit/len(trades))*100, 3),
        "Просадка (%)": round(max_dd * 100, 2),
        "Прибыльность (%)": round(sum_profit * 100, 2)
    }

# --- 3. OPTUNA & WORKER ---
def objective(trial, df):
    params = {
        'use_rsi': trial.suggest_categorical('use_rsi', [True, False]),
        'use_bb': trial.suggest_categorical('use_bb', [True, False]),
        'use_macd': trial.suggest_categorical('use_macd', [True, False]),
        'use_stoch': trial.suggest_categorical('use_stoch', [True, False]),
        'use_ema': trial.suggest_categorical('use_ema', [True, False]),
        'use_adx': trial.suggest_categorical('use_adx', [True, False]),
        
        'rsi_len': trial.suggest_int('rsi_len', 7, 21),
        'rsi_buy_lvl': trial.suggest_int('rsi_buy_lvl', 30, 55),
        'bb_len': trial.suggest_int('bb_len', 10, 60),
        'bb_std': trial.suggest_float('bb_std', 1.0, 2.5, step=0.1),
        'ema_len': trial.suggest_int('ema_len', 50, 200),
        'adx_len': trial.suggest_int('adx_len', 10, 25),
        'adx_min': trial.suggest_int('adx_min', 15, 35)
    }
    res = run_full_backtest(df, params)
    return res['Прибыльность (%)'] if res else -1000

def worker_optuna(ticker, tf, raw_data):
    try:
        clean_tf = str(tf).lower().replace('m', 'min')
        data = raw_data.resample(clean_tf).agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        study = optuna.create_study(direction='maximize')
        study.optimize(lambda trial: objective(trial, data), n_trials=50)
        if study.best_value > -1000:
            res = run_full_backtest(data, study.best_params)
            if res: res.update({'Ticker': ticker, 'TF': tf}); return [res]
    except: pass
    return []

# --- 4. MAIN ---
if __name__ == '__main__':
    tickers = ['SBER', 'GAZP', 'LKOH', 'ROSN']
    tfs = ['15min', '30min', '1h', '4h', '1d']
    start_d, end_d = "01.01.2024", "01.01.2025"
    storage = {}
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    
    print("--- ЭТАП 1: ПОДГОТОВКА ДАННЫХ ---")
    for t in tickers:
        data = get_moex_data(t, start_d, end_d)
        if data is not None:
            storage[t] = data
            print(f"  [OK] {t} готов.")

    if storage:
        print("\n--- ЭТАП 2: ОПТИМИЗАЦИЯ ---")
        tasks = [(t, tf, storage[t]) for t in storage for tf in tfs]
        all_results = []
        with ProcessPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(worker_optuna, t, tf, data): (t, tf) for t, tf, data in tasks}
            for f in tqdm(as_completed(futures), total=len(tasks), desc="Анализ"):
                all_results.extend(f.result())

        if all_results:
            final_df = pd.DataFrame(all_results).sort_values("Прибыльность (%)", ascending=False)
            print("\n", final_df.to_string(index=False))
            final_df.to_excel("param_test_optuna.xlsx")