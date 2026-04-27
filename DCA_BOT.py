"""
╔═══════════════════════════════════════════════════════════════════╗
║                       DCA_BOT v2.0                                ║
║       Smart Multi-Exchange Portfolio Manager                     ║
║       Phases 3.1 + 3.2 + 3.3 + 3.4 (MVP Bundle)                  ║
║                                                                   ║
║  Features:                                                        ║
║    💼 Unified portfolio (Binance + OKX)                           ║
║    📊 Trade history sync + Auto avg buy price (WAP)              ║
║    💰 P&L per coin (realized + unrealized)                        ║
║    📈 Technical analysis (RSI, EMA, ATR, Trend)                   ║
║    🎯 Recommendations Engine (Hold/Sell/Buy/Replace/TakeProfit)   ║
║    🔄 Sector classification + Risk analysis                       ║
║                                                                   ║
║  للأغراض التعليمية فقط — ليس نصيحة مالية                          ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import hmac
import hashlib
import base64
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlencode

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)


# ══════════════════════════════════════════════════════════════════
# 1. CONFIG
# ══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("DCA_BOT")

BOT_TOKEN          = os.environ.get("BOT_TOKEN", "").strip()
BINANCE_API_KEY    = os.environ.get("BINANCE_API_KEY", "").strip()
BINANCE_SECRET     = os.environ.get("BINANCE_SECRET", "").strip()
OKX_API_KEY        = os.environ.get("OKX_API_KEY", "").strip()
OKX_SECRET         = os.environ.get("OKX_SECRET", "").strip()
OKX_PASSPHRASE     = os.environ.get("OKX_PASSPHRASE", "").strip()

DATA_DIR = os.environ.get("DATA_DIR", "/data").rstrip("/")
if not os.path.exists(DATA_DIR) and not os.access("/", os.W_OK):
    DATA_DIR = "./data"

BINANCE_BASE = "https://api.binance.com"
OKX_BASE     = "https://www.okx.com"
CP_BASE      = "https://api.coinpaprika.com/v1"

MIN_USD_VALUE = 1.0
TZ_RIYADH     = timezone(timedelta(hours=3))

STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDD",
    "USDP", "GUSD", "PYUSD", "USDE",
}

SECTOR_MAP = {
    "BTC": "L1", "ETH": "L1", "SOL": "L1", "BNB": "L1", "XRP": "L1",
    "ADA": "L1", "AVAX": "L1", "TRX": "L1", "DOT": "L1", "ATOM": "L1",
    "NEAR": "L1", "HBAR": "L1", "ALGO": "L1", "ETC": "L1", "TON": "L1",
    "APT": "L1", "SUI": "L1", "ICP": "L1", "FTM": "L1",
    "ARB": "L2", "OP": "L2", "MATIC": "L2", "POL": "L2", "MNT": "L2",
    "STRK": "L2", "BLAST": "L2", "ZRO": "L2",
    "UNI": "DeFi", "AAVE": "DeFi", "MKR": "DeFi", "SNX": "DeFi",
    "CRV": "DeFi", "COMP": "DeFi", "LDO": "DeFi", "RUNE": "DeFi",
    "GMX": "DeFi", "DYDX": "DeFi", "HYPE": "DeFi", "JUP": "DeFi",
    "PENDLE": "DeFi", "RAY": "DeFi",
    "RENDER": "AI", "RNDR": "AI", "TAO": "AI", "FET": "AI",
    "AGIX": "AI", "OCEAN": "AI", "WLD": "AI", "AKT": "AI", "GRT": "AI",
    "ONDO": "RWA", "POLYX": "RWA", "RIO": "RWA",
    "LINK": "Oracle", "PYTH": "Oracle", "BAND": "Oracle",
    "DOGE": "Meme", "SHIB": "Meme", "PEPE": "Meme", "WIF": "Meme",
    "BONK": "Meme", "FLOKI": "Meme", "MEME": "Meme", "POPCAT": "Meme",
    "MEW": "Meme", "BRETT": "Meme", "TURBO": "Meme", "SLERF": "Meme",
    "AXS": "Gaming", "SAND": "Gaming", "MANA": "Gaming",
    "GALA": "Gaming", "IMX": "Gaming", "APE": "Gaming",
    "BEAM": "Gaming", "PIXEL": "Gaming", "RON": "Gaming",
}
SECTOR_MAP.update({s: "Stable" for s in STABLECOINS})


def classify_asset(symbol: str) -> str:
    return SECTOR_MAP.get((symbol or "").upper(), "Other")


# ══════════════════════════════════════════════════════════════════
# 2. STORAGE
# ══════════════════════════════════════════════════════════════════

def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        log.warning(f"[STORAGE] cannot create {DATA_DIR}: {e}")


def storage_load(filename: str, default: Any = None) -> Any:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"[STORAGE] failed load {filename}: {e}")
        return default if default is not None else {}


def storage_save(filename: str, data: Any) -> bool:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        log.warning(f"[STORAGE] failed save {filename}: {e}")
        return False


def now_iso() -> str:
    return datetime.now(TZ_RIYADH).isoformat()


def now_str() -> str:
    return datetime.now(TZ_RIYADH).strftime("%H:%M:%S")


# ══════════════════════════════════════════════════════════════════
# 3. HTTP HELPER
# ══════════════════════════════════════════════════════════════════

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DcaBot/2.0)",
    "Accept": "application/json",
})


def safe_request(method: str, url: str,
                 params: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 timeout: tuple = (5, 20),
                 retries: int = 2) -> Optional[Any]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            h = dict(_session.headers)
            if headers:
                h.update(headers)
            r = _session.request(method, url, params=params, headers=h,
                                 timeout=timeout)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return r.text
            elif r.status_code == 429:
                last_err = "429"
                time.sleep(2 ** attempt)
                continue
            elif r.status_code in (401, 403):
                return {"_auth_error": r.status_code,
                        "_text": (r.text or "")[:200]}
            else:
                last_err = f"HTTP {r.status_code}: {(r.text or '')[:120]}"
        except requests.exceptions.Timeout:
            last_err = "timeout"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:100]}"
        if attempt < retries:
            time.sleep(1)
    log.warning(f"[HTTP] {method} {url[:70]} → {last_err}")
    return None


# ══════════════════════════════════════════════════════════════════
# 4. BINANCE CLIENT
# ══════════════════════════════════════════════════════════════════

def binance_signed_request(endpoint: str, params: Optional[dict] = None) -> Optional[Any]:
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return None
    if params is None:
        params = {}
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 60000
    query_string = urlencode(params)
    signature = hmac.new(
        BINANCE_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    url = f"{BINANCE_BASE}{endpoint}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    return safe_request("GET", url, params=params, headers=headers)


def binance_get_account() -> Optional[Dict]:
    return binance_signed_request("/api/v3/account")


def binance_get_prices() -> Optional[Dict[str, float]]:
    data = safe_request("GET", f"{BINANCE_BASE}/api/v3/ticker/price")
    if not isinstance(data, list):
        return None
    return {item["symbol"]: float(item["price"]) for item in data}


def binance_get_my_trades(symbol: str, from_id: int = 0,
                          limit: int = 1000) -> Optional[List[Dict]]:
    params = {"symbol": symbol, "limit": limit}
    if from_id > 0:
        params["fromId"] = from_id
    result = binance_signed_request("/api/v3/myTrades", params=params)
    return result if isinstance(result, list) else None


def binance_get_klines(symbol: str, interval: str = "1h",
                       limit: int = 200) -> Optional[List[List]]:
    data = safe_request("GET", f"{BINANCE_BASE}/api/v3/klines",
                        params={"symbol": symbol, "interval": interval,
                                "limit": limit})
    return data if isinstance(data, list) else None


def fetch_binance_portfolio() -> Tuple[List[Dict], Optional[str]]:
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        return [], "missing credentials"
    account = binance_get_account()
    if not account:
        return [], "API request failed"
    if isinstance(account, dict) and "_auth_error" in account:
        return [], f"auth error {account['_auth_error']}"
    if not isinstance(account, dict) or "balances" not in account:
        return [], "unexpected response"
    prices = binance_get_prices()
    if not prices:
        return [], "could not fetch prices"
    positions = []
    for bal in account.get("balances", []):
        try:
            asset = bal.get("asset", "")
            free = float(bal.get("free", 0))
            locked = float(bal.get("locked", 0))
            total = free + locked
            if total <= 0 or not asset:
                continue
            if asset in STABLECOINS:
                price_usd = 1.0
            else:
                price_usd = 0
                for quote in ("USDT", "USDC", "BUSD"):
                    sym = f"{asset}{quote}"
                    if sym in prices:
                        price_usd = prices[sym]
                        break
                if price_usd == 0:
                    btc_sym = f"{asset}BTC"
                    btc_usdt = prices.get("BTCUSDT", 0)
                    if btc_sym in prices and btc_usdt > 0:
                        price_usd = prices[btc_sym] * btc_usdt
                if price_usd == 0:
                    continue
            usd_value = total * price_usd
            if usd_value < MIN_USD_VALUE:
                continue
            positions.append({
                "asset": asset, "amount": total, "free": free,
                "locked": locked, "price_usd": price_usd,
                "usd_value": usd_value, "source": "binance",
            })
        except (TypeError, ValueError):
            continue
    return positions, None


# ══════════════════════════════════════════════════════════════════
# 5. OKX CLIENT
# ══════════════════════════════════════════════════════════════════

def _okx_timestamp() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _okx_sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    msg = f"{timestamp}{method}{path}{body}"
    sig = hmac.new(OKX_SECRET.encode("utf-8"), msg.encode("utf-8"),
                   hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")


def okx_signed_request(path: str, params: Optional[dict] = None) -> Optional[Any]:
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        return None
    full_path = path
    if params:
        full_path = f"{path}?{urlencode(params)}"
    timestamp = _okx_timestamp()
    sign = _okx_sign(timestamp, "GET", full_path, "")
    url = f"{OKX_BASE}{full_path}"
    headers = {
        "OK-ACCESS-KEY": OKX_API_KEY,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
    }
    return safe_request("GET", url, headers=headers)


def okx_get_balances() -> Optional[List[Dict]]:
    if not OKX_API_KEY:
        return None
    all_balances = []
    trading = okx_signed_request("/api/v5/account/balance")
    if trading and isinstance(trading, dict) and trading.get("code") == "0":
        for entry in trading.get("data", []):
            for det in entry.get("details", []):
                try:
                    ccy = det.get("ccy", "")
                    eq = float(det.get("eq", 0) or 0)
                    if ccy and eq > 0:
                        all_balances.append({"ccy": ccy, "amount": eq,
                                             "account": "trading"})
                except (TypeError, ValueError):
                    continue
    funding = okx_signed_request("/api/v5/asset/balances")
    if funding and isinstance(funding, dict) and funding.get("code") == "0":
        for det in funding.get("data", []):
            try:
                ccy = det.get("ccy", "")
                bal = float(det.get("bal", 0) or 0)
                if ccy and bal > 0:
                    all_balances.append({"ccy": ccy, "amount": bal,
                                         "account": "funding"})
            except (TypeError, ValueError):
                continue
    return all_balances if all_balances else None


def okx_get_prices() -> Optional[Dict[str, float]]:
    data = safe_request("GET", f"{OKX_BASE}/api/v5/market/tickers",
                        params={"instType": "SPOT"})
    if not isinstance(data, dict) or data.get("code") != "0":
        return None
    out = {}
    for t in data.get("data", []):
        try:
            inst = t.get("instId", "")
            last = float(t.get("last", 0) or 0)
            if inst and last > 0:
                out[inst] = last
        except (TypeError, ValueError):
            continue
    return out


def okx_get_fills_history(after: str = "", limit: int = 100) -> Optional[List[Dict]]:
    params = {"instType": "SPOT", "limit": str(limit)}
    if after:
        params["after"] = after
    result = okx_signed_request("/api/v5/trade/fills-history", params=params)
    if isinstance(result, dict) and result.get("code") == "0":
        return result.get("data", [])
    return None


def fetch_okx_portfolio() -> Tuple[List[Dict], Optional[str]]:
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        return [], "missing credentials"
    balances = okx_get_balances()
    if balances is None:
        test = okx_signed_request("/api/v5/account/balance")
        if isinstance(test, dict):
            if "_auth_error" in test:
                return [], f"auth error {test['_auth_error']}"
            if test.get("code") and test.get("code") != "0":
                return [], f"OKX: {test.get('msg', '?')}"
        return [], "API request failed"
    prices = okx_get_prices()
    if not prices:
        return [], "could not fetch prices"
    aggregated: Dict[str, Dict] = {}
    for b in balances:
        ccy = b["ccy"]
        if ccy not in aggregated:
            aggregated[ccy] = {"amount": 0.0, "accounts": []}
        aggregated[ccy]["amount"] += b["amount"]
        aggregated[ccy]["accounts"].append(b["account"])
    positions = []
    for ccy, info in aggregated.items():
        total = info["amount"]
        if total <= 0:
            continue
        if ccy in STABLECOINS:
            price_usd = 1.0
        else:
            price_usd = 0
            for quote in ("USDT", "USDC", "USD"):
                sym = f"{ccy}-{quote}"
                if sym in prices:
                    price_usd = prices[sym]
                    break
            if price_usd == 0:
                btc_sym = f"{ccy}-BTC"
                btc_usdt = prices.get("BTC-USDT", 0)
                if btc_sym in prices and btc_usdt > 0:
                    price_usd = prices[btc_sym] * btc_usdt
            if price_usd == 0:
                continue
        usd_value = total * price_usd
        if usd_value < MIN_USD_VALUE:
            continue
        positions.append({
            "asset": ccy, "amount": total, "price_usd": price_usd,
            "usd_value": usd_value, "source": "okx",
            "accounts": info["accounts"],
        })
    return positions, None


# ══════════════════════════════════════════════════════════════════
# 6. TRADE HISTORY SYNC + WAP (Phase 3.2)
# ══════════════════════════════════════════════════════════════════

def sync_binance_trades(assets: List[str]) -> Dict[str, List[Dict]]:
    state = storage_load("binance_trades_state.json", {})
    all_trades: Dict[str, List[Dict]] = state.get("trades", {})
    last_ids: Dict[str, int] = state.get("last_ids", {})
    quote_currencies = ["USDT", "USDC", "BUSD", "FDUSD", "BTC"]

    for asset in assets:
        if asset in STABLECOINS:
            continue
        new_trades_for_asset = []
        for quote in quote_currencies:
            symbol = f"{asset}{quote}"
            from_id = last_ids.get(symbol, 0)
            try:
                trades = binance_get_my_trades(symbol, from_id=from_id, limit=1000)
                if not trades or not isinstance(trades, list):
                    continue
                for tr in trades:
                    new_trades_for_asset.append({
                        "asset": asset, "symbol": symbol, "quote": quote,
                        "id": tr.get("id"), "time": int(tr.get("time", 0)),
                        "price": float(tr.get("price", 0)),
                        "qty": float(tr.get("qty", 0)),
                        "quote_qty": float(tr.get("quoteQty", 0)),
                        "is_buyer": tr.get("isBuyer", False),
                        "commission": float(tr.get("commission", 0)),
                        "commission_asset": tr.get("commissionAsset", ""),
                    })
                if trades:
                    max_id = max(int(t.get("id", 0)) for t in trades)
                    last_ids[symbol] = max_id
                time.sleep(0.1)
            except Exception as e:
                log.warning(f"[BIN_TRADES] {symbol}: {e}")
                continue

        if new_trades_for_asset:
            existing = all_trades.get(asset, [])
            existing_ids = {t.get("id") for t in existing}
            for t in new_trades_for_asset:
                if t["id"] not in existing_ids:
                    existing.append(t)
            existing.sort(key=lambda x: x.get("time", 0))
            all_trades[asset] = existing

    state = {"trades": all_trades, "last_ids": last_ids, "last_sync": now_iso()}
    storage_save("binance_trades_state.json", state)
    log.info(f"[BIN_TRADES] synced {len(all_trades)} assets")
    return all_trades


def sync_okx_trades() -> Dict[str, List[Dict]]:
    state = storage_load("okx_trades_state.json", {})
    all_trades: Dict[str, List[Dict]] = state.get("trades", {})
    seen_bill_ids = set(state.get("seen_bill_ids", []))

    after_id = ""
    page_count = 0
    max_pages = 10

    while page_count < max_pages:
        fills = okx_get_fills_history(after=after_id, limit=100)
        if not fills:
            break
        new_in_page = 0
        oldest_bill_id = None
        for f in fills:
            try:
                bill_id = f.get("billId", "")
                if not bill_id or bill_id in seen_bill_ids:
                    continue
                inst_id = f.get("instId", "")
                if "-" not in inst_id:
                    continue
                base, quote = inst_id.split("-", 1)
                side = f.get("side", "")
                px = float(f.get("fillPx", 0) or 0)
                sz = float(f.get("fillSz", 0) or 0)
                ts = int(f.get("ts", 0) or 0)
                if px <= 0 or sz <= 0:
                    continue
                trade = {
                    "asset": base, "symbol": inst_id, "quote": quote,
                    "id": bill_id, "time": ts, "price": px, "qty": sz,
                    "quote_qty": px * sz, "is_buyer": side == "buy",
                    "commission": float(f.get("fee", 0) or 0),
                    "commission_asset": f.get("feeCcy", ""),
                }
                all_trades.setdefault(base, []).append(trade)
                seen_bill_ids.add(bill_id)
                new_in_page += 1
                if not oldest_bill_id or bill_id < oldest_bill_id:
                    oldest_bill_id = bill_id
            except (TypeError, ValueError):
                continue
        if new_in_page == 0 or not oldest_bill_id:
            break
        after_id = oldest_bill_id
        page_count += 1
        time.sleep(0.5)

    for asset, trades in all_trades.items():
        trades.sort(key=lambda x: x.get("time", 0))

    state = {"trades": all_trades,
             "seen_bill_ids": list(seen_bill_ids),
             "last_sync": now_iso()}
    storage_save("okx_trades_state.json", state)
    log.info(f"[OKX_TRADES] synced {len(all_trades)} assets")
    return all_trades


def calculate_wap(trades: List[Dict]) -> Dict[str, Any]:
    """Weighted Average Purchase price across buys, with realized P&L on sells."""
    if not trades:
        return {
            "avg_buy_price": 0, "total_invested": 0, "total_realized": 0,
            "realized_pnl": 0, "first_buy_time": 0,
            "buy_count": 0, "sell_count": 0,
            "computed_remaining": 0,
        }

    sorted_trades = sorted(trades, key=lambda x: x.get("time", 0))

    avg_price = 0.0
    remaining_qty = 0.0
    total_invested = 0.0
    total_realized = 0.0
    realized_pnl = 0.0
    first_buy_time = 0
    buy_count = 0
    sell_count = 0

    for t in sorted_trades:
        price = float(t.get("price", 0))
        qty = float(t.get("qty", 0))
        is_buy = t.get("is_buyer", False)
        ts = int(t.get("time", 0))
        if price <= 0 or qty <= 0:
            continue
        if is_buy:
            new_total = avg_price * remaining_qty + price * qty
            new_qty = remaining_qty + qty
            avg_price = new_total / new_qty if new_qty > 0 else 0
            remaining_qty = new_qty
            total_invested += price * qty
            buy_count += 1
            if first_buy_time == 0:
                first_buy_time = ts
        else:
            sell_qty = min(qty, remaining_qty)
            cost_basis = avg_price * sell_qty
            proceeds = price * sell_qty
            realized_pnl += (proceeds - cost_basis)
            total_realized += proceeds
            remaining_qty -= sell_qty
            sell_count += 1
            if remaining_qty < 0.000001:
                remaining_qty = 0

    return {
        "avg_buy_price": round(avg_price, 8),
        "total_invested": round(total_invested, 2),
        "total_realized": round(total_realized, 2),
        "realized_pnl": round(realized_pnl, 2),
        "first_buy_time": first_buy_time,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "computed_remaining": round(remaining_qty, 8),
    }


# ══════════════════════════════════════════════════════════════════
# 7. TECHNICAL ANALYSIS (Phase 3.3)
# ══════════════════════════════════════════════════════════════════

def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_ema(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return round(ema, 8)


def calc_atr(highs: List[float], lows: List[float],
             closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return round(atr, 8)


def analyze_technical(symbol_full: str) -> Dict[str, Any]:
    out = {"rsi": None, "ema20": None, "ema50": None, "ema200": None,
           "atr": None, "trend": "Unknown", "last_price": None}
    klines = binance_get_klines(symbol_full, interval="1h", limit=250)
    if not klines or len(klines) < 50:
        return out
    closes = [float(k[4]) for k in klines]
    highs  = [float(k[2]) for k in klines]
    lows   = [float(k[3]) for k in klines]
    out["last_price"] = closes[-1]
    out["rsi"] = calc_rsi(closes, 14)
    out["ema20"] = calc_ema(closes, 20)
    out["ema50"] = calc_ema(closes, 50)
    out["ema200"] = calc_ema(closes, 200) if len(closes) >= 200 else None
    out["atr"] = calc_atr(highs, lows, closes, 14)
    e20, e50, e200 = out["ema20"], out["ema50"], out["ema200"]
    if e20 and e50:
        if e200:
            if e20 > e50 > e200:
                out["trend"] = "StrongUp"
            elif e20 < e50 < e200:
                out["trend"] = "StrongDown"
            elif e20 > e50:
                out["trend"] = "MildUp"
            elif e20 < e50:
                out["trend"] = "MildDown"
            else:
                out["trend"] = "Sideways"
        else:
            if e20 > e50:
                out["trend"] = "MildUp"
            elif e20 < e50:
                out["trend"] = "MildDown"
            else:
                out["trend"] = "Sideways"
    return out


# ══════════════════════════════════════════════════════════════════
# 8. RECOMMENDATIONS (Phase 3.4)
# ══════════════════════════════════════════════════════════════════

def make_recommendation(asset_data: Dict[str, Any]) -> Dict[str, Any]:
    pnl_pct = asset_data.get("unrealized_pct", 0)
    rsi = asset_data.get("rsi")
    trend = asset_data.get("trend", "Unknown")
    price = asset_data.get("price_usd", 0)
    avg_buy = asset_data.get("avg_buy_price", 0)
    atr = asset_data.get("atr", 0)
    sector = asset_data.get("sector", "Other")
    is_stable = asset_data.get("is_stable", False)

    rec = {
        "action": "HOLD", "icon": "💎", "confidence": "MEDIUM",
        "reasons": [], "hold_period": "غير محدد",
        "target_price": 0, "stop_loss": 0,
    }

    if is_stable:
        rec.update({
            "action": "HOLD", "icon": "💵", "confidence": "HIGH",
            "reasons": ["cash position — جاهز للـ DCA"],
            "hold_period": "DCA reserve",
        })
        return rec

    if avg_buy <= 0 or price <= 0:
        rec.update({
            "action": "HOLD", "icon": "❓", "confidence": "LOW",
            "reasons": ["لا يوجد trade history كافٍ"],
        })
        return rec

    # Decision tree
    if pnl_pct >= 30 and rsi is not None and rsi > 70:
        rec.update({
            "action": "TAKE_PROFIT_PARTIAL", "icon": "🟡",
            "confidence": "HIGH",
            "reasons": [
                f"P&L مرتفع جداً (+{pnl_pct:.1f}%)",
                f"RSI={rsi:.0f} (overbought)",
                "خذ ربح 50% — احتفظ بالباقي",
            ],
            "target_price": price * 1.15,
            "stop_loss": price * 0.92,
            "hold_period": "1-2 أسبوع للنصف الباقي",
        })
        return rec

    if pnl_pct >= 50:
        rec.update({
            "action": "TAKE_PROFIT_PARTIAL", "icon": "🟡",
            "confidence": "HIGH",
            "reasons": [f"P&L استثنائي (+{pnl_pct:.1f}%)",
                        "اقفل 50% للأمان"],
            "target_price": price * 1.20,
            "stop_loss": avg_buy * 1.10,
            "hold_period": "1-3 شهور للباقي",
        })
        return rec

    if trend == "StrongDown" and pnl_pct < -15:
        rec.update({
            "action": "SELL", "icon": "🔴", "confidence": "HIGH",
            "reasons": ["trend هابط قوي",
                        f"P&L سلبي ({pnl_pct:.1f}%)",
                        "اقطع الخسارة قبل ما تتفاقم"],
        })
        return rec

    if pnl_pct < -25 and trend in ("StrongDown", "MildDown"):
        rec.update({
            "action": "REPLACE", "icon": "🔄", "confidence": "MEDIUM",
            "reasons": [f"خسارة كبيرة ({pnl_pct:.1f}%)",
                        f"trend ضعيف ({trend})",
                        f"ابحث عن بديل في قطاع {sector}"],
        })
        return rec

    if pnl_pct < -8 and rsi is not None and rsi < 35 and trend != "StrongDown":
        rec.update({
            "action": "BUY_MORE", "icon": "🟢",
            "confidence": "HIGH" if rsi < 30 else "MEDIUM",
            "reasons": [f"P&L سلبي خفيف ({pnl_pct:.1f}%)",
                        f"RSI={rsi:.0f} (oversold)",
                        "فرصة DCA كلاسيكية"],
            "target_price": avg_buy * 1.10,
            "stop_loss": price * 0.92,
            "hold_period": "2-4 أسابيع",
        })
        return rec

    if trend in ("StrongUp", "MildUp") and rsi is not None and rsi < 70:
        rec.update({
            "action": "HOLD", "icon": "💎", "confidence": "HIGH",
            "reasons": [f"trend صاعد ({trend})",
                        f"RSI={rsi:.0f} (مساحة للنمو)",
                        "let winners run"],
            "hold_period": "1-3 شهور",
        })
        if atr and price:
            rec["target_price"] = price + (atr * 5)
            rec["stop_loss"] = max(avg_buy, price - (atr * 3))
        return rec

    rec.update({
        "action": "HOLD", "icon": "💎", "confidence": "MEDIUM",
        "reasons": [f"trend: {trend}",
                    f"P&L: {pnl_pct:+.1f}%",
                    "لا إشارة واضحة — راقب"],
        "hold_period": "راقب يومياً",
    })
    return rec


# ══════════════════════════════════════════════════════════════════
# 9. PORTFOLIO BUILDER
# ══════════════════════════════════════════════════════════════════

def build_full_portfolio(do_sync_trades: bool = True,
                         do_technical: bool = True) -> Dict[str, Any]:
    log.info("[PORTFOLIO] building...")
    binance_positions, binance_err = fetch_binance_portfolio()
    okx_positions, okx_err = fetch_okx_portfolio()
    binance_total = sum(p["usd_value"] for p in binance_positions)
    okx_total = sum(p["usd_value"] for p in okx_positions)

    by_asset: Dict[str, Dict] = {}
    for p in binance_positions + okx_positions:
        asset = p["asset"]
        if asset not in by_asset:
            by_asset[asset] = {
                "asset": asset, "total_amount": 0.0, "total_usd": 0.0,
                "price_usd": p["price_usd"],
                "sources": {"binance": {"amount": 0.0, "usd": 0.0},
                            "okx": {"amount": 0.0, "usd": 0.0}},
                "is_stable": asset in STABLECOINS,
                "sector": classify_asset(asset),
            }
        by_asset[asset]["total_amount"] += p["amount"]
        by_asset[asset]["total_usd"] += p["usd_value"]
        by_asset[asset]["sources"][p["source"]]["amount"] += p["amount"]
        by_asset[asset]["sources"][p["source"]]["usd"] += p["usd_value"]

    non_stable_assets = [a for a in by_asset.keys() if a not in STABLECOINS]
    binance_trades: Dict[str, List[Dict]] = {}
    okx_trades: Dict[str, List[Dict]] = {}

    if do_sync_trades and not binance_err:
        try:
            binance_trades = sync_binance_trades(non_stable_assets)
        except Exception as e:
            log.warning(f"[BIN_TRADES] sync failed: {e}")
    if do_sync_trades and not okx_err:
        try:
            okx_trades = sync_okx_trades()
        except Exception as e:
            log.warning(f"[OKX_TRADES] sync failed: {e}")

    for asset, info in by_asset.items():
        if info["is_stable"]:
            info["avg_buy_price"] = 1.0
            info["total_invested"] = info["total_usd"]
            info["realized_pnl"] = 0
            info["unrealized_pnl"] = 0
            info["unrealized_pct"] = 0
            info["first_buy_time"] = 0
            info["buy_count"] = 0
            info["sell_count"] = 0
            continue
        combined = []
        combined.extend(binance_trades.get(asset, []))
        combined.extend(okx_trades.get(asset, []))
        wap = calculate_wap(combined)
        info["avg_buy_price"] = wap["avg_buy_price"]
        info["total_invested"] = wap["total_invested"]
        info["realized_pnl"] = wap["realized_pnl"]
        info["first_buy_time"] = wap["first_buy_time"]
        info["buy_count"] = wap["buy_count"]
        info["sell_count"] = wap["sell_count"]
        if wap["avg_buy_price"] > 0:
            cost_basis = info["total_amount"] * wap["avg_buy_price"]
            unrealized = info["total_usd"] - cost_basis
            unrealized_pct = (unrealized / cost_basis * 100) if cost_basis > 0 else 0
        else:
            unrealized = 0
            unrealized_pct = 0
        info["unrealized_pnl"] = round(unrealized, 2)
        info["unrealized_pct"] = round(unrealized_pct, 2)

    if do_technical and not binance_err:
        for asset, info in by_asset.items():
            if info["is_stable"]:
                continue
            symbol_full = f"{asset}USDT"
            try:
                ta = analyze_technical(symbol_full)
                info.update(ta)
            except Exception as e:
                log.warning(f"[TA] {asset}: {e}")
            time.sleep(0.05)

    for asset, info in by_asset.items():
        try:
            info["recommendation"] = make_recommendation(info)
        except Exception as e:
            log.warning(f"[REC] {asset}: {e}")
            info["recommendation"] = {
                "action": "HOLD", "icon": "❓",
                "reasons": ["خطأ"], "confidence": "LOW",
                "hold_period": "?", "target_price": 0, "stop_loss": 0,
            }

    unified = sorted(by_asset.values(), key=lambda x: x["total_usd"], reverse=True)
    stable_usd = sum(a["total_usd"] for a in unified if a["is_stable"])
    crypto_usd = sum(a["total_usd"] for a in unified if not a["is_stable"])
    total_usd = stable_usd + crypto_usd
    total_invested = sum(a.get("total_invested", 0) for a in unified
                         if not a["is_stable"])
    total_unrealized = sum(a.get("unrealized_pnl", 0) for a in unified
                           if not a["is_stable"])
    total_realized = sum(a.get("realized_pnl", 0) for a in unified
                         if not a["is_stable"])

    sector_totals: Dict[str, float] = {}
    for a in unified:
        sector_totals[a["sector"]] = sector_totals.get(a["sector"], 0) + a["total_usd"]

    portfolio = {
        "timestamp": now_iso(),
        "binance": {"positions": binance_positions, "total_usd": binance_total,
                    "error": binance_err},
        "okx": {"positions": okx_positions, "total_usd": okx_total,
                "error": okx_err},
        "unified": unified, "total_usd": total_usd,
        "stable_usd": stable_usd, "crypto_usd": crypto_usd,
        "total_invested": round(total_invested, 2),
        "total_unrealized": round(total_unrealized, 2),
        "total_realized": round(total_realized, 2),
        "sectors": sector_totals,
    }
    storage_save("portfolio_latest.json", portfolio)
    log.info(f"[PORTFOLIO] built. Total: ${total_usd:,.2f}")
    return portfolio


# ══════════════════════════════════════════════════════════════════
# 10. FORMATTERS
# ══════════════════════════════════════════════════════════════════

def _fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    return f"${value:,.2f}"


def _fmt_amount(amount: float) -> str:
    if amount >= 1000:
        return f"{amount:,.2f}"
    if amount >= 1:
        return f"{amount:,.4f}"
    if amount >= 0.001:
        return f"{amount:.6f}"
    return f"{amount:.8f}"


def _fmt_price(price: float) -> str:
    if price <= 0:
        return "—"
    if price < 0.01:
        return f"${price:.8f}".rstrip("0").rstrip(".")
    if price < 1:
        return f"${price:.6f}".rstrip("0").rstrip(".")
    return f"${price:,.4f}"


def _trend_label(trend: str) -> str:
    return {"StrongUp": "🟢 صاعد قوي", "MildUp": "🟢 صاعد",
            "Sideways": "⚪ جانبي", "MildDown": "🔴 هابط",
            "StrongDown": "🔴 هابط قوي",
            "Unknown": "⚪ غير محدد"}.get(trend, "⚪ غير محدد")


def _action_label(action: str) -> str:
    return {"HOLD": "احتفظ", "SELL": "بِع",
            "BUY_MORE": "اشترِ المزيد (DCA)",
            "REPLACE": "استبدل",
            "TAKE_PROFIT_PARTIAL": "خذ ربح جزئي (50%)"}.get(action, action)


def format_full_portfolio(p: Dict[str, Any]) -> str:
    lines = ["💼 *محفظتك — تحليل كامل*", f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━", ""]

    if p["binance"].get("error"):
        lines.append(f"⚠️ Binance: `{p['binance']['error']}`")
    if p["okx"].get("error"):
        lines.append(f"⚠️ OKX: `{p['okx']['error']}`")
    if p["binance"].get("error") or p["okx"].get("error"):
        lines.append("")

    total = p["total_usd"]
    invested = p.get("total_invested", 0)
    unrealized = p.get("total_unrealized", 0)
    realized = p.get("total_realized", 0)

    lines.append(f"💰 *الإجمالي*: {_fmt_usd(total)}")
    if invested > 0:
        total_pnl = unrealized + realized
        total_pnl_pct = (total_pnl / invested * 100) if invested > 0 else 0
        sign = "+" if total_pnl >= 0 else ""
        emoji = "✅" if total_pnl >= 0 else "❌"
        lines.append(f"📈 *إجمالي P&L*: {sign}{_fmt_usd(total_pnl)} "
                     f"({sign}{total_pnl_pct:.1f}%) {emoji}")
        if abs(unrealized) > 0.01:
            usign = "+" if unrealized >= 0 else ""
            lines.append(f"   • Unrealized: {usign}{_fmt_usd(unrealized)}")
        if abs(realized) > 0.01:
            rsign = "+" if realized >= 0 else ""
            lines.append(f"   • Realized: {rsign}{_fmt_usd(realized)}")

    if p["crypto_usd"] > 0 and p["stable_usd"] > 0:
        crypto_pct = (p["crypto_usd"] / total * 100) if total > 0 else 0
        stable_pct = 100 - crypto_pct
        lines.append("")
        lines.append(f"📊 Crypto: {_fmt_usd(p['crypto_usd'])} ({crypto_pct:.0f}%) | "
                     f"💵 Cash: {_fmt_usd(p['stable_usd'])} ({stable_pct:.0f}%)")

    bin_t = p["binance"]["total_usd"]
    okx_t = p["okx"]["total_usd"]
    if bin_t > 0 or okx_t > 0:
        bin_pct = (bin_t / total * 100) if total > 0 else 0
        okx_pct = (okx_t / total * 100) if total > 0 else 0
        lines.append(f"📍 Binance: {_fmt_usd(bin_t)} ({bin_pct:.0f}%) | "
                     f"OKX: {_fmt_usd(okx_t)} ({okx_pct:.0f}%)")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    unified = p["unified"]
    for i, asset in enumerate(unified, 1):
        sym = asset["asset"]
        sector = asset["sector"]
        amount = asset["total_amount"]
        usd = asset["total_usd"]
        price = asset["price_usd"]
        is_stable = asset["is_stable"]

        bin_amt = asset["sources"]["binance"]["amount"]
        okx_amt = asset["sources"]["okx"]["amount"]
        if bin_amt > 0 and okx_amt > 0:
            src_tag = "Binance+OKX"
        elif bin_amt > 0:
            src_tag = "Binance"
        else:
            src_tag = "OKX"

        tag = "💵" if is_stable else "🪙"
        lines.append(f"{i}️⃣ {tag} *{sym}* — {_fmt_amount(amount)} ({src_tag}) | {sector}")

        if is_stable:
            lines.append(f"   💰 {_fmt_usd(usd)} (cash)")
        else:
            avg_buy = asset.get("avg_buy_price", 0)
            invested = asset.get("total_invested", 0)
            unrealized = asset.get("unrealized_pnl", 0)
            unrealized_pct = asset.get("unrealized_pct", 0)
            buy_count = asset.get("buy_count", 0)

            if avg_buy > 0:
                lines.append(f"   📥 شراء (avg): {_fmt_price(avg_buy)} | "
                             f"الآن: {_fmt_price(price)}")
                if invested > 0:
                    lines.append(f"   💼 مستثمر: {_fmt_usd(invested)} | "
                                 f"قيمة: {_fmt_usd(usd)}")
                    sign = "+" if unrealized >= 0 else ""
                    emoji = "✅" if unrealized >= 0 else "❌"
                    lines.append(f"   📊 P&L: {sign}{_fmt_usd(unrealized)} "
                                 f"({sign}{unrealized_pct:.1f}%) {emoji}")
            else:
                lines.append(f"   💰 السعر الحالي: {_fmt_price(price)}")
                if buy_count == 0:
                    lines.append(f"   _(لا يوجد trade history — اكتشاف رصيد فقط)_")

            trend = asset.get("trend", "Unknown")
            rsi = asset.get("rsi")
            if rsi is not None:
                rsi_tag = ""
                if rsi >= 70:
                    rsi_tag = " [overbought]"
                elif rsi <= 30:
                    rsi_tag = " [oversold]"
                lines.append(f"   📈 Trend: {_trend_label(trend)} | "
                             f"RSI: {rsi:.0f}{rsi_tag}")

            rec = asset.get("recommendation", {})
            action = rec.get("action", "HOLD")
            icon = rec.get("icon", "💎")
            confidence = rec.get("confidence", "MEDIUM")
            conf_emoji = {"HIGH": "🔥", "MEDIUM": "⚖️",
                          "LOW": "❓"}.get(confidence, "")
            lines.append("")
            lines.append(f"   💡 *التوصية*: {icon} {_action_label(action)} {conf_emoji}")
            for reason in rec.get("reasons", []):
                lines.append(f"      • {reason}")
            target = rec.get("target_price", 0)
            stop = rec.get("stop_loss", 0)
            hold = rec.get("hold_period", "")
            if target > 0:
                target_pct = ((target - price) / price * 100) if price > 0 else 0
                lines.append(f"   🎯 الهدف: {_fmt_price(target)} ({target_pct:+.1f}%)")
            if stop > 0:
                stop_pct = ((stop - price) / price * 100) if price > 0 else 0
                lines.append(f"   ⚠️ Stop: {_fmt_price(stop)} ({stop_pct:+.1f}%)")
            if hold:
                lines.append(f"   ⏳ المدة: {hold}")
        lines.append("")

    sectors = p.get("sectors", {})
    if sectors and total > 0:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ *تحليل المخاطر (sectors):*")
        sorted_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)
        for sec_name, sec_usd in sorted_sectors:
            pct = (sec_usd / total * 100) if total > 0 else 0
            warning = ""
            if pct >= 70 and sec_name != "Stable":
                warning = " ⚠️ مركّز جداً"
            elif pct >= 50 and sec_name != "Stable":
                warning = " ⚠️ مركّز"
            lines.append(f"   {sec_name}: {pct:.0f}%{warning}")

    lines.append("")
    lines.append("💡 *اقتراحات:*")
    if total > 0:
        if p["stable_usd"] / total > 0.5:
            lines.append("   • Cash كبير — فكّر في DCA بطيء")
        elif p["stable_usd"] / total < 0.1:
            lines.append("   • Cash قليل — احتفظ بـ stable للفرص")

        has_btc = any(a["asset"] == "BTC" for a in unified)
        has_eth = any(a["asset"] == "ETH" for a in unified)
        if not has_btc and total > 100:
            lines.append("   • لا BTC — أساس أي محفظة (30-40%)")
        if not has_eth and total > 100:
            lines.append("   • لا ETH — مكمّل أساسي (15-25%)")

        if sectors.get("Meme", 0) / total > 0.5:
            lines.append("   ⚠️ Memes مركّز — قلّل المخاطر")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ _تحليل آلي — تنفيذ يدوي 100%_")
    lines.append("⚠️ _تعليمي فقط — ليس نصيحة مالية_")
    return "\n".join(lines)


def format_single_exchange(p: Dict[str, Any], exchange: str) -> str:
    ex_data = p.get(exchange, {})
    positions = ex_data.get("positions", [])
    error = ex_data.get("error")
    total = ex_data.get("total_usd", 0)
    name = "Binance" if exchange == "binance" else "OKX"
    icon = "🟡" if exchange == "binance" else "⚫️"
    lines = [f"{icon} *محفظة {name}*", f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━"]
    if error:
        lines.append(f"❌ *خطأ*: `{error}`")
        return "\n".join(lines)
    if not positions:
        lines.append("⚪ لا توجد عملات")
        return "\n".join(lines)
    lines.append(f"💰 الإجمالي: {_fmt_usd(total)}")
    lines.append(f"🪙 العملات: {len(positions)}")
    lines.append("")
    for i, pos in enumerate(sorted(positions, key=lambda x: x["usd_value"],
                                    reverse=True)[:20], 1):
        asset = pos["asset"]
        amount = pos["amount"]
        usd = pos["usd_value"]
        price = pos["price_usd"]
        tag = "💵" if asset in STABLECOINS else "🪙"
        lines.append(f"{i}. {tag} *{asset}* — {_fmt_amount(amount)} ≈ {_fmt_usd(usd)}")
        if asset not in STABLECOINS:
            lines.append(f"   💰 {_fmt_price(price)}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 11. CONNECTIVITY TEST
# ══════════════════════════════════════════════════════════════════

def run_connectivity_test() -> Dict[str, Any]:
    results = {}
    bin_start = time.time()
    if not BINANCE_API_KEY or not BINANCE_SECRET:
        results["binance"] = {"ok": False, "error": "missing credentials",
                              "elapsed_ms": 0}
    else:
        account = binance_get_account()
        elapsed = int((time.time() - bin_start) * 1000)
        if account and isinstance(account, dict) and "balances" in account:
            non_zero = sum(1 for b in account["balances"]
                          if float(b.get("free", 0)) + float(b.get("locked", 0)) > 0)
            results["binance"] = {"ok": True, "balances": non_zero,
                                  "elapsed_ms": elapsed}
        elif isinstance(account, dict) and "_auth_error" in account:
            results["binance"] = {"ok": False,
                                  "error": f"auth {account['_auth_error']}",
                                  "elapsed_ms": elapsed}
        else:
            results["binance"] = {"ok": False, "error": "request failed",
                                  "elapsed_ms": elapsed}

    okx_start = time.time()
    if not OKX_API_KEY or not OKX_SECRET or not OKX_PASSPHRASE:
        results["okx"] = {"ok": False, "error": "missing credentials",
                          "elapsed_ms": 0}
    else:
        bal = okx_signed_request("/api/v5/account/balance")
        elapsed = int((time.time() - okx_start) * 1000)
        if isinstance(bal, dict) and bal.get("code") == "0":
            details_count = sum(len(e.get("details", [])) for e in bal.get("data", []))
            results["okx"] = {"ok": True, "details_count": details_count,
                              "elapsed_ms": elapsed}
        elif isinstance(bal, dict) and "_auth_error" in bal:
            results["okx"] = {"ok": False, "error": f"auth {bal['_auth_error']}",
                              "elapsed_ms": elapsed}
        else:
            results["okx"] = {"ok": False, "error": "request failed",
                              "elapsed_ms": elapsed}

    cp_start = time.time()
    cp = safe_request("GET", f"{CP_BASE}/global", timeout=(5, 10))
    elapsed = int((time.time() - cp_start) * 1000)
    results["coinpaprika"] = {"ok": bool(cp and "market_cap_usd" in (cp or {})),
                              "elapsed_ms": elapsed}
    storage_ok = storage_save("_health.json", {"ts": now_iso()})
    results["storage"] = {"ok": storage_ok, "path": DATA_DIR}
    return results


# ══════════════════════════════════════════════════════════════════
# 12. TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════════

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💼 *DCA_BOT v2.0* — Smart Portfolio Manager\n"
        "_MVP: Binance + OKX + P&L + TA + Recommendations_\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*الميزات:*\n"
        "💼 محفظة موحّدة (Binance + OKX)\n"
        "📊 P&L per coin (avg buy تلقائي)\n"
        "📈 تحليل فني (RSI, EMA, ATR, Trend)\n"
        "🎯 توصيات: احتفظ / بِع / اشترِ / استبدل / خذ ربح\n"
        "🔄 تصنيف القطاعات + تحليل المخاطر\n\n"
        "*الأوامر:*\n"
        "`/start`           القائمة\n"
        "`/test`            فحص الاتصال\n"
        "`/sync`            مزامنة فورية لـ trades\n"
        "`محفظتي`          التحليل الكامل ⭐\n"
        "`محفظة Binance`   فقط Binance\n"
        "`محفظة OKX`       فقط OKX\n\n"
        "⚠️ _Read-Only — تنفيذ يدوي 100%_\n"
        "⚠️ _تعليمي فقط — ليس نصيحة مالية_"
    )
    await u.message.reply_text(msg, parse_mode="Markdown")


async def cmd_test(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ فحص الاتصالات...")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_connectivity_test)
    lines = ["🔍 *نتيجة الفحص:*\n"]
    b = results["binance"]
    if b["ok"]:
        lines.append(f"✅ *Binance*: {b['balances']} عملة | {b['elapsed_ms']}ms")
    else:
        lines.append(f"❌ *Binance*: {b.get('error', '?')[:80]}")
    o = results["okx"]
    if o["ok"]:
        lines.append(f"✅ *OKX*: {o['details_count']} عملة | {o['elapsed_ms']}ms")
    else:
        lines.append(f"❌ *OKX*: {o.get('error', '?')[:80]}")
    cp = results["coinpaprika"]
    icon = "✅" if cp["ok"] else "❌"
    lines.append(f"{icon} *CoinPaprika*: {cp['elapsed_ms']}ms")
    s = results["storage"]
    icon = "✅" if s["ok"] else "❌"
    lines.append(f"{icon} *Storage*: `{s['path']}`")
    ok_count = sum(1 for k in ("binance", "okx", "coinpaprika", "storage")
                   if results[k]["ok"])
    lines.append("")
    lines.append(f"🎯 *الحالة*: {ok_count}/4")
    await msg.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_sync(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ مزامنة trade history...")
    loop = asyncio.get_event_loop()
    binance_pos, _ = await loop.run_in_executor(None, fetch_binance_portfolio)
    assets = [p["asset"] for p in binance_pos
              if p["asset"] not in STABLECOINS]
    bin_trades = await loop.run_in_executor(None, sync_binance_trades, assets)
    okx_trades = await loop.run_in_executor(None, sync_okx_trades)
    bin_total = sum(len(v) for v in bin_trades.values())
    okx_total = sum(len(v) for v in okx_trades.values())
    await msg.delete()
    await u.message.reply_text(
        f"✅ *مزامنة منتهية*\n\n"
        f"🟡 Binance: {bin_total} trade ({len(bin_trades)} عملة)\n"
        f"⚫️ OKX: {okx_total} trade ({len(okx_trades)} عملة)\n\n"
        f"أرسل `محفظتي` للتحليل الكامل.",
        parse_mode="Markdown"
    )


async def handle_msg(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text:
        return
    text = u.message.text.strip()
    text_l = text.lower()

    if text_l in ("محفظتي", "محفظة", "portfolio", "wallet"):
        msg = await u.message.reply_text(
            "⏳ جاري التحليل الكامل...\n_(محفظة + trades + TA + توصيات)_\n"
            "قد يستغرق 30-60 ثانية في أول مرة.",
            parse_mode="Markdown"
        )
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_full_portfolio)
        formatted = format_full_portfolio(portfolio)
        await msg.delete()
        if len(formatted) > 3900:
            chunks = []
            current = ""
            for line in formatted.split("\n"):
                if len(current) + len(line) + 1 > 3900:
                    chunks.append(current)
                    current = line
                else:
                    current = current + "\n" + line if current else line
            if current:
                chunks.append(current)
            for ch in chunks:
                await u.message.reply_text(ch, parse_mode="Markdown")
        else:
            await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    if "binance" in text_l:
        msg = await u.message.reply_text("⏳ Binance...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_full_portfolio,
                                                False, False)
        formatted = format_single_exchange(portfolio, "binance")
        await msg.delete()
        await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    if "okx" in text_l or "اوكي" in text or "أوكي" in text:
        msg = await u.message.reply_text("⏳ OKX...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_full_portfolio,
                                                False, False)
        formatted = format_single_exchange(portfolio, "okx")
        await msg.delete()
        await u.message.reply_text(formatted, parse_mode="Markdown")
        return

    if text_l in ("تحديث", "refresh", "update"):
        msg = await u.message.reply_text("⏳ تحديث سريع...")
        loop = asyncio.get_event_loop()
        portfolio = await loop.run_in_executor(None, build_full_portfolio,
                                                False, False)
        await msg.delete()
        await u.message.reply_text(
            f"✅ *تم التحديث*\n\n"
            f"💰 الإجمالي: {_fmt_usd(portfolio['total_usd'])}\n"
            f"🪙 العملات: {len(portfolio['unified'])}\n"
            f"🕐 {now_str()}\n\n"
            f"أرسل `محفظتي` للتحليل الكامل.",
            parse_mode="Markdown"
        )
        return

    await u.message.reply_text(
        "🤖 لم أفهم الأمر.\n\nأرسل `/start` لرؤية الأوامر.",
        parse_mode="Markdown"
    )


async def error_handler(update, context):
    log.warning(f"[ERR] {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ خطأ مؤقت. حاول مرة أخرى.")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# 13. MAIN
# ══════════════════════════════════════════════════════════════════

async def _post_init(app):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        log.info("✅ Webhook cleared")
    except Exception as e:
        log.warning(f"webhook clear failed: {e}")


def _print_banner():
    bin_status = "✅ مفعّل" if (BINANCE_API_KEY and BINANCE_SECRET) else "⚪ معطّل"
    okx_status = ("✅ مفعّل"
                  if (OKX_API_KEY and OKX_SECRET and OKX_PASSPHRASE)
                  else "⚪ معطّل")
    print("=" * 70)
    print("  💼 DCA_BOT v2.0 — Smart Portfolio Manager (MVP) ✅")
    print("=" * 70)
    print(f"  المنصات         :")
    print(f"    🟡 Binance     : {bin_status}")
    print(f"    ⚫️ OKX         : {okx_status}")
    print(f"  Storage          : {DATA_DIR}")
    print(f"  المراحل المدمجة  : 3.1 + 3.2 + 3.3 + 3.4 (MVP)")
    print(f"  الميزات          :")
    print(f"    💼 Unified portfolio")
    print(f"    📊 Auto avg buy + P&L")
    print(f"    📈 Technical analysis")
    print(f"    🎯 Recommendations engine")
    print(f"    🔄 Sector classification")
    print("=" * 70)


def main():
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN غير موجود")
        return
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_msg
    ))
    app.add_error_handler(error_handler)
    _print_banner()
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
